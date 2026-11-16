"""Trained DrumSep on AMD: real neural layers on GPU, complex STFT on CPU."""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--architecture", type=Path, required=True)
    args = parser.parse_args()
    from app.core.process import arm_parent_watchdog

    os.environ.setdefault("STEMDECK_PARENT_PID", str(os.getppid()))
    arm_parent_watchdog()
    import numpy as np
    import soundfile as sf
    import torch

    from app.core.amd_directml import select_device
    from app.core.drum_model import PIECES, load_model

    torch.set_num_threads(4)
    started = time.monotonic()
    device, adapter = select_device()

    def report(completed=None, total=None):
        print(
            "@@PROGRESS@@"
            + json.dumps(
                {
                    "fraction": completed / total if total else None,
                    "device": "directml",
                    "completed": completed,
                    "total": total,
                    "pass": 1,
                    "passes": 1,
                }
            ),
            file=sys.stderr,
            flush=True,
        )

    report()
    model, config = load_model(args.models, args.architecture, device)
    if any(parameter.device.type != "privateuseone" for parameter in model.parameters()):
        raise RuntimeError("DrumSep neural parameters are not on AMD")
    data, rate = sf.read(args.input, always_2d=True, dtype="float32")
    if (
        rate != config.audio.sample_rate
        or data.shape[1] != 2
        or not len(data)
        or not np.isfinite(data).all()
    ):
        raise ValueError("DrumSep expects finite stereo audio at its trained sample rate")
    mix = torch.from_numpy(data.T.copy())
    # Match the installed audio-separator MDXC demix: dim_t=256, batch=1, overlap=4.
    size = config.audio.hop_length * (config.inference.dim_t - 1)
    overlap = 4
    hop = size // overlap
    padding = hop - (mix.shape[-1] - size) % hop
    mix = torch.cat([torch.zeros(2, size - hop), mix, torch.zeros(2, padding + size - hop)], 1)
    chunks = mix.unfold(1, size, hop).transpose(0, 1)
    output = torch.zeros(len(PIECES), *mix.shape)
    report(0, len(chunks))
    with torch.no_grad():
        for index, part in enumerate(chunks):
            value = model(part.unsqueeze(0).to(device)).cpu()[0]
            if value.shape != (len(PIECES), 2, size) or not torch.isfinite(value).all():
                raise RuntimeError("DrumSep produced an invalid audio window")
            output[..., index * hop : index * hop + size] += value
            del value
            gc.collect()
            report(index + 1, len(chunks))
    output = output[..., size - hop : -(padding + size - hop)] / overlap
    if output.shape[-1] != len(data):
        raise RuntimeError("DrumSep changed the sample grid")
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in zip(PIECES, output.numpy(), strict=True):
        sf.write(args.output / f"drum_{name}.wav", value.T, rate, subtype="FLOAT")
    receipt = {
        "device": "directml",
        "adapter": adapter,
        "sample_rate": rate,
        "samples": len(data),
        "channels": 2,
        "chunks": len(chunks),
        "segment_frames": config.inference.dim_t,
        "overlap": overlap,
        "elapsed": time.monotonic() - started,
        "neural_cpu_fallback": False,
    }
    (args.output / "drum-device.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt), file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
