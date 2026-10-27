"""Offline AMD guitar extraction for whole songs, with exact stereo remainder."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROMPTS = {
    "lead": "A lead electric guitar playing a melodic solo.",
    "acoustic": "An acoustic guitar being strummed or fingerpicked.",
    "rhythm": "Electric rhythm guitars playing chords and accompaniment.",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--roles", nargs="+", choices=list(PROMPTS), default=list(PROMPTS))
    parser.add_argument("--window", type=float, default=12.0, choices=[3.0, 6.0, 12.0])
    parser.add_argument("--pipeline-progress", action="store_true")
    args = parser.parse_args()
    from app.core.process import arm_parent_watchdog

    arm_parent_watchdog()
    import numpy as np
    import soundfile as sf
    from sam_audio_inference import SAMSession
    from sam_audio_stereo import restore_stereo
    from scipy.signal import resample_poly

    from app.core.guitar_audio import add_window, finish_windows, windows

    started = time.monotonic()

    def emit(**fields):
        if args.pipeline_progress:
            percent = fields.get("percent")
            record = {
                "fraction": percent / 100 if percent is not None else None,
                "device": "directml",
                "phase": fields.get("phase"),
                "role": fields.get("role"),
                "completed": fields.get("completed_chunks"),
                "total": fields.get("total_chunks"),
                "pass": fields.get("role_index"),
                "passes": fields.get("roles"),
            }
            print("@@PROGRESS@@" + json.dumps(record), file=sys.stderr, flush=True)
        print(
            "@@GUITAR@@" + json.dumps({"elapsed": time.monotonic() - started, **fields}), flush=True
        )

    args.output.mkdir(parents=True, exist_ok=False)
    emit(phase="loading", completed_chunks=0, percent=0)
    with args.input.open("rb") as stream:
        fingerprint = hashlib.file_digest(stream, "sha256").hexdigest()
    original, rate = sf.read(args.input, dtype="float32", always_2d=True)
    if (
        original.shape[1] not in (1, 2)
        or len(original) < rate * 0.12
        or not np.isfinite(original).all()
    ):
        raise ValueError("Invalid guitar audio")
    session = SAMSession(args.source, os.environ.get("STEMDECK_DIRECTML_ADAPTER", "RX 6600M"))
    emit(phase="ready", adapter=session.adapter)
    remaining = original.copy()
    roles = [role for role in PROMPTS if role in args.roles]
    names, timings = [], []
    for role_index, role in enumerate(roles):
        size = args.window
        while True:
            overlap = min(2.0, size / 4)
            intervals = windows(len(original), rate, size, overlap)
            accumulator = np.zeros_like(original)
            weights = np.zeros(len(original), dtype=np.float32)
            memory_failure = False
            for index, (begin, end) in enumerate(intervals):
                baseline = {
                    "role": role,
                    "role_index": role_index + 1,
                    "roles": len(roles),
                    "chunk": index + 1,
                    "chunks": len(intervals),
                    "completed_chunks": role_index * len(intervals) + index,
                    "total_chunks": len(roles) * len(intervals),
                    "percent": 100 * (role_index + index / len(intervals)) / len(roles),
                }

                def progress(_baseline=baseline, **fields):
                    emit(**{**_baseline, **fields})

                part = remaining[begin:end]
                mono = part.mean(axis=1)
                factor = math.gcd(rate, 48000)
                mono = resample_poly(mono, 48000 // factor, rate // factor).astype(np.float32)
                progress(phase="starting")
                failed = False
                try:
                    target, residual = session.infer(
                        mono, PROMPTS[role], seed=42 + begin, progress=progress
                    )
                except RuntimeError as error:
                    if "memory" not in str(error).casefold() or size <= 3:
                        raise
                    failed = True
                if failed:
                    size /= 2
                    emit(phase="smaller_window", window_seconds=size, role=role)
                    memory_failure = True
                    break
                selected, _, _ = restore_stereo(part, rate, target, residual)
                add_window(
                    accumulator,
                    weights,
                    selected,
                    begin,
                    round(overlap * rate),
                    first=index == 0,
                    last=index == len(intervals) - 1,
                )
                progress(
                    phase="chunk_done",
                    completed_chunks=baseline["completed_chunks"] + 1,
                    percent=100 * (role_index + (index + 1) / len(intervals)) / len(roles),
                )
            if not memory_failure:
                break
        selected = finish_windows(accumulator, weights)
        name = f"guitar_{role}"
        sf.write(args.output / f"{name}.wav", selected, rate, subtype="FLOAT")
        remaining = remaining - selected
        names.append(name)
        timings.append({"role": role, "window_seconds": size, "chunks": len(intervals)})
    # Calculate the final residue from the published targets in double precision.
    total = np.zeros_like(original, dtype=np.float64)
    for name in names:
        total += sf.read(args.output / f"{name}.wav", always_2d=True)[0]
    remaining = (original.astype(np.float64) - total).astype(np.float32)
    sf.write(args.output / "residual_guitar.wav", remaining, rate, subtype="FLOAT")
    error = float(np.max(np.abs(original.astype(np.float64) - total - remaining)))
    if error > 1e-6:
        raise RuntimeError("Guitar reconstruction did not pass validation")
    receipt = {
        "status": "done",
        "checkpoint_loaded": True,
        "adapter": session.adapter,
        "device": str(session.device),
        "sample_rate": rate,
        "samples": len(original),
        "channels": original.shape[1],
        "names": [*names, "residual_guitar"],
        "roles": roles,
        "prompts": {role: PROMPTS[role] for role in roles},
        "input_sha256": fingerprint,
        "reconstruction_max_abs_error": error,
        "semantic_quality": "estimated",
        "sequential_partition": True,
        "processing": timings,
        "elapsed": time.monotonic() - started,
    }
    (args.output / "result.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    emit(phase="done", percent=100, **{"result": receipt})


if __name__ == "__main__":
    main()
