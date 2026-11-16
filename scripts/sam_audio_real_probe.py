"""Run a bounded real-music SAM test on AMD, outside the N3LX_Stem service.

Text, codec and diffusion modules run on the selected GPU in separate stages to
limit resident weights. Host copies between stages are explicit in the report.
This is a research command, not a production guitar multitrack feature.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import subprocess
import time
import traceback
import warnings
from pathlib import Path


def run(args, report):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import numpy as np
    import soundfile as sf
    import torch
    import torch_directml
    import torchaudio
    from sam_audio_amd_compat import configure_codec, configure_transformer, directml_t5_compat
    from sam_audio_text_loader import load_text_audio
    from torchdiffeq import odeint

    torch.set_num_threads(4)
    torch.manual_seed(args.seed)
    index = next(
        i
        for i in range(torch_directml.device_count())
        if args.adapter.casefold() in torch_directml.device_name(i).casefold()
    )
    device = torch.device("cpu") if args.cpu_reference else torch_directml.device(index)
    report.update(
        adapter="CPU reference"
        if args.cpu_reference
        else torch_directml.device_name(index).rstrip("\0"),
        device=str(device),
        torch=torch.__version__,
        upstream_revision=subprocess.check_output(
            ["git", "-C", str(args.source), "rev-parse", "HEAD"], text=True
        ).strip(),
    )

    def emit(stage, **fields):
        print(json.dumps({"stage": stage, **fields}), flush=True)

    with sf.SoundFile(args.input) as stream:
        stream.seek(round(args.start * stream.samplerate))
        pcm = stream.read(round(args.seconds * stream.samplerate), dtype="float32", always_2d=True)
        sample_rate = stream.samplerate
    if len(pcm) < sample_rate * 0.12:
        raise ValueError("Test clip is too short or starts after the input ends")
    waveform = torch.from_numpy(pcm.T.copy()).mean(0, keepdim=True)
    if sample_rate != 48000:
        waveform = torchaudio.functional.resample(waveform, sample_rate, 48000)
    report.update(
        input=str(args.input.resolve()),
        start=args.start,
        seconds=waveform.shape[-1] / 48000,
        prompt=args.prompt,
        mono_downmix=True,
        checkpoint_loaded=False,
        stages=[],
    )
    emit("loading_official_weights")
    started = time.perf_counter()
    model, processor, receipt = load_text_audio(args.source, args.weights, args.text_weights)
    report.update(receipt)
    report["load_seconds"] = time.perf_counter() - started
    emit("weights_loaded", **receipt)
    configure_codec(model.audio_codec)
    configure_transformer(model.transformer)
    batch = processor(audios=[waveform], descriptions=[args.prompt])
    dtype = torch.float16 if args.dtype == "float16" else torch.float32
    codec_dtype = torch.float16 if args.codec_dtype == "float16" else torch.float32

    def stage(name, module, operation, precision):
        emit(name, status="started", device=str(device))
        started = time.perf_counter()
        module.to(device=device, dtype=precision)
        with torch.no_grad():
            result = operation()
        # CPU transfers synchronize completion, so timings include all stage work.
        host = tuple(t.cpu() for t in result) if isinstance(result, tuple) else result.cpu()
        record = {
            "stage": name,
            "seconds": time.perf_counter() - started,
            "device": str(next(module.parameters()).device),
            "dtype": str(precision),
        }
        report["stages"].append(record)
        emit(name, status="complete", **{k: v for k, v in record.items() if k != "stage"})
        module.to("cpu")
        gc.collect()
        return host

    with directml_t5_compat():
        text, text_mask = stage(
            "text_encode",
            model.text_encoder,
            lambda: model.text_encoder([args.prompt]),
            torch.float32,
        )
    features = stage(
        "audio_encode",
        model.audio_codec,
        lambda: model._get_audio_features(batch.audios.to(device, dtype=codec_dtype)),
        codec_dtype,
    )

    forward_names = (
        "transformer",
        "proj",
        "align_masked_video",
        "embed_anchors",
        "memory_proj",
        "timestep_emb",
    )
    for name in forward_names:
        getattr(model, name).to(device=device, dtype=dtype)
    forward_args = {
        "audio_features": features.to(device, dtype=dtype),
        "text_features": text.to(device, dtype=dtype),
        "text_mask": text_mask.to(device),
        "masked_video_features": torch.zeros(
            1, model.vision_encoder.dim, features.shape[1], device=device, dtype=dtype
        ),
        "anchor_ids": batch.anchor_ids.to(device),
        "anchor_alignment": batch.anchor_alignment.to(device),
        "audio_pad_mask": batch.audio_pad_mask.to(device),
    }
    # Host seeded noise makes future CPU/GPU comparisons reproducible.
    noise = torch.randn(features.shape).to(device, dtype=dtype)
    calls = 0
    started = time.perf_counter()

    def field(t, value):
        nonlocal calls
        output = model(noisy_audio=value, time=t.expand(value.shape[0]), **forward_args)
        calls += 1
        emit(
            "diffusion",
            evaluation=calls,
            expected=args.steps * 2,
            seconds=round(time.perf_counter() - started, 3),
        )
        return output

    emit("diffusion", status="started", steps=args.steps)
    with torch.no_grad():
        states = odeint(
            field,
            noise,
            torch.tensor([0.0, 1.0], device=device, dtype=dtype),
            method="midpoint",
            options={"step_size": 1 / args.steps},
        )
        generated = states[-1].transpose(1, 2).cpu()
    report["stages"].append(
        {
            "stage": "diffusion",
            "seconds": time.perf_counter() - started,
            "device": str(device),
            "dtype": str(dtype),
            "evaluations": calls,
        }
    )
    del states, noise
    forward_args.clear()
    for name in forward_names:
        getattr(model, name).to("cpu")
    gc.collect()
    channels = generated.shape[1] // 2
    latents = generated.reshape(2, channels, generated.shape[-1])

    def decode_outputs():
        # Target/residual are independent batch members. Serial decoding lowers
        # peak activation memory without segmenting time or resetting LSTM state.
        outputs = []
        for index in range(2):
            emit("audio_decode", output=index + 1, outputs=2, status="started")
            value = model.audio_codec.decode(
                latents[index : index + 1].to(device, dtype=codec_dtype)
            )
            outputs.append(value.cpu())
            del value
            gc.collect()
        return torch.cat(outputs, dim=0)

    decoded = stage(
        "audio_decode",
        model.audio_codec,
        decode_outputs,
        codec_dtype,
    )
    decoded = decoded.float().reshape(2, -1)[:, : waveform.shape[-1]]
    if decoded.shape[-1] != waveform.shape[-1] or not torch.isfinite(decoded).all():
        raise RuntimeError("Decoded audio is nonfinite or not aligned with the input")
    target, model_residual = decoded.numpy()
    original = waveform.squeeze(0).numpy()
    reconstruction_residual = original - target
    args.output.mkdir(parents=True, exist_ok=True)
    for name, data in (
        ("input", original),
        ("target", target),
        ("model_residual", model_residual),
        ("reconstruction_residual", reconstruction_residual),
    ):
        sf.write(args.output / f"{name}.wav", data, 48000, subtype="FLOAT")
    report.update(
        status="completed",
        output=str(args.output.resolve()),
        samples=len(target),
        sample_rate=48000,
        target_rms=float(np.sqrt(np.mean(target.astype(np.float64) ** 2))),
        target_peak=float(np.max(np.abs(target))),
        model_reconstruction_rmse=float(
            np.sqrt(np.mean((original.astype(np.float64) - target - model_residual) ** 2))
        ),
        exact_reconstruction_max_error=float(
            np.max(np.abs(original - (target + reconstruction_residual)))
        ),
        semantic_quality="not reviewed",
        application_integrated=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("D:/git/sam-audio-amd"))
    parser.add_argument(
        "--weights", type=Path, default=Path("D:/git/sam-audio-amd/models/sam-audio-small")
    )
    parser.add_argument(
        "--text-weights", type=Path, default=Path("D:/git/sam-audio-amd/models/t5-base")
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--start", type=float, default=30)
    parser.add_argument("--seconds", type=float, default=3)
    parser.add_argument("--prompt", default="A lead electric guitar playing a melodic solo.")
    parser.add_argument("--steps", type=int, default=16, choices=range(1, 33))
    parser.add_argument("--dtype", choices=["float16", "float32"], default="float32")
    parser.add_argument("--codec-dtype", choices=["float16", "float32"], default="float32")
    parser.add_argument("--adapter", default="RX 6600M")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cpu-reference", action="store_true", help="Numerical QA reference only")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not (0.12 <= args.seconds <= 30) or args.start < 0:
        parser.error("Bounded research requires 0.12-30 seconds and a nonnegative start")
    report = {"status": "started"}
    started = time.perf_counter()
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                run(args, report)
            finally:
                report["warnings"] = list(dict.fromkeys(str(w.message) for w in caught))
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__, error=str(error))
        traceback.print_exc()
    finally:
        report["total_seconds"] = time.perf_counter() - started
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report), flush=True)
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
