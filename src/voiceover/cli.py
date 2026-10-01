"""Typer command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from voiceover import audio, report
from voiceover.config import ConfigError, Script, Segment, load_script, parse_id_list, validate_voice
from voiceover.tts_client import (
    InvalidApiKeyError,
    MissingApiKeyError,
    TTSClient,
    TTSError,
    default_model,
    load_api_key,
)
from voiceover.voices import PREBUILT_VOICES

app = typer.Typer(
    help="Generate segment-by-segment voice-overs with Gemini Text-to-Speech.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)

ScriptArg = Annotated[Path, typer.Argument(help="Path to the YAML script.", exists=False)]
OutputOpt = Annotated[Path, typer.Option("--output-dir", "-o", help="Root output directory.")]
ModelOpt = Annotated[Optional[str], typer.Option("--model", help="TTS model (default: GEMINI_TTS_MODEL or gemini-3.8-flash-tts).")]
DryRunOpt = Annotated[bool, typer.Option("--dry-run", help="Print the final text sent to the API without calling it.")]


def make_client(model: str) -> TTSClient:
    """Create the API client (patched in tests)."""
    api_key = load_api_key()

    def on_retry(attempt: int, delay: float, exc: BaseException) -> None:
        err_console.print(f"[yellow]  transient error ({exc.__class__.__name__}), retry {attempt} in {delay:.1f}s[/]")

    return TTSClient(api_key, model, on_retry=on_retry)


def _fail(message: str) -> None:
    err_console.print(f"[bold red]Error:[/] {message}")
    raise typer.Exit(code=1)


def _load(script_path: Path) -> Script:
    try:
        return load_script(script_path)
    except ConfigError as exc:
        _fail(str(exc))
        raise  # unreachable, keeps type checkers happy


def _client_or_exit(model: str) -> TTSClient:
    try:
        return make_client(model)
    except MissingApiKeyError as exc:
        _fail(str(exc))
        raise


def _print_dry_run(script: Script, segments: list[Segment], voice: str) -> None:
    table = Table(title=f"Dry run: {script.project} (voice {voice}, {script.language})", show_lines=True)
    table.add_column("Segment", no_wrap=True)
    table.add_column("Text sent to the API")
    table.add_column("Style")
    for segment in segments:
        table.add_row(segment.id, script.prepared_text(segment), script.combined_style(segment))
    console.print(table)


def _synthesize_to_file(
    client: TTSClient, script: Script, segment: Segment, voice: str, path: Path
) -> report.SegmentMetrics:
    result = client.synthesize(
        script.prepared_text(segment),
        voice=voice,
        style=script.combined_style(segment),
        language=script.language,
    )
    processed = audio.process(result.data, result.sample_rate)
    audio.write_wav(path, processed.samples, processed.sample_rate)
    return report.segment_metrics(
        segment.id, path, segment.text, processed.duration_s, processed.loudness_lufs, processed.peak_dbfs
    )


def _metrics_from_disk(script: Script, out_dir: Path) -> list[report.SegmentMetrics]:
    metrics = []
    for segment in script.segments:
        path = out_dir / f"{segment.id}.wav"
        if not path.exists():
            continue
        measured = audio.read_wav(path)
        metrics.append(
            report.segment_metrics(
                segment.id, path, segment.text, measured.duration_s, measured.loudness_lufs, measured.peak_dbfs
            )
        )
    return metrics


@app.command()
def generate(
    script_path: ScriptArg,
    only: Annotated[Optional[str], typer.Option("--only", help="Comma-separated segment ids, e.g. V03,V07.")] = None,
    skip_existing: Annotated[bool, typer.Option("--skip-existing", help="Skip segments whose WAV already exists.")] = False,
    dry_run: DryRunOpt = False,
    output_dir: OutputOpt = Path("output"),
    model: ModelOpt = None,
) -> None:
    """Generate every segment (or a subset) as <output>/<project>/<ID>.wav."""
    script = _load(script_path)
    try:
        segments = script.select(parse_id_list(only))
    except ConfigError as exc:
        _fail(str(exc))
    out_dir = output_dir / script.project

    if skip_existing:
        skipped = [s.id for s in segments if (out_dir / f"{s.id}.wav").exists()]
        segments = [s for s in segments if s.id not in skipped]
        if skipped:
            console.print(f"[dim]Skipping existing: {', '.join(skipped)}[/]")

    if dry_run:
        _print_dry_run(script, segments, script.voice)
        return

    model_name = model or default_model()
    failures: dict[str, str] = {}
    if segments:
        client = _client_or_exit(model_name)
        console.print(f"Generating {len(segments)} segment(s) with [bold]{script.voice}[/] ({model_name}) → {out_dir}/")
        for segment in segments:
            path = out_dir / f"{segment.id}.wav"
            with console.status(f"{segment.id}…"):
                try:
                    m = _synthesize_to_file(client, script, segment, script.voice, path)
                except InvalidApiKeyError as exc:
                    _fail(str(exc))
                except (TTSError, audio.AudioError) as exc:
                    failures[segment.id] = str(exc)
                    err_console.print(f"[red]✗ {segment.id}: {exc}[/]")
                    continue
            console.print(f"[green]✓[/] {segment.id} ({m.duration_s:.2f}s)")
    else:
        console.print("Nothing to generate.")

    metrics = _metrics_from_disk(script, out_dir)
    if metrics:
        report_path = out_dir / "report.json"
        data = report.build_report(script.project, script.voice, model_name, metrics)
        if failures:
            data["failures"] = failures
        report.write_report(report_path, data)
        report.render_table(metrics, console, title=f"{script.project} ({script.voice})")
        console.print(f"[dim]Report written to {report_path}[/]")
    if failures:
        _fail(f"{len(failures)} segment(s) failed: {', '.join(failures)}")


@app.command()
def preview(
    script_path: ScriptArg,
    voices: Annotated[str, typer.Option("--voices", help="Comma-separated voice names, e.g. Charon,Puck,Orus.")],
    segment_id: Annotated[Optional[str], typer.Option("--segment", help="Segment id (default: first segment).")] = None,
    dry_run: DryRunOpt = False,
    output_dir: OutputOpt = Path("output"),
    model: ModelOpt = None,
) -> None:
    """Render one segment with several voices into <output>/<project>/preview/."""
    script = _load(script_path)
    try:
        segment = script.segment(segment_id) if segment_id else script.segments[0]
        voice_names = [validate_voice(v) for v in parse_id_list(voices)]
    except (ConfigError, ValueError) as exc:
        _fail(str(exc))
    if not voice_names:
        _fail("--voices must list at least one voice.")

    if dry_run:
        for voice in voice_names:
            _print_dry_run(script, [segment], voice)
        return

    model_name = model or default_model()
    client = _client_or_exit(model_name)
    out_dir = output_dir / script.project / "preview"
    rows: list[tuple[str, report.SegmentMetrics]] = []
    for voice in voice_names:
        path = out_dir / f"{segment.id}_{voice}.wav"
        with console.status(f"{segment.id} with {voice}…"):
            try:
                rows.append((voice, _synthesize_to_file(client, script, segment, voice, path)))
            except InvalidApiKeyError as exc:
                _fail(str(exc))
            except (TTSError, audio.AudioError) as exc:
                err_console.print(f"[red]✗ {voice}: {exc}[/]")

    table = Table(title=f"Preview {segment.id}")
    for column in ("Voice", "File", "Duration (s)", "Words/s", "Loudness (LUFS)"):
        table.add_column(column, justify="left" if column in ("Voice", "File") else "right")
    for voice, m in rows:
        table.add_row(
            voice,
            str(out_dir / m.file),
            f"{m.duration_s:.2f}",
            f"{m.words_per_second:.2f}",
            "n/a" if m.loudness_lufs is None else f"{m.loudness_lufs:.1f}",
            style=None if m.pace_ok else "bold orange1",
        )
    console.print(table)
    if len(rows) < len(voice_names):
        raise typer.Exit(code=1)


@app.command("voices")
def list_voices(
    offline: Annotated[bool, typer.Option("--offline", help="Use the built-in catalog without calling the API.")] = False,
    language: Annotated[Optional[str], typer.Option("--language", help="Filter by BCP-47 code (API only), e.g. fr-FR.")] = None,
) -> None:
    """List available prebuilt voices (from the API when a key is configured)."""
    rows: list[tuple[str, str]] = []
    source = "built-in catalog (ai.google.dev docs)"
    if not offline:
        try:
            client = make_client(default_model())
            api_voices = client.list_voices(language_code=language)
            rows = [(v["name"], " · ".join(x for x in (v["description"], v["gender"], v["language"]) if x)) for v in api_voices]
            source = "Gemini voices API"
        except MissingApiKeyError:
            err_console.print("[yellow]GEMINI_API_KEY not set, showing the built-in catalog.[/]")
        except TTSError as exc:
            err_console.print(f"[yellow]Voices API unavailable ({exc}), showing the built-in catalog.[/]")
    if not rows:
        rows = list(PREBUILT_VOICES.items())

    table = Table(title=f"Prebuilt voices — {source}")
    table.add_column("Voice", style="bold")
    table.add_column("Description")
    for name, description in rows:
        table.add_row(name, description)
    console.print(table)


if __name__ == "__main__":
    app()
