"""Per-segment metrics, report.json and the Rich summary table."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

MIN_WPS = 2.2
MAX_WPS = 3.2
WORD_PATTERN = re.compile(r"\w+(?:['’-]\w+)*")


@dataclass(frozen=True)
class SegmentMetrics:
    id: str
    file: str
    duration_s: float
    word_count: int
    words_per_second: float
    loudness_lufs: float | None
    peak_dbfs: float

    @property
    def pace_ok(self) -> bool:
        return MIN_WPS <= self.words_per_second <= MAX_WPS


def count_words(text: str) -> int:
    return len(WORD_PATTERN.findall(text))


def segment_metrics(
    segment_id: str,
    file: Path,
    text: str,
    duration_s: float,
    loudness_lufs: float | None,
    peak_dbfs: float,
) -> SegmentMetrics:
    words = count_words(text)
    wps = words / duration_s if duration_s > 0 else 0.0
    return SegmentMetrics(
        id=segment_id,
        file=file.name,
        duration_s=round(duration_s, 3),
        word_count=words,
        words_per_second=round(wps, 2),
        loudness_lufs=None if loudness_lufs is None else round(loudness_lufs, 2),
        peak_dbfs=round(peak_dbfs, 2),
    )


def build_report(project: str, voice: str, model: str, segments: list[SegmentMetrics]) -> dict:
    return {
        "project": project,
        "voice": voice,
        "model": model,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pace_range_wps": [MIN_WPS, MAX_WPS],
        "total_duration_s": round(sum(s.duration_s for s in segments), 3),
        "segments": [asdict(s) | {"pace_ok": s.pace_ok} for s in segments],
    }


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_table(segments: list[SegmentMetrics], console: Console, title: str = "Voice-over report") -> None:
    table = Table(title=title, show_footer=True)
    total = sum(s.duration_s for s in segments)
    table.add_column("Segment", footer="Total")
    table.add_column("Duration (s)", justify="right", footer=f"{total:.2f}")
    table.add_column("Words", justify="right", footer=str(sum(s.word_count for s in segments)))
    table.add_column("Words/s", justify="right")
    table.add_column("Loudness (LUFS)", justify="right")
    for s in segments:
        loudness = "n/a" if s.loudness_lufs is None else f"{s.loudness_lufs:.1f}"
        table.add_row(
            s.id,
            f"{s.duration_s:.2f}",
            str(s.word_count),
            f"{s.words_per_second:.2f}",
            loudness,
            style=None if s.pace_ok else "bold orange1",
        )
    console.print(table)
    flagged = [s.id for s in segments if not s.pace_ok]
    if flagged:
        console.print(
            f"[orange1]Pace outside {MIN_WPS}-{MAX_WPS} words/s: {', '.join(flagged)}[/]"
        )
    console.print(f"[bold]Total duration: {total:.2f} s[/]")
