import json

import pytest
import soundfile as sf
from typer.testing import CliRunner

from voiceover import cli
from voiceover.tts_client import MissingApiKeyError, TTSClient
from conftest import FakeGenAIClient, FakeHTTPError

runner = CliRunner()


@pytest.fixture
def fake_api(monkeypatch):
    fake = FakeGenAIClient()
    monkeypatch.setattr(
        cli, "make_client", lambda model: TTSClient("k", model, client=fake, sleep=lambda s: None)
    )
    return fake


def test_generate_all(script_file, tmp_path, fake_api):
    out = tmp_path / "out"
    result = runner.invoke(cli.app, ["generate", str(script_file), "-o", str(out), "--model", "m"])
    assert result.exit_code == 0, result.output
    project_dir = out / "test-promo"
    for seg in ("V01", "V02"):
        info = sf.info(project_dir / f"{seg}.wav")
        assert (info.samplerate, info.channels, info.subtype) == (48_000, 1, "PCM_16")
    data = json.loads((project_dir / "report.json").read_text(encoding="utf-8"))
    assert [s["id"] for s in data["segments"]] == ["V01", "V02"]
    assert data["model"] == "m"
    assert "Total duration" in result.output
    sent = [c["input"][0]["content"][0]["text"] for c in fake_api.interactions.calls]
    assert sent[1] == "Voici Auto Koul, dès quinze mille francs CFA."


def test_generate_only_and_skip_existing(script_file, tmp_path, fake_api):
    out = tmp_path / "out"
    assert runner.invoke(cli.app, ["generate", str(script_file), "-o", str(out), "--only", "V02"]).exit_code == 0
    assert len(fake_api.interactions.calls) == 1
    assert not (out / "test-promo" / "V01.wav").exists()

    result = runner.invoke(cli.app, ["generate", str(script_file), "-o", str(out), "--skip-existing"])
    assert result.exit_code == 0, result.output
    assert len(fake_api.interactions.calls) == 2  # only V01 was generated
    data = json.loads((out / "test-promo" / "report.json").read_text(encoding="utf-8"))
    assert [s["id"] for s in data["segments"]] == ["V01", "V02"]


def test_generate_unknown_only_id(script_file, tmp_path, fake_api):
    result = runner.invoke(cli.app, ["generate", str(script_file), "-o", str(tmp_path), "--only", "V99"])
    assert result.exit_code == 1
    assert "V99" in result.output


def test_dry_run_never_calls_api(script_file, tmp_path, monkeypatch):
    def boom(model):
        raise AssertionError("API client must not be created in dry-run")

    monkeypatch.setattr(cli, "make_client", boom)
    out = tmp_path / "out"
    result = runner.invoke(cli.app, ["generate", str(script_file), "-o", str(out), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Auto Koul" in result.output
    assert not out.exists()


def test_missing_key_message(script_file, tmp_path, monkeypatch):
    def missing(model):
        raise MissingApiKeyError("GEMINI_API_KEY is not set.")

    monkeypatch.setattr(cli, "make_client", missing)
    result = runner.invoke(cli.app, ["generate", str(script_file), "-o", str(tmp_path)])
    assert result.exit_code == 1
    assert "GEMINI_API_KEY is not set" in result.output


def test_invalid_key_aborts(script_file, tmp_path, fake_api):
    fake_api.interactions.responses = [FakeHTTPError(403)]
    result = runner.invoke(cli.app, ["generate", str(script_file), "-o", str(tmp_path)])
    assert result.exit_code == 1
    assert "rejected the key" in result.output
    assert len(fake_api.interactions.calls) == 1


def test_failed_segment_is_reported_and_others_continue(script_file, tmp_path, fake_api):
    fake_api.interactions.responses = [FakeHTTPError(400, "bad")]
    result = runner.invoke(cli.app, ["generate", str(script_file), "-o", str(tmp_path)])
    assert result.exit_code == 1
    assert (tmp_path / "test-promo" / "V02.wav").exists()
    data = json.loads((tmp_path / "test-promo" / "report.json").read_text(encoding="utf-8"))
    assert "V01" in data["failures"]


def test_preview_multiple_voices(script_file, tmp_path, fake_api):
    result = runner.invoke(
        cli.app,
        ["preview", str(script_file), "--voices", "Charon,puck", "--segment", "V02", "-o", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    preview_dir = tmp_path / "test-promo" / "preview"
    assert (preview_dir / "V02_Charon.wav").exists()
    assert (preview_dir / "V02_Puck.wav").exists()
    voices = [c["generation_config"]["speech_config"][0]["voice"] for c in fake_api.interactions.calls]
    assert voices == ["Charon", "Puck"]


def test_preview_rejects_unknown_voice(script_file, tmp_path, fake_api):
    result = runner.invoke(cli.app, ["preview", str(script_file), "--voices", "Nope", "-o", str(tmp_path)])
    assert result.exit_code == 1
    assert fake_api.interactions.calls == []


def test_voices_offline():
    result = runner.invoke(cli.app, ["voices", "--offline"])
    assert result.exit_code == 0
    assert "Charon" in result.output and "Sulafat" in result.output


def test_voices_falls_back_without_key(monkeypatch):
    def missing(model):
        raise MissingApiKeyError("no key")

    monkeypatch.setattr(cli, "make_client", missing)
    result = runner.invoke(cli.app, ["voices"])
    assert result.exit_code == 0
    assert "built-in catalog" in result.output
