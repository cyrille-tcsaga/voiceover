import base64
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

SCRIPT_YAML = """\
project: test-promo
voice: Charon
language: fr-FR
style: Warm and confident.
pronunciations:
  AutoKool: "Auto Koul"
  FCFA: "francs CFA"
segments:
  - id: V01
    text: "Gérer une auto-école, c'est épuisant."
    style: "Understanding frustration."
  - id: V02
    text: "Voici AutoKool, dès quinze mille FCFA."
"""


def make_pcm(
    sample_rate: int = 24_000,
    lead_s: float = 0.5,
    tone_s: float = 1.5,
    tail_s: float = 0.7,
    amplitude: float = 0.1,
) -> bytes:
    """Silence + 440 Hz tone + silence as raw 16-bit little-endian PCM."""
    t = np.arange(int(tone_s * sample_rate)) / sample_rate
    tone = amplitude * np.sin(2 * np.pi * 440 * t)
    signal = np.concatenate(
        [np.zeros(int(lead_s * sample_rate)), tone, np.zeros(int(tail_s * sample_rate))]
    )
    return (signal * 32767).astype("<i2").tobytes()


class FakeInteractions:
    def __init__(self, responses=None):
        # Each response is either bytes (audio payload) or an exception to raise.
        self.responses = list(responses or [])
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0) if self.responses else make_pcm()
        if isinstance(item, BaseException):
            raise item
        return SimpleNamespace(
            output_audio=SimpleNamespace(
                data=base64.b64encode(item).decode(), mime_type="audio/l16;rate=24000"
            )
        )


class FakeGenAIClient:
    def __init__(self, responses=None, voices_pages=None):
        self.interactions = FakeInteractions(responses)
        self.voices = SimpleNamespace(list=self._list_voices)
        self._voices_pages = list(voices_pages or [])
        self.voice_calls = []

    def _list_voices(self, **kwargs):
        self.voice_calls.append(kwargs)
        return self._voices_pages.pop(0)


class FakeHTTPError(Exception):
    def __init__(self, status_code: int, message: str = "error"):
        super().__init__(message)
        self.status_code = status_code


@pytest.fixture
def script_file(tmp_path: Path) -> Path:
    path = tmp_path / "script.yaml"
    path.write_text(SCRIPT_YAML, encoding="utf-8")
    return path
