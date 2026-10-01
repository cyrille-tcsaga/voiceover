"""Thin wrapper around the Gemini TTS Interactions API with retries."""

from __future__ import annotations

import base64
import os
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from dotenv import load_dotenv

DEFAULT_MODEL = "gemini-3.8-flash-tts"
API_SAMPLE_RATE = 24_000
API_MIME_TYPE = "audio/l16"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
AUTH_HINTS = ("api key not valid", "api_key_invalid", "invalid api key", "permission_denied")


class TTSError(Exception):
    """Generic, non-retryable TTS failure."""


class MissingApiKeyError(TTSError):
    pass


class InvalidApiKeyError(TTSError):
    pass


class RetriesExhaustedError(TTSError):
    pass


@dataclass(frozen=True)
class TTSAudio:
    data: bytes
    mime_type: str
    sample_rate: int


def load_api_key() -> str:
    """Read GEMINI_API_KEY from the environment (after loading .env)."""
    load_dotenv()
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise MissingApiKeyError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key "
            "(https://aistudio.google.com/apikey)."
        )
    return key


def default_model() -> str:
    load_dotenv()
    return os.environ.get("GEMINI_TTS_MODEL", "").strip() or DEFAULT_MODEL


def _status_code(exc: BaseException) -> int | None:
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


def _is_auth_error(exc: BaseException, status: int | None) -> bool:
    if status in (401, 403):
        return True
    return status == 400 and any(h in str(exc).lower() for h in AUTH_HINTS)


def _is_transient_transport_error(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TransportError, TimeoutError, ConnectionError)):
        return True
    return type(exc).__name__ == "NoResponseError"


def _get(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _sample_rate_from_mime(mime_type: str, fallback: int) -> int:
    match = re.search(r"rate=(\d+)", mime_type or "")
    return int(match.group(1)) if match else fallback


class TTSClient:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        *,
        client: Any | None = None,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
        on_retry: Callable[[int, float, BaseException], None] | None = None,
    ) -> None:
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self._client = client
        self.model = model
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._sleep = sleep
        self._on_retry = on_retry

    def _backoff(self, attempt: int) -> float:
        delay = min(self.max_delay, self.base_delay * (2**attempt))
        return delay + random.uniform(0, delay * 0.25)

    def _call_with_retry(self, func: Callable[[], Any]) -> Any:
        attempt = 0
        while True:
            try:
                return func()
            except Exception as exc:
                status = _status_code(exc)
                if _is_auth_error(exc, status):
                    raise InvalidApiKeyError(
                        "The Gemini API rejected the key (invalid or missing permissions). "
                        "Check GEMINI_API_KEY in your .env file."
                    ) from exc
                retryable = status in RETRYABLE_STATUS or (
                    status is None and _is_transient_transport_error(exc)
                )
                if not retryable:
                    raise TTSError(f"Gemini API error ({status or type(exc).__name__}): {exc}") from exc
                if attempt >= self.max_retries:
                    raise RetriesExhaustedError(
                        f"Gave up after {attempt + 1} attempts: {exc}"
                    ) from exc
                delay = self._backoff(attempt)
                if self._on_retry:
                    self._on_retry(attempt + 1, delay, exc)
                self._sleep(delay)
                attempt += 1

    def synthesize(self, text: str, voice: str, style: str = "", language: str | None = None) -> TTSAudio:
        content: dict[str, Any] = {"type": "text", "text": text}
        if style:
            content["annotations"] = [{"type": "speech_metadata", "style": style}]
        speech_config: dict[str, Any] = {"voice": voice}
        if language:
            speech_config["language"] = language

        def call() -> Any:
            return self._client.interactions.create(
                model=self.model,
                input=[{"type": "user_input", "content": [content]}],
                response_format={
                    "type": "audio",
                    "mime_type": API_MIME_TYPE,
                    "sample_rate": API_SAMPLE_RATE,
                },
                generation_config={"speech_config": [speech_config]},
            )

        interaction = self._call_with_retry(call)
        output_audio = _get(interaction, "output_audio")
        data = _get(output_audio, "data") if output_audio is not None else None
        if not data:
            raise TTSError("The API response contained no audio.")
        mime_type = _get(output_audio, "mime_type") or API_MIME_TYPE
        audio_bytes = base64.b64decode(data) if isinstance(data, str) else bytes(data)
        return TTSAudio(
            data=audio_bytes,
            mime_type=mime_type,
            sample_rate=_sample_rate_from_mime(mime_type, API_SAMPLE_RATE),
        )

    def list_voices(self, language_code: str | None = None) -> list[dict[str, str]]:
        """List prebuilt voices from the API (all pages)."""
        voices: list[dict[str, str]] = []
        page_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {"type_": ["prebuilt"], "page_size": 100}
            if language_code:
                kwargs["language_code"] = [language_code]
            if page_token:
                kwargs["page_token"] = page_token
            response = self._call_with_retry(lambda: self._client.voices.list(**kwargs))
            for voice in _get(response, "voices") or []:
                voices.append(
                    {
                        "name": _get(voice, "id") or _get(voice, "display_name") or "",
                        "description": _get(voice, "description") or "",
                        "gender": _get(voice, "gender") or "",
                        "language": _get(voice, "language_code") or "",
                    }
                )
            page_token = _get(response, "next_page_token")
            if not page_token:
                return voices
