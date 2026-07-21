"""Uranium species cry -> pokeemerald-expansion cry WAV converter (W4).

Converts the six starter-line cries (`Audio/SE/NNNCry.wav`) into the exact
WAV format the vendored engine's audio build rule expects. The build rule
(`engine/audio_rules.mk` ~line 22) runs `wav2agb -b -c -l 1 --no-pad`
directly against `.wav` files, so this module's job stops at emitting a
well-formed WAV — it does not touch the engine tree and does not invoke
wav2agb itself.

House norm (measured 2026-07-18 from `engine/sound/direct_sound_samples/
cries/{bulbasaur,charmander,squirtle,pikachu}.wav`, all four in agreement):
mono, 10512 Hz, 8-bit *unsigned* PCM. This matches `common.CRY_SAMPLE_RATE`
/ `CRY_CHANNELS` / `CRY_SAMPLE_WIDTH` exactly — no discrepancy found, so
those constants are used as-is rather than questioned.

Source cries (measured the same day from `$RPG2GBA_URANIUM_SRC/Audio/SE/
00NCry.wav`, N in 1..6) are PCM16, mono except species 3 (RAPTORCH, stereo),
at three different sample rates depending on species: 8000, 11025, 44100 Hz.
None of the sources are already at the 10512 Hz target, so every cry goes
through the resampler.

Processing pipeline (`_process_pcm`):
  1. decode PCM to float64 in [-1, 1]
  2. downmix stereo -> mono (plain channel average)
  3. anti-alias low-pass (only when downsampling) + linear-interpolation
     resample to `CRY_SAMPLE_RATE`
  4. trim leading/trailing silence
  5. normalize peak amplitude without clipping
  6. quantize to 8-bit unsigned PCM (128-biased, NOT a naive truncation --
     that's the classic bug that makes silence encode as 0 instead of 128
     and turns the whole clip into a click of garbage)
"""

from __future__ import annotations

import json
import logging
import wave
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from rpg2gba.species_converter.common import (
    CRY_CHANNELS,
    CRY_SAMPLE_RATE,
    CRY_SAMPLE_WIDTH,
    STARTER_SPECIES,
    SpeciesSpec,
    uranium_cry,
)

logger = logging.getLogger(__name__)

#: Amplitude (relative to full scale, [0, 1]) below which a sample is
#: considered silence for head/tail trimming. -34 dBFS: quiet enough that
#: source noise floor and fade-in/out tails fall under it, loud enough that
#: it doesn't clip off the actual onset transient of a cry.
SILENCE_THRESHOLD = 0.02

#: Padding kept on either side of the trimmed region so the cut doesn't
#: produce an audible click at the new clip boundary.
SILENCE_TRIM_PAD_MS = 3.0

#: Peak amplitude (relative to full scale) the normalization step targets.
#: Slightly under 1.0 so linear-interpolation resampling overshoot (which
#: can exceed the original peak by a small amount between samples) doesn't
#: clip when quantized to 8-bit.
NORMALIZE_TARGET_PEAK = 0.98

#: Below this peak, a clip is treated as effectively silent and normalizing
#: it would just amplify noise -- fail loud instead of producing a bogus
#: full-scale "cry".
MIN_MEANINGFUL_PEAK = 1e-4

SIDECAR_NAME = "cries.json"


@dataclass(frozen=True)
class CryConversionResult:
    """Per-species record of a cry conversion, also the sidecar JSON schema."""

    internal_name: str
    source_path: Path
    source_rate: int
    source_channels: int
    source_sample_width: int
    output_path: Path
    output_duration_s: float
    peak_amplitude: float
    silence_trimmed_start_s: float
    silence_trimmed_end_s: float

    def to_json_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["source_path"] = str(self.source_path)
        d["output_path"] = str(self.output_path)
        return d


# --- WAV I/O -----------------------------------------------------------


def read_wav_as_float(path: Path) -> tuple[int, int, int, np.ndarray]:
    """Decode a WAV file to float64 samples in [-1, 1].

    Returns `(frame_rate, channels, sample_width_bytes, data)` where `data`
    has shape `(n_frames, channels)`. Only 8-bit unsigned and 16-bit signed
    PCM are handled (the only widths this pipeline's inputs ever use); any
    other width fails loud rather than guessing a decode.
    """
    with wave.open(str(path), "rb") as w:
        channels = w.getnchannels()
        rate = w.getframerate()
        width = w.getsampwidth()
        n_frames = w.getnframes()
        raw = w.readframes(n_frames)

    if width == 2:
        ints = np.frombuffer(raw, dtype="<i2").astype(np.float64)
        floats = ints / 32768.0
    elif width == 1:
        ints = np.frombuffer(raw, dtype=np.uint8).astype(np.float64)
        floats = (ints - 128.0) / 128.0
    else:
        raise ValueError(f"{path}: unsupported PCM sample width {width} bytes")

    data = floats.reshape(-1, channels)
    return rate, channels, width, data


def write_mono8_wav(path: Path, samples_u8: np.ndarray, rate: int) -> None:
    """Write mono 8-bit unsigned PCM samples to `path` (the house norm)."""
    if samples_u8.dtype != np.uint8:
        raise TypeError(f"expected uint8 samples, got {samples_u8.dtype}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(CRY_CHANNELS)
        w.setsampwidth(CRY_SAMPLE_WIDTH)
        w.setframerate(rate)
        w.writeframes(samples_u8.tobytes())


# --- Pipeline stages -----------------------------------------------------


def downmix_to_mono(data: np.ndarray) -> np.ndarray:
    """Average all channels down to one. No-op if already mono."""
    if data.ndim == 1:
        return data
    if data.shape[1] == 1:
        return data[:, 0]
    return data.mean(axis=1)


def _num_lowpass_taps(source_rate: int, target_rate: int) -> int:
    """Heuristic FIR tap count, scaled to the downsample ratio.

    More taps -> sharper transition band -> better stopband attenuation,
    at proportionally more compute. Clamped to a sane range; this pipeline
    only ever sees ratios up to ~4.2 (44100 -> 10512).
    """
    ratio = source_rate / target_rate
    taps = int(round(8 * ratio)) | 1  # force odd (symmetric kernel)
    return max(15, min(taps, 127))


def lowpass_filter(samples: np.ndarray, source_rate: int, cutoff_rate: int) -> np.ndarray:
    """Windowed-sinc FIR low-pass, cutoff at `cutoff_rate`'s Nyquist.

    Only meant to run ahead of downsampling, to knock down energy above the
    target Nyquist before decimating so it doesn't fold back as aliasing.
    Uses a Hann-windowed sinc kernel (simple, stable, no ringing surprises)
    normalized to unit DC gain.
    """
    if cutoff_rate >= source_rate:
        return samples
    num_taps = _num_lowpass_taps(source_rate, cutoff_rate)
    # Normalized cutoff: fraction of source Nyquist represented by the
    # target Nyquist frequency.
    wc = cutoff_rate / source_rate
    n = np.arange(num_taps) - (num_taps - 1) / 2
    kernel = 2 * wc * np.sinc(2 * wc * n)
    kernel *= np.hanning(num_taps)
    kernel /= kernel.sum()
    return np.convolve(samples, kernel, mode="same")


def resample_linear(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """Linearly-interpolated resample from `source_rate` to `target_rate`.

    None of the source rates (8000/11025/44100) divide evenly into the
    10512 Hz target, so an integer up/down-sample ratio doesn't exist.
    Linear interpolation is the standard low-cost choice for this and is
    adequate for short percussive clips like cries; the caller is expected
    to have already low-passed the signal when downsampling (see
    `lowpass_filter`) so this step isn't also responsible for anti-aliasing.
    """
    if source_rate == target_rate:
        return samples.copy()
    if len(samples) == 0:
        return samples.copy()
    duration = len(samples) / source_rate
    n_out = max(1, round(duration * target_rate))
    src_times = np.arange(len(samples)) / source_rate
    dst_times = np.arange(n_out) / target_rate
    return np.interp(dst_times, src_times, samples)


def trim_silence(
    samples: np.ndarray,
    rate: int,
    threshold: float = SILENCE_THRESHOLD,
    pad_ms: float = SILENCE_TRIM_PAD_MS,
) -> tuple[np.ndarray, float, float]:
    """Trim leading/trailing silence, keeping a small pad to avoid a click.

    Returns `(trimmed_samples, seconds_trimmed_from_start, seconds_trimmed_
    from_end)`. Fails loud if the whole clip is under threshold -- that's a
    broken source cry, not something to silently pass through as an empty
    WAV.
    """
    above = np.where(np.abs(samples) > threshold)[0]
    if above.size == 0:
        raise ValueError("cry is silent throughout (no sample exceeds SILENCE_THRESHOLD)")
    pad = int(round(rate * pad_ms / 1000.0))
    start = max(0, int(above[0]) - pad)
    end = min(len(samples), int(above[-1]) + 1 + pad)
    trimmed_start_s = start / rate
    trimmed_end_s = (len(samples) - end) / rate
    return samples[start:end], trimmed_start_s, trimmed_end_s


def normalize_peak(samples: np.ndarray, target_peak: float = NORMALIZE_TARGET_PEAK) -> np.ndarray:
    """Scale so the loudest sample hits `target_peak`, never clipping."""
    peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
    if peak < MIN_MEANINGFUL_PEAK:
        raise ValueError(
            f"cry peak amplitude {peak!r} is below MIN_MEANINGFUL_PEAK "
            f"({MIN_MEANINGFUL_PEAK}) -- refusing to amplify what looks like noise"
        )
    return samples * (target_peak / peak)


def float_to_uint8_pcm(samples: np.ndarray) -> np.ndarray:
    """Quantize float64 samples in [-1, 1] to 8-bit *unsigned* PCM.

    8-bit PCM WAV is unsigned with a 128 bias (0 = full negative, 128 =
    silence, 255 = full positive) -- unlike 16-bit PCM, which is signed.
    Getting this backwards (e.g. writing signed bytes, or truncating a
    16-bit sample's high byte without the +128 bias) makes silence encode
    as 0 and turns the clip into a burst of garbage rather than a cry.
    """
    scaled = np.round(samples * 127.0) + 128.0
    clipped = np.clip(scaled, 0, 255)
    return clipped.astype(np.uint8)


def _process_pcm(rate: int, channels: int, data: np.ndarray) -> tuple[np.ndarray, dict[str, float]]:
    """Run the full pipeline (steps 2-6 of the module docstring) on decoded
    float samples. Returns `(uint8_samples, metrics)` where metrics has
    `peak_amplitude`, `silence_trimmed_start_s`, `silence_trimmed_end_s`.
    """
    mono = downmix_to_mono(data)
    if rate > CRY_SAMPLE_RATE:
        mono = lowpass_filter(mono, rate, CRY_SAMPLE_RATE)
    resampled = resample_linear(mono, rate, CRY_SAMPLE_RATE)
    trimmed, trim_start_s, trim_end_s = trim_silence(resampled, CRY_SAMPLE_RATE)
    normalized = normalize_peak(trimmed)
    pcm8 = float_to_uint8_pcm(normalized)
    peak_amplitude = float(np.max(np.abs(pcm8.astype(np.int16) - 128))) / 127.0
    metrics = {
        "peak_amplitude": peak_amplitude,
        "silence_trimmed_start_s": trim_start_s,
        "silence_trimmed_end_s": trim_end_s,
    }
    return pcm8, metrics


# --- Per-species / batch entry points ------------------------------------


def convert_species_cry(
    uranium_src: Path, spec: SpeciesSpec, output_dir: Path
) -> CryConversionResult:
    """Convert one species' cry and write it to `output_dir/<name>.wav`."""
    source_path = uranium_cry(uranium_src, spec)
    rate, channels, width, data = read_wav_as_float(source_path)
    pcm8, metrics = _process_pcm(rate, channels, data)

    output_path = output_dir / f"{spec.internal_name.lower()}.wav"
    write_mono8_wav(output_path, pcm8, CRY_SAMPLE_RATE)

    duration_s = len(pcm8) / CRY_SAMPLE_RATE
    logger.info(
        "%s: %d Hz/%dch/%d-byte source -> %.3fs mono/%d Hz/8-bit, peak=%.2f, "
        "trimmed %.3fs/%.3fs",
        spec.internal_name,
        rate,
        channels,
        width,
        duration_s,
        CRY_SAMPLE_RATE,
        metrics["peak_amplitude"],
        metrics["silence_trimmed_start_s"],
        metrics["silence_trimmed_end_s"],
    )

    return CryConversionResult(
        internal_name=spec.internal_name,
        source_path=source_path,
        source_rate=rate,
        source_channels=channels,
        source_sample_width=width,
        output_path=output_path,
        output_duration_s=duration_s,
        peak_amplitude=metrics["peak_amplitude"],
        silence_trimmed_start_s=metrics["silence_trimmed_start_s"],
        silence_trimmed_end_s=metrics["silence_trimmed_end_s"],
    )


def convert_starter_cries(
    uranium_src: Path,
    output_dir: Path,
    species: Sequence[SpeciesSpec] = STARTER_SPECIES,
) -> list[CryConversionResult]:
    """Convert every species in `species` and write the JSON sidecar.

    The sidecar (`<output_dir>/cries.json`) is read by the staging emitter
    (W1); this module only ever writes it, never the emitter's own
    `species_manifest.json`.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results = [convert_species_cry(uranium_src, spec, output_dir) for spec in species]

    sidecar_path = output_dir / SIDECAR_NAME
    sidecar_path.write_text(
        json.dumps([r.to_json_dict() for r in results], indent=2) + "\n",
        encoding="utf-8",
    )
    return results


__all__ = [
    "CryConversionResult",
    "SILENCE_THRESHOLD",
    "SILENCE_TRIM_PAD_MS",
    "NORMALIZE_TARGET_PEAK",
    "read_wav_as_float",
    "write_mono8_wav",
    "downmix_to_mono",
    "lowpass_filter",
    "resample_linear",
    "trim_silence",
    "normalize_peak",
    "float_to_uint8_pcm",
    "convert_species_cry",
    "convert_starter_cries",
]
