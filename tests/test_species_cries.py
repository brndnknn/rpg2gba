"""Tests for `rpg2gba.species_converter.cries` (W4, the cry converter).

Per CLAUDE.md §4.6: a synthetic round-trip test, an explicit pin on the
16-bit-signed -> 8-bit-unsigned sign convention (the classic silent bug in
this kind of conversion), an edge test for the stereo downmix, and a
structural test over the real six starter cries that skips cleanly without
`RPG2GBA_URANIUM_SRC`.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from rpg2gba.species_converter import cries
from rpg2gba.species_converter.common import (
    CRY_CHANNELS,
    CRY_SAMPLE_RATE,
    CRY_SAMPLE_WIDTH,
    STARTER_SPECIES,
)


def _write_pcm16_wav(path: Path, samples: np.ndarray, rate: int, channels: int) -> None:
    """Write int16 PCM samples (shape (n, channels) or (n,) for mono) to a WAV."""
    interleaved = samples.reshape(-1).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(interleaved.tobytes())


def _sine_int16(freq: float, duration_s: float, rate: int, amplitude: float = 0.8) -> np.ndarray:
    t = np.arange(int(duration_s * rate)) / rate
    wave_f = amplitude * np.sin(2 * np.pi * freq * t)
    return (wave_f * 32767).astype("<i2")


# --- 1. Synthetic normalization round-trip --------------------------------


def test_synthetic_tone_round_trip(tmp_path: Path) -> None:
    """A clean tone at a non-target rate should come out mono/target-rate/
    8-bit, with duration close to the (untrimmed, since it's all signal)
    input duration."""
    source_rate = 8000
    duration_s = 0.5
    tone = _sine_int16(440.0, duration_s, source_rate)
    src_path = tmp_path / "tone.wav"
    _write_pcm16_wav(src_path, tone, source_rate, channels=1)

    rate, channels, width, data = cries.read_wav_as_float(src_path)
    assert rate == source_rate
    assert channels == 1
    assert width == 2

    pcm8, metrics = cries._process_pcm(rate, channels, data)

    assert pcm8.dtype == np.uint8
    out_duration = len(pcm8) / CRY_SAMPLE_RATE
    # A full-amplitude sine has no head/tail silence to trim, so output
    # duration should track the source duration closely.
    assert out_duration == pytest.approx(duration_s, abs=0.01)
    assert metrics["silence_trimmed_start_s"] < 0.01
    assert metrics["silence_trimmed_end_s"] < 0.01
    # Should be normalized close to full scale without clipping every sample.
    assert 0.8 <= metrics["peak_amplitude"] <= 1.0

    out_path = tmp_path / "tone_out.wav"
    cries.write_mono8_wav(out_path, pcm8, CRY_SAMPLE_RATE)
    with wave.open(str(out_path), "rb") as w:
        assert w.getnchannels() == CRY_CHANNELS == 1
        assert w.getframerate() == CRY_SAMPLE_RATE
        assert w.getsampwidth() == CRY_SAMPLE_WIDTH == 1


def test_resample_linear_preserves_duration() -> None:
    samples = np.linspace(-1, 1, 4410)  # 0.4s @ 11025 Hz
    out = cries.resample_linear(samples, source_rate=11025, target_rate=CRY_SAMPLE_RATE)
    expected_len = round(0.4 * CRY_SAMPLE_RATE)
    assert abs(len(out) - expected_len) <= 1


# --- 2. Pin the 16-bit-signed -> 8-bit-unsigned sign convention -----------


def test_silence_maps_to_128_not_0() -> None:
    """The classic bug: silence must encode as ~128 (unsigned mid-point),
    not 0. If this ever regresses, the cry becomes a burst of garbage."""
    result = cries.float_to_uint8_pcm(np.array([0.0]))
    assert result[0] == 128


def test_full_scale_pcm16_signed_to_pcm8_unsigned_via_pipeline() -> None:
    """Feed a signal containing full-positive, full-negative, and silent
    16-bit samples through the real decode path and check the 8-bit
    unsigned output lands at the correct ends/midpoint of its range."""
    rate = CRY_SAMPLE_RATE  # avoid resampling so indices are traceable
    raw_int16 = np.array([0, 32767, -32768, 0], dtype="<i2")
    _, _, _, data = cries.read_wav_as_float(_roundtrip_wav_path(raw_int16, rate))
    mono = cries.downmix_to_mono(data)

    # Bypass trim/normalize (designed for real audio, not this 4-sample
    # synthetic edge case) to isolate the quantization step itself.
    pcm8 = cries.float_to_uint8_pcm(mono)

    assert pcm8[0] == 128  # silence -> mid-point, not 0
    assert pcm8[3] == 128
    assert pcm8[1] >= 250  # full positive -> near 255
    assert pcm8[2] <= 5  # full negative -> near 0, but via the 128 bias


def _roundtrip_wav_path(raw_int16: np.ndarray, rate: int) -> Path:
    import tempfile

    tmp_dir = Path(tempfile.mkdtemp())
    path = tmp_dir / "edge.wav"
    _write_pcm16_wav(path, raw_int16, rate, channels=1)
    return path


def test_normalize_peak_rejects_near_silent_clip() -> None:
    with pytest.raises(ValueError):
        cries.normalize_peak(np.array([1e-6, -1e-6, 0.0]))


def test_trim_silence_rejects_all_silent_clip() -> None:
    with pytest.raises(ValueError):
        cries.trim_silence(np.zeros(100), rate=CRY_SAMPLE_RATE)


# --- 3. Stereo downmix edge test (species 003's case) ---------------------


def test_stereo_downmix_averages_channels() -> None:
    left = np.array([1.0, -1.0, 0.5])
    right = np.array([-1.0, 1.0, 0.5])
    stereo = np.stack([left, right], axis=1)
    mono = cries.downmix_to_mono(stereo)
    assert mono.shape == (3,)
    np.testing.assert_allclose(mono, [0.0, 0.0, 0.5])


def test_stereo_wav_decodes_and_downmixes(tmp_path: Path) -> None:
    rate = 44100
    duration_s = 0.2
    left = _sine_int16(440.0, duration_s, rate)
    right = _sine_int16(440.0, duration_s, rate, amplitude=0.0)  # silent right channel
    interleaved = np.empty(left.size * 2, dtype="<i2")
    interleaved[0::2] = left
    interleaved[1::2] = right
    path = tmp_path / "stereo.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(interleaved.tobytes())

    out_rate, channels, width, data = cries.read_wav_as_float(path)
    assert channels == 2
    assert data.shape == (len(left), 2)
    mono = cries.downmix_to_mono(data)
    # Averaging a full-amplitude left with a silent right halves the peak.
    assert np.max(np.abs(mono)) == pytest.approx(0.8 / 2, abs=0.01)


# --- 4. Structural test over the real six starter cries -------------------


@pytest.mark.phase2
def test_real_starter_cries_convert_cleanly(tmp_path: Path, uranium_data: Path) -> None:
    uranium_src = uranium_data.parent  # uranium_data fixture points at .../Data
    results = cries.convert_starter_cries(uranium_src, tmp_path, species=STARTER_SPECIES)

    assert len(results) == len(STARTER_SPECIES)
    sidecar_path = tmp_path / cries.SIDECAR_NAME
    assert sidecar_path.is_file()

    for result in results:
        assert result.output_path.is_file()
        with wave.open(str(result.output_path), "rb") as w:
            assert w.getnchannels() == CRY_CHANNELS == 1
            assert w.getframerate() == CRY_SAMPLE_RATE == 10512
            assert w.getsampwidth() == CRY_SAMPLE_WIDTH == 1
            n_frames = w.getnframes()
            raw = w.readframes(n_frames)
        assert n_frames > 0
        pcm = np.frombuffer(raw, dtype=np.uint8)
        # Non-silent: some sample must deviate meaningfully from the 128
        # midpoint (guards against a pipeline bug that emits flat silence).
        assert np.max(np.abs(pcm.astype(np.int16) - 128)) > 20
        assert result.output_duration_s > 0.05  # sane, non-degenerate duration
