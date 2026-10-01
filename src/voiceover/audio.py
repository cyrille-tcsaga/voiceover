"""Audio post-processing: decode, resample, trim, loudness-normalize, write."""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from math import gcd
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy.signal import resample_poly

TARGET_SAMPLE_RATE = 48_000
TARGET_LUFS = -16.0
PEAK_CEILING_DBFS = -1.0
SILENCE_PADDING_S = 0.15
# Frames quieter than (peak - SILENCE_RANGE_DB) or SILENCE_FLOOR_DBFS count as silence.
SILENCE_RANGE_DB = 40.0
SILENCE_FLOOR_DBFS = -60.0
FRAME_S = 0.010


class AudioError(Exception):
    pass


@dataclass(frozen=True)
class ProcessedAudio:
    samples: np.ndarray  # float32 mono in [-1, 1]
    sample_rate: int
    loudness_lufs: float | None
    peak_dbfs: float

    @property
    def duration_s(self) -> float:
        return len(self.samples) / self.sample_rate


def to_dbfs(value: float) -> float:
    return float(20 * np.log10(value)) if value > 0 else float("-inf")


def decode_api_audio(data: bytes, sample_rate: int) -> tuple[np.ndarray, int]:
    """Decode API output (WAV container or raw 16-bit LE PCM) to float32 mono."""
    if not data:
        raise AudioError("empty audio payload")
    if data[:4] == b"RIFF":
        samples, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
        return samples.mean(axis=1).astype(np.float32), int(sr)
    if len(data) % 2:
        data = data[:-1]
    pcm = np.frombuffer(data, dtype="<i2")
    return (pcm.astype(np.float32) / 32768.0), sample_rate


def resample(samples: np.ndarray, sr_in: int, sr_out: int = TARGET_SAMPLE_RATE) -> np.ndarray:
    if sr_in == sr_out:
        return samples.astype(np.float32)
    divisor = gcd(sr_in, sr_out)
    return resample_poly(samples, sr_out // divisor, sr_in // divisor).astype(np.float32)


def trim_silence(
    samples: np.ndarray, sample_rate: int, padding_s: float = SILENCE_PADDING_S
) -> np.ndarray:
    """Remove leading/trailing silence, keeping `padding_s` of margin on each side."""
    if samples.size == 0:
        return samples
    frame = max(1, int(sample_rate * FRAME_S))
    n_frames = int(np.ceil(samples.size / frame))
    padded = np.zeros(n_frames * frame, dtype=np.float32)
    padded[: samples.size] = samples
    rms = np.sqrt(np.mean(padded.reshape(n_frames, frame) ** 2, axis=1))
    peak = float(np.max(np.abs(samples)))
    if peak <= 0:
        return samples
    threshold_db = max(SILENCE_FLOOR_DBFS, to_dbfs(peak) - SILENCE_RANGE_DB)
    threshold = 10 ** (threshold_db / 20)
    voiced = np.nonzero(rms > threshold)[0]
    if voiced.size == 0:
        return samples
    pad = int(round(padding_s * sample_rate))
    start = max(0, voiced[0] * frame - pad)
    end = min(samples.size, (voiced[-1] + 1) * frame + pad)
    return samples[start:end]


def measure_loudness(samples: np.ndarray, sample_rate: int) -> float | None:
    """Integrated loudness in LUFS, or None if the clip is too short/silent."""
    meter = pyln.Meter(sample_rate)
    if samples.size < int(meter.block_size * sample_rate):
        return None
    loudness = float(meter.integrated_loudness(samples.astype(np.float64)))
    return loudness if np.isfinite(loudness) else None


def normalize_loudness(
    samples: np.ndarray,
    sample_rate: int,
    target_lufs: float = TARGET_LUFS,
    peak_ceiling_dbfs: float = PEAK_CEILING_DBFS,
) -> np.ndarray:
    """Gain to `target_lufs`, then scale down if the sample peak exceeds the ceiling."""
    loudness = measure_loudness(samples, sample_rate)
    out = samples.astype(np.float64)
    if loudness is not None:
        out = out * 10 ** ((target_lufs - loudness) / 20)
    ceiling = 10 ** (peak_ceiling_dbfs / 20)
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    if peak > ceiling:
        out = out * (ceiling / peak)
    return out.astype(np.float32)


def process(data: bytes, sample_rate: int) -> ProcessedAudio:
    samples, sr = decode_api_audio(data, sample_rate)
    samples = resample(samples, sr, TARGET_SAMPLE_RATE)
    samples = trim_silence(samples, TARGET_SAMPLE_RATE)
    samples = normalize_loudness(samples, TARGET_SAMPLE_RATE)
    return analyze(samples, TARGET_SAMPLE_RATE)


def analyze(samples: np.ndarray, sample_rate: int) -> ProcessedAudio:
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    return ProcessedAudio(
        samples=samples,
        sample_rate=sample_rate,
        loudness_lufs=measure_loudness(samples, sample_rate),
        peak_dbfs=to_dbfs(peak),
    )


def write_wav(path: Path, samples: np.ndarray, sample_rate: int = TARGET_SAMPLE_RATE) -> None:
    """Write a 16-bit PCM mono WAV atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    sf.write(tmp, np.clip(samples, -1.0, 1.0), sample_rate, subtype="PCM_16", format="WAV")
    os.replace(tmp, path)


def read_wav(path: Path) -> ProcessedAudio:
    samples, sr = sf.read(path, dtype="float32", always_2d=True)
    return analyze(samples.mean(axis=1).astype(np.float32), int(sr))
