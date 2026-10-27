"""Probe SAM dependencies with random weights. This does not separate music."""

from __future__ import annotations

import argparse
import json
import time
import warnings
from contextlib import nullcontext
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=["codec", "text", "ode"])
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--compat", action="store_true")
    args = parser.parse_args()
    import torch
    import torch_directml

    torch.set_num_threads(4)
    index = next(
        i
        for i in range(torch_directml.device_count())
        if "RX 6600M" in torch_directml.device_name(i)
    )
    device = torch_directml.device(index)
    torch.manual_seed(42)
    report = {
        "component": args.component,
        "checkpoint_loaded": False,
        "scope": "reduced geometry, random weights; NOT audio separation",
        "adapter": torch_directml.device_name(index).rstrip("\0"),
        "cases": [],
        "compat": args.compat,
    }
    if args.component == "codec":
        from dacvae import DACVAE

        def factory():
            return DACVAE(
                encoder_dim=8,
                encoder_rates=[2, 8, 10, 12],
                latent_dim=32,
                decoder_dim=1536,
                decoder_rates=[12, 10, 8, 2],
                n_codebooks=2,
                codebook_size=16,
                codebook_dim=8,
            ).eval()

        audio = torch.randn(1, 1, 5760) * 0.1

        def forward(model, dtype, where):
            encoded = model.encoder(audio.to(device=where, dtype=dtype))
            mean, _ = model.quantizer.in_proj(encoded).chunk(2, dim=1)
            return model.decoder(
                model.quantizer.out_proj(mean), message=torch.zeros(1, 16, device=where)
            )
    elif args.component == "text":
        from transformers import T5Config, T5EncoderModel

        def factory():
            return T5EncoderModel(
                T5Config(
                    vocab_size=128,
                    d_model=64,
                    d_kv=16,
                    d_ff=128,
                    num_layers=2,
                    num_heads=4,
                    dropout_rate=0,
                )
            ).eval()

        ids = torch.randint(0, 128, (1, 16))
        mask = torch.tensor([[1] * 13 + [0] * 3])

        def forward(model, dtype, where):
            from sam_audio_amd_compat import directml_t5_compat

            with directml_t5_compat() if args.compat else nullcontext():
                return model(
                    input_ids=ids.to(where), attention_mask=mask.to(where)
                ).last_hidden_state
    else:
        from torchdiffeq import odeint

        def factory():
            return torch.nn.Sequential(
                torch.nn.Linear(16, 32), torch.nn.SiLU(), torch.nn.Linear(32, 16)
            ).eval()

        noise = torch.randn(1, 8, 16)

        def forward(model, dtype, where):
            def field(t, state):
                return model(state) * (1 + t)

            return odeint(
                field,
                noise.to(device=where, dtype=dtype),
                torch.tensor([0.0, 1.0], device=where, dtype=dtype),
                method="midpoint",
                options={"step_size": 2 / 32},
            )[-1]

    reference = factory()
    with torch.no_grad():
        expected = forward(reference, torch.float32, "cpu")
        if args.compat and args.component == "codec":
            from sam_audio_amd_compat import configure_codec

            cpu_adapted = factory()
            cpu_adapted.load_state_dict(reference.state_dict())
            configure_codec(cpu_adapted)
            cpu_result = forward(cpu_adapted, torch.float32, "cpu")
            report["cpu_adaptation_max_abs_error"] = (cpu_result - expected).abs().max().item()
            print(
                json.dumps(
                    {"cpu_adaptation_max_abs_error": report["cpu_adaptation_max_abs_error"]}
                ),
                flush=True,
            )
            del cpu_adapted, cpu_result
    for dtype in [torch.float32, torch.float16]:
        case = {"dtype": str(dtype)}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                model = factory()
                model.load_state_dict(reference.state_dict())
                if args.compat and args.component == "codec":
                    from sam_audio_amd_compat import configure_codec

                    configure_codec(model)
                model = model.to(device=device, dtype=dtype)
                with torch.no_grad():
                    started = time.perf_counter()
                    result = forward(model, dtype, device)
                    actual = result.cpu().float()
                    elapsed = time.perf_counter() - started
                error = (actual - expected).abs().max().item()
                rmse = (actual - expected).square().mean().sqrt().item()
                tol = 0.015 if dtype == torch.float16 else 0.0001
                case.update(
                    ok=bool(torch.isfinite(actual).all()) and error < tol,
                    output_device=str(result.device),
                    max_abs_error=error,
                    rmse=rmse,
                    tolerance=tol,
                    first_forward_seconds=elapsed,
                )
                del model, result
            except Exception as error:
                case.update(ok=False, error_type=type(error).__name__, error=str(error))
            case["warnings"] = list(dict.fromkeys(str(w.message) for w in caught))
        report["cases"].append(case)
        print(json.dumps(case), flush=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if all(case["ok"] for case in report["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
