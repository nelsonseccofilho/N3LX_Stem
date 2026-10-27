"""Compare the official trained codec on CPU and AMD using a real audio clip."""

from __future__ import annotations

import argparse
import json
import time
import warnings
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--start", type=float, default=30)
    parser.add_argument("--seconds", type=float, default=3)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()
    if not (0.12 <= args.seconds <= 10) or args.start < 0:
        parser.error("Use a 0.12-10 second clip and a nonnegative start")
    import soundfile as sf
    import torch
    import torch_directml
    import torchaudio
    from sam_audio_amd_compat import configure_codec
    from sam_audio_text_loader import load_upstream

    torch.set_num_threads(4)
    config_module, _, upstream = load_upstream(Path("D:/git/sam-audio-amd"))
    weights = Path("D:/git/sam-audio-amd/models/sam-audio-small")
    cfg = config_module.SAMAudioConfig(**json.loads((weights / "config.json").read_text()))
    model = upstream.DACVAE(cfg.audio_codec).eval()
    state = torch.load(weights / "checkpoint.pt", map_location="cpu", mmap=True, weights_only=True)
    state = {
        k.removeprefix("audio_codec."): v for k, v in state.items() if k.startswith("audio_codec.")
    }
    model.load_state_dict(state, strict=True, assign=True)
    del state
    with sf.SoundFile(args.input) as stream:
        stream.seek(round(args.start * stream.samplerate))
        audio = stream.read(
            round(args.seconds * stream.samplerate), dtype="float32", always_2d=True
        )
        rate = stream.samplerate
    waveform = torch.from_numpy(audio.T.copy()).mean(0, keepdim=True).unsqueeze(0)
    if rate != 48000:
        waveform = torchaudio.functional.resample(waveform, rate, 48000)
    message = torch.zeros(1, 16)
    report = {"checkpoint_loaded": True, "input": str(args.input), "cases": []}

    def decode(latent, msg):
        return model.decoder(model.quantizer.out_proj(latent), message=msg)

    def errors(reference, result):
        delta = result.float() - reference
        return {
            "max_abs_error": delta.abs().max().item(),
            "rmse": delta.square().mean().sqrt().item(),
            "snr_db": (10 * torch.log10(reference.square().mean() / delta.square().mean())).item(),
        }

    args.output.mkdir(parents=True, exist_ok=True)
    trace_mode = "cpu"
    trace_rows = []
    handles = []
    if args.trace:
        trace_dir = args.output / "trace"
        trace_dir.mkdir(exist_ok=True)

        def hook(name):
            def compare(_module, _inputs, output):
                if trace_mode == "skip":
                    return
                value = output[0] if isinstance(output, tuple) else output
                value = value.detach().cpu().float()
                path = trace_dir / f"{name}.pt"
                if trace_mode == "cpu":
                    torch.save(value, path)
                else:
                    ref = torch.load(path, weights_only=True)
                    row = {"layer": name, "shape": list(value.shape), **errors(ref, value)}
                    trace_rows.append(row)
                    print(json.dumps(row), flush=True)

            return compare

        for name, layer in model.decoder.named_modules():
            if name == "model.4.block.7.block.3":

                def prehook(module, inputs):
                    if trace_mode == "skip":
                        return
                    path = trace_dir / "first_bad_input.pt"
                    if trace_mode == "cpu":
                        torch.save(
                            {
                                "x": inputs[0].cpu(),
                                "weight": module.weight.cpu(),
                                "bias": module.bias.cpu(),
                            },
                            path,
                        )
                    else:
                        ref = torch.load(path, weights_only=True)
                        print(
                            json.dumps(
                                {
                                    "prehook": "first_bad",
                                    "strides": list(inputs[0].stride()),
                                    "input": errors(ref["x"], inputs[0].cpu()),
                                    "weight": errors(ref["weight"], module.weight.cpu()),
                                    "bias": errors(ref["bias"], module.bias.cpu()),
                                }
                            ),
                            flush=True,
                        )

                handles.append(layer.register_forward_pre_hook(prehook))
            if name in ("model.0", "model.1", "model.2", "model.3", "model.4") or isinstance(
                layer, (torch.nn.Conv1d, torch.nn.ConvTranspose1d, torch.nn.LSTM)
            ):
                handles.append(layer.register_forward_hook(hook(name)))

    with torch.no_grad():
        start = time.perf_counter()
        cpu_latent = model(waveform)
        cpu_audio = decode(cpu_latent, message)
        report["cpu_seconds"] = time.perf_counter() - start
        print(json.dumps({"stage": "cpu_reference", "seconds": report["cpu_seconds"]}), flush=True)
        trace_mode = "skip"
        configure_codec(model)
        adapted_cpu = decode(cpu_latent, message)
        report["cpu_adaptation"] = errors(cpu_audio, adapted_cpu)
        print(json.dumps({"stage": "cpu_adaptation", **report["cpu_adaptation"]}), flush=True)
        device = torch_directml.device(0)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model.to(device)
            start = time.perf_counter()
            gpu_latent = model(waveform.to(device)).cpu()
            latent_error = errors(cpu_latent, gpu_latent)
            print(json.dumps({"stage": "gpu_encode", **latent_error}), flush=True)
            # Use the same reference latent to isolate decoder numerical differences.
            trace_mode = "gpu"
            gpu_audio = decode(cpu_latent.to(device), message.to(device)).cpu()
            audio_error = errors(cpu_audio, gpu_audio)
            report["gpu_seconds"] = time.perf_counter() - start
            report["cases"].append(
                {
                    "dtype": "float32",
                    "device": str(device),
                    "encode": latent_error,
                    "decode": audio_error,
                }
            )
            report["warnings"] = list(dict.fromkeys(str(w.message) for w in caught))
    for handle in handles:
        handle.remove()
    report["trace"] = trace_rows
    report["ok"] = all(
        case[part]["max_abs_error"] < 1e-4
        for case in report["cases"]
        for part in ("encode", "decode")
    )
    for name, value in (("input", waveform), ("codec_cpu", cpu_audio), ("codec_gpu", gpu_audio)):
        sf.write(args.output / f"{name}.wav", value.flatten().numpy(), 48000, subtype="FLOAT")
    (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
