"""Transfer a SAM mono estimate to the original stereo signal for lab review.

The SAM estimates define a bounded spectral mask. The same real mask is applied
to both original channels, preserving their relative phase per time/frequency
bin. A complementary remainder preserves reconstruction. This is not evidence
that SAM identified a particular guitar role correctly.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy.signal import istft, resample_poly, stft


def _estimate_at_rate(estimate, rate, source_rate, samples):
    estimate = np.asarray(estimate, dtype=np.float64)
    if estimate.ndim != 1 or not np.isfinite(estimate).all():
        raise ValueError("SAM estimates must be finite mono audio")
    if rate != source_rate:
        factor = math.gcd(rate, source_rate)
        estimate = resample_poly(estimate, source_rate // factor, rate // factor)
    if abs(len(estimate) - samples) > 2:
        raise ValueError("SAM estimates and original audio must cover the same time interval")
    return np.pad(estimate[:samples], (0, max(0, samples - len(estimate))))


def restore_stereo(original, sample_rate, target, residual, *, estimate_rate=48000):
    """Return estimated target + exact remainder, in the source sample rate."""
    original = np.asarray(original, dtype=np.float32)
    if original.ndim == 1:
        original = original[:, None]
    if (
        original.ndim != 2
        or original.shape[1] not in (1, 2)
        or original.shape[0] < 2048
        or not np.isfinite(original).all()
    ):
        raise ValueError("Original audio must be finite mono/stereo with at least 2048 samples")
    if sample_rate <= 0 or estimate_rate <= 0:
        raise ValueError("Sample rates must be positive")
    samples = original.shape[0]
    target = _estimate_at_rate(target, estimate_rate, sample_rate, samples)
    residual = _estimate_at_rate(residual, estimate_rate, sample_rate, samples)
    settings = dict(fs=sample_rate, window="hann", nperseg=2048, noverlap=1536)
    _, _, target_spec = stft(target, **settings)
    _, _, residual_spec = stft(residual, **settings)
    target_power = np.abs(target_spec) ** 2
    denominator = target_power + np.abs(residual_spec) ** 2
    mask = np.divide(
        target_power, denominator, out=np.zeros_like(target_power), where=denominator > 1e-24
    )
    mask = np.clip(mask, 0, 1)
    _, _, original_spec = stft(original.astype(np.float64).T, **settings)
    _, selected = istft(original_spec * mask[None], **settings)
    selected = selected[:, :samples].T.astype(np.float32)
    remainder = original - selected
    reconstruction_error = float(np.max(np.abs(original - (selected + remainder))))
    channel_power = float(np.mean(original.astype(np.float64) ** 2))
    mid_power = float(np.mean(original.mean(axis=1, dtype=np.float64) ** 2))
    report = {
        "method": "SAM mono power-ratio mask applied to original channels",
        "neural_inference": False,
        "semantic_quality": "not reviewed",
        "channels": original.shape[1],
        "sample_rate": sample_rate,
        "samples": samples,
        "mask_min": float(mask.min()),
        "mask_max": float(mask.max()),
        "exact_reconstruction_max_error": reconstruction_error,
        "mid_to_channel_power_ratio": mid_power / channel_power if channel_power else 0,
    }
    return selected, remainder, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True, help="A completed SAM probe directory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import soundfile as sf

    receipt = json.loads((args.probe / "report.json").read_text(encoding="utf-8"))
    if receipt.get("status") != "completed" or not receipt.get("checkpoint_loaded"):
        parser.error("A completed probe using the official checkpoint is required")
    with sf.SoundFile(receipt["input"]) as stream:
        stream.seek(round(receipt["start"] * stream.samplerate))
        original = stream.read(
            round(receipt["seconds"] * stream.samplerate), dtype="float32", always_2d=True
        )
        rate = stream.samplerate
    target, estimate_rate = sf.read(args.probe / "target.wav", dtype="float32")
    residual, residual_rate = sf.read(args.probe / "model_residual.wav", dtype="float32")
    if residual_rate != estimate_rate:
        parser.error("Target and residual sample rates must match")
    selected, remainder, report = restore_stereo(
        original, rate, target, residual, estimate_rate=estimate_rate
    )
    args.output.mkdir(parents=True, exist_ok=True)
    for name, audio in (
        ("original_stereo", original),
        ("target_stereo", selected),
        ("remainder_stereo", remainder),
    ):
        sf.write(args.output / f"{name}.wav", audio, rate, subtype="FLOAT")
    report.update(probe=str(args.probe.resolve()), prompt=receipt["prompt"])
    (args.output / "stereo-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
