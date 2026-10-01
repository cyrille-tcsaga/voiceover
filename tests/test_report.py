import json
from pathlib import Path

import pytest
from rich.console import Console

from voiceover import report


def metrics(seg_id: str, duration: float, text: str) -> report.SegmentMetrics:
    return report.segment_metrics(seg_id, Path(f"/x/{seg_id}.wav"), text, duration, -16.04, -1.5)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Gérer une auto-école, c'est épuisant.", 5),
        ("D'un coup d'œil, suivez vos revenus.", 6),
        ("Moniteurs, véhicules : tout au même endroit.", 6),
        ("", 0),
    ],
)
def test_count_words(text, expected):
    assert report.count_words(text) == expected


def test_segment_metrics_and_pace_flags():
    ok = metrics("V01", 2.0, "un deux trois quatre cinq")  # 2.5 wps
    slow = metrics("V02", 2.0, "un deux trois quatre")  # 2.0 wps
    fast = metrics("V03", 1.0, "un deux trois quatre")  # 4.0 wps
    assert ok.words_per_second == 2.5 and ok.pace_ok
    assert not slow.pace_ok
    assert not fast.pace_ok
    assert ok.file == "V01.wav"
    assert ok.loudness_lufs == -16.04


def test_pace_bounds_are_inclusive():
    assert metrics("A", 10.0, " ".join(["w"] * 22)).pace_ok
    assert metrics("B", 10.0, " ".join(["w"] * 32)).pace_ok


def test_zero_duration_does_not_crash():
    assert metrics("V01", 0.0, "mot").words_per_second == 0.0


def test_build_and_write_report(tmp_path):
    segs = [metrics("V01", 2.0, "un deux trois quatre cinq"), metrics("V02", 1.5, "un deux")]
    data = report.build_report("proj", "Charon", "gemini-3.8-flash-tts", segs)
    path = tmp_path / "out" / "report.json"
    report.write_report(path, data)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["total_duration_s"] == 3.5
    assert loaded["voice"] == "Charon"
    assert [s["id"] for s in loaded["segments"]] == ["V01", "V02"]
    assert loaded["segments"][0]["pace_ok"] is True
    assert loaded["segments"][1]["pace_ok"] is False


def test_render_table_flags_out_of_range_pace():
    console = Console(record=True, width=120, force_terminal=True, color_system="truecolor")
    report.render_table([metrics("V01", 2.0, "un deux trois quatre cinq"), metrics("V02", 1.0, "a b c d")], console)
    styled = console.export_text(styles=True, clear=False)
    text = console.export_text()
    assert "V01" in text and "V02" in text
    assert "Total duration: 3.00 s" in text
    assert "Pace outside 2.2-3.2 words/s: V02" in text
    # orange1 is xterm color 214
    assert "38;5;214" in styled
