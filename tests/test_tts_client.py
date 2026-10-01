import base64

import httpx
import pytest

from voiceover import tts_client
from voiceover.tts_client import (
    InvalidApiKeyError,
    MissingApiKeyError,
    RetriesExhaustedError,
    TTSClient,
    TTSError,
)
from conftest import FakeGenAIClient, FakeHTTPError


def make(fake, **kwargs):
    sleeps = []
    client = TTSClient("k", "gemini-3.8-flash-tts", client=fake, sleep=sleeps.append, **kwargs)
    return client, sleeps


def test_request_shape():
    fake = FakeGenAIClient(responses=[b"\x01\x00\x02\x00"])
    client, _ = make(fake)
    result = client.synthesize("Bonjour", voice="Charon", style="Warm.", language="fr-FR")
    call = fake.interactions.calls[0]
    assert call["model"] == "gemini-3.8-flash-tts"
    assert call["input"] == [
        {
            "type": "user_input",
            "content": [
                {"type": "text", "text": "Bonjour", "annotations": [{"type": "speech_metadata", "style": "Warm."}]}
            ],
        }
    ]
    assert call["response_format"] == {"type": "audio", "mime_type": "audio/l16", "sample_rate": 24000}
    assert call["generation_config"] == {"speech_config": [{"voice": "Charon", "language": "fr-FR"}]}
    assert result.data == b"\x01\x00\x02\x00"
    assert result.sample_rate == 24000


def test_no_style_means_no_annotations():
    fake = FakeGenAIClient()
    client, _ = make(fake)
    client.synthesize("Bonjour", voice="Charon")
    assert "annotations" not in fake.interactions.calls[0]["input"][0]["content"][0]


@pytest.mark.parametrize("status", [429, 500, 503])
def test_retries_on_429_and_5xx_with_exponential_backoff(status, monkeypatch):
    monkeypatch.setattr(tts_client.random, "uniform", lambda a, b: 0.0)
    fake = FakeGenAIClient(responses=[FakeHTTPError(status), FakeHTTPError(status), b"\x00\x00"])
    client, sleeps = make(fake, base_delay=1.0)
    client.synthesize("x", voice="Charon")
    assert sleeps == [1.0, 2.0]
    assert len(fake.interactions.calls) == 3


def test_retries_on_transport_error():
    fake = FakeGenAIClient(responses=[httpx.ConnectError("boom"), b"\x00\x00"])
    client, sleeps = make(fake)
    client.synthesize("x", voice="Charon")
    assert len(sleeps) == 1


def test_gives_up_after_max_retries():
    fake = FakeGenAIClient(responses=[FakeHTTPError(503)] * 4)
    client, sleeps = make(fake, max_retries=3)
    with pytest.raises(RetriesExhaustedError):
        client.synthesize("x", voice="Charon")
    assert len(sleeps) == 3


def test_backoff_is_capped():
    client, _ = make(FakeGenAIClient(), base_delay=1.0, max_delay=8.0)
    assert client._backoff(10) <= 8.0 * 1.25


def test_does_not_retry_on_other_4xx():
    fake = FakeGenAIClient(responses=[FakeHTTPError(400, "bad request")])
    client, sleeps = make(fake)
    with pytest.raises(TTSError, match="400"):
        client.synthesize("x", voice="Charon")
    assert sleeps == []


@pytest.mark.parametrize(
    "error",
    [FakeHTTPError(400, "API key not valid. Please pass a valid API key."), FakeHTTPError(403), FakeHTTPError(401)],
)
def test_invalid_key_has_clear_message(error):
    client, sleeps = make(FakeGenAIClient(responses=[error]))
    with pytest.raises(InvalidApiKeyError, match="GEMINI_API_KEY"):
        client.synthesize("x", voice="Charon")
    assert sleeps == []


def test_empty_audio_raises():
    fake = FakeGenAIClient()
    fake.interactions.create = lambda **kw: type("R", (), {"output_audio": None})()
    client, _ = make(fake)
    with pytest.raises(TTSError, match="no audio"):
        client.synthesize("x", voice="Charon")


def test_dict_response_is_supported():
    fake = FakeGenAIClient()
    fake.interactions.create = lambda **kw: {"output_audio": {"data": base64.b64encode(b"ab").decode(), "mime_type": "audio/l16;rate=16000"}}
    client, _ = make(fake)
    result = client.synthesize("x", voice="Charon")
    assert result.sample_rate == 16000


def test_list_voices_paginates():
    pages = [
        {"voices": [{"id": "Charon", "description": "Informative", "gender": "male"}], "next_page_token": "t"},
        {"voices": [{"id": "Kore", "description": "Firm"}], "next_page_token": None},
    ]
    fake = FakeGenAIClient(voices_pages=pages)
    client, _ = make(fake)
    voices = client.list_voices(language_code="fr-FR")
    assert [v["name"] for v in voices] == ["Charon", "Kore"]
    assert fake.voice_calls[0]["language_code"] == ["fr-FR"]
    assert fake.voice_calls[1]["page_token"] == "t"


def test_load_api_key(monkeypatch):
    monkeypatch.setattr(tts_client, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "  secret  ")
    assert tts_client.load_api_key() == "secret"
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(MissingApiKeyError, match="GEMINI_API_KEY"):
        tts_client.load_api_key()
