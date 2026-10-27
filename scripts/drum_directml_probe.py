"""Isolated trained DrumSep CPU/AMD comparison; never changes the library."""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=64)
    parser.add_argument("--start", type=float, default=70)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    import numpy as np
    import soundfile as sf
    import torch

    from app.core.amd_directml import select_device
    from app.core.drum_model import load_model

    torch.set_num_threads(4)
    device, name = select_device()
    code = ROOT / ".venv/Lib/site-packages/audio_separator/separator/uvr_lib_v5/tfc_tdf_v3.py"
    directory = ROOT / "data/models/audio-separator"
    model, config = load_model(directory, code, torch.device("cpu"))
    samples = config.audio.hop_length * (args.frames - 1)
    data, rate = sf.read(
        args.input, start=round(44100 * args.start), frames=samples, always_2d=True, dtype="float32"
    )
    assert rate == 44100 and len(data) == samples
    x = torch.from_numpy(data.T.copy()).unsqueeze(0)
    start = time.monotonic()
    with torch.no_grad():
        cpu = model(x).numpy()
    cpu_elapsed = time.monotonic() - start
    model.to(device)
    model.device = device
    model.stft.device = device
    start = time.monotonic()
    results = []
    with torch.no_grad():
        for i in range(4):
            value = model(x.to(device)).cpu().numpy()
            error = float(np.max(np.abs(value - cpu)))
            rmse = float(np.sqrt(np.mean((value - cpu).astype(np.float64) ** 2)))
            snr = float(
                20 * np.log10(np.sqrt(np.mean(cpu.astype(np.float64) ** 2)) / max(rmse, 1e-20))
            )
            results.append(
                {
                    "iteration": i,
                    "max_error": error,
                    "snr_db": snr,
                    "finite": bool(np.isfinite(value).all()),
                }
            )
            print(json.dumps(results[-1]), flush=True)
            gc.collect()
    report = {
        "adapter": name,
        "frames": args.frames,
        "samples": samples,
        "cpu_seconds": cpu_elapsed,
        "gpu_seconds": time.monotonic() - start,
        "results": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
