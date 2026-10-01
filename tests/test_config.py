from pathlib import Path

import pytest

from voiceover.config import ConfigError, combine_styles, load_script, parse_id_list


def write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "s.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_valid_script(script_file):
    script = load_script(script_file)
    assert script.project == "test-promo"
    assert script.voice == "Charon"
    assert [s.id for s in script.segments] == ["V01", "V02"]
    assert script.segments[1].style is None


def test_voice_name_is_canonicalized(tmp_path):
    script = load_script(write(tmp_path, "project: p\nvoice: charon\nsegments:\n  - {id: V01, text: Hi}\n"))
    assert script.voice == "Charon"


@pytest.mark.parametrize(
    "content, fragment",
    [
        ("project: p\nvoice: Charon\nsegments:\n  - {id: V01, text: a}\n  - {id: V01, text: b}\n", "duplicate segment ids: V01"),
        ("project: p\nvoice: Charon\nsegments:\n  - {id: V01, text: '   '}\n", "must not be empty"),
        ("project: p\nvoice: NotAVoice\nsegments:\n  - {id: V01, text: a}\n", "unknown prebuilt voice"),
        ("project: p\nvoice: ''\nsegments:\n  - {id: V01, text: a}\n", "voice must be set"),
        ("project: p\nsegments:\n  - {id: V01, text: a}\n", "voice"),
        ("project: p\nvoice: Charon\nsegments: []\n", "segments"),
        ("project: ../evil\nvoice: Charon\nsegments:\n  - {id: V01, text: a}\n", "project"),
        ("project: p\nvoice: Charon\nvoise: x\nsegments:\n  - {id: V01, text: a}\n", "voise"),
    ],
)
def test_invalid_scripts(tmp_path, content, fragment):
    with pytest.raises(ConfigError, match=fragment):
        load_script(write(tmp_path, content))


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_script(tmp_path / "nope.yaml")


def test_invalid_yaml(tmp_path):
    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_script(write(tmp_path, "project: [unclosed\n"))


def test_select_filters_in_script_order(script_file):
    script = load_script(script_file)
    assert [s.id for s in script.select(["V02", "V01"])] == ["V01", "V02"]
    assert [s.id for s in script.select([])] == ["V01", "V02"]
    with pytest.raises(ConfigError, match="V99"):
        script.select(["V99"])


def test_combined_style(script_file):
    script = load_script(script_file)
    assert script.combined_style(script.segments[0]) == "Warm and confident. Understanding frustration."
    assert script.combined_style(script.segments[1]) == "Warm and confident."
    assert combine_styles("", None) == ""


def test_parse_id_list():
    assert parse_id_list("V03, V07,,") == ["V03", "V07"]
    assert parse_id_list(None) == []


def test_bundled_autokool_script_is_valid():
    script = load_script(Path(__file__).parent.parent / "scripts" / "autokool.yaml")
    assert [s.id for s in script.segments] == [f"V0{i}" for i in range(1, 10)]
    assert script.voice == "Charon"
