import io

import numpy as np
import pyloudnorm as pyln
import pytest
import soundfile as sf

from voiceover import audio
from conftest import make_pcm


def test_decode_raw_pcm():
    samples, sr = audio.decode_api_audio(np.array([0, 16384, -32768], dtype="<i2").tobytes(), 24_000)
    assert sr == 24_000
    np.testing.assert_allclose(samples, [0.0, 0.5, -1.0])


def test_decode_wav_container():
    buf = io.BytesIO()
    sf.write(buf, np.zeros(2400, dtype=np.float32), 24_000, format="WAV", subtype="PCM_16")
    samples, sr = audio.decode_api_audio(buf.getvalue(), 16_000)
    assert sr == 24_000
    assert samples.shape == (2400,)


def test_decode_empty_raises():
    with pytest.raises(audio.AudioError):
        audio.decode_api_audio(b"", 24_000)


def test_resample_to_48k():
    out = audio.resample(np.zeros(24_000, dtype=np.float32), 24_000)
    assert out.shape == (48_000,)
    assert out.dtype == np.float32


def test_trim_silence_keeps_padding():
    sr = 48_000
    signal = np.concatenate([np.zeros(sr), 0.3 * np.ones(sr), np.zeros(sr)]).astype(np.float32)
    trimmed = audio.trim_silence(signal, sr)
    expected = 1.0 + 2 * audio.SILENCE_PADDING_S
    assert abs(len(trimmed) / sr - expected) < 0.02


def test_trim_silence_on_pure_silence_is_noop():
    silent = np.zeros(4800, dtype=np.float32)
    assert audio.trim_silence(silent, 48_000).size == 4800


def test_normalize_hits_target_lufs():
    sr = 48_000
    t = np.arange(3 * sr) / sr
    quiet = (0.02 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    out = audio.normalize_loudness(quiet, sr)
    assert pyln.Meter(sr).integrated_loudness(out.astype(np.float64)) == pytest.approx(-16.0, abs=0.1)
    assert np.max(np.abs(out)) <= 10 ** (-1 / 20) + 1e-6


def test_normalize_enforces_peak_ceiling():
    sr = 48_000
    # Sparse loud clicks: reaching -16 LUFS would push peaks far above -1 dBFS.
    signal = np.zeros(3 * sr, dtype=np.float32)
    signal[::4800] = 0.5
    out = audio.normalize_loudness(signal, sr)
    assert audio.to_dbfs(float(np.max(np.abs(out)))) == pytest.approx(-1.0, abs=0.01)


def test_process_full_pipeline_and_write(tmp_path):
    processed = audio.process(make_pcm(lead_s=0.5, tone_s=1.5, tail_s=0.7), 24_000)
    assert processed.sample_rate == 48_000
    assert processed.duration_s == pytest.approx(1.5 + 2 * audio.SILENCE_PADDING_S, abs=0.03)
    assert processed.loudness_lufs == pytest.approx(-16.0, abs=0.2)
    assert processed.peak_dbfs <= -1.0 + 1e-6

    path = tmp_path / "V01.wav"
    audio.write_wav(path, processed.samples)
    info = sf.info(path)
    assert (info.samplerate, info.channels, info.subtype) == (48_000, 1, "PCM_16")
    reread = audio.read_wav(path)
    assert reread.loudness_lufs == pytest.approx(-16.0, abs=0.2)
    assert not list(tmp_path.glob(".*.tmp"))


def test_short_clip_has_no_loudness():
    assert audio.measure_loudness(np.ones(100, dtype=np.float32) * 0.1, 48_000) is None
