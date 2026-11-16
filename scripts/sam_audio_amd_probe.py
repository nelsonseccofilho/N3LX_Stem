"""Probe real upstream SAM DiT layers without gated weights or optional encoders.

This checks backend compatibility only: random weights do NOT separate audio.
Run with the existing isolated DirectML Python, never the application runtime.
"""

from __future__ import annotations

import argparse
import ast
import copy
import importlib
import json
import subprocess
import sys
import time
import types
import warnings
from pathlib import Path
from typing import Optional


def load_transformer(source: Path):
    """Load upstream DiT unchanged; omit unrelated multimodal config imports."""
    root = source / "sam_audio" / "model"
    package_name = "_n3lx_sam_probe"
    package = types.ModuleType(package_name)
    package.__path__ = [str(root)]
    sys.modules[package_name] = package
    tree = ast.parse((root / "config.py").read_text(encoding="utf-8"))
    config_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "TransformerConfig"
    )
    config = types.ModuleType(f"{package_name}.config")
    config.Optional = Optional
    exec(
        compile(ast.Module(body=[config_class], type_ignores=[]), str(root / "config.py"), "exec"),
        config.__dict__,
    )
    sys.modules[config.__name__] = config
    return config.TransformerConfig, importlib.import_module(f"{package_name}.transformer")


def run_probe(
    source: Path,
    adapter: str,
    *,
    no_inference_mode: bool = False,
    trace: bool = False,
    compat: bool = False,
):
    import torch
    import torch_directml

    torch.set_num_threads(4)
    adapters = [
        torch_directml.device_name(i).rstrip("\0") for i in range(torch_directml.device_count())
    ]
    index = next(i for i, name in enumerate(adapters) if adapter.casefold() in name.casefold())
    device = torch_directml.device(index)
    config_type, module = load_transformer(source)
    revision = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    report = {
        "upstream_revision": revision,
        "torch": torch.__version__,
        "adapter": adapters[index],
        "device": str(device),
        "scope": "upstream DiT, reduced geometry, random weights; NOT audio separation",
        "checkpoint_loaded": False,
        "attention": "upstream",
        "rotary": "real_4d" if compat else "upstream_6d",
        "autograd_context": "no_grad" if no_inference_mode else "inference_mode",
        "cases": [],
    }
    torch.manual_seed(42)
    cfg = config_type(
        dim=64,
        n_heads=4,
        n_layers=2,
        out_channels=32,
        context_dim=48,
        frequency_embedding_dim=32,
        multiple_of=16,
        max_positions=256,
        dropout=0,
    )
    reference = module.DiT(cfg).eval()
    x, memory, timestep = torch.randn(1, 64, 64), torch.randn(1, 12, 48), torch.tensor([0.25])
    masks = [None, torch.tensor([[True] * 10 + [False] * 2])]
    for dtype in [torch.float32, torch.float16]:
        for mask in masks:
            case = {"dtype": str(dtype), "masked": mask is not None}
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                try:
                    model = copy.deepcopy(reference).to(device=device, dtype=dtype)
                    if compat:
                        from sam_audio_amd_compat import configure_transformer

                        configure_transformer(model)
                    if trace:
                        for name, layer in model.named_modules():
                            layer.register_forward_pre_hook(
                                lambda _module, _args, name=name: print(
                                    f"GPU layer: {name}", file=sys.stderr, flush=True
                                )
                            )
                    with torch.no_grad() if no_inference_mode else torch.inference_mode():
                        expected = reference(x, timestep, memory=memory, memory_padding_mask=mask)
                        inputs = [
                            tensor.to(device=device, dtype=dtype)
                            for tensor in (x, timestep, memory)
                        ]
                        gpu_mask = mask.to(device) if mask is not None else None
                        start = time.perf_counter()
                        result = model(
                            inputs[0], inputs[1], memory=inputs[2], memory_padding_mask=gpu_mask
                        )
                        actual = result.cpu().float()
                        elapsed = time.perf_counter() - start
                    error = (actual - expected).abs().max().item()
                    tolerance = 0.01 if dtype == torch.float16 else 0.0001
                    case.update(
                        ok=bool(torch.isfinite(actual).all()) and error < tolerance,
                        output_device=str(result.device),
                        max_abs_error=error,
                        tolerance=tolerance,
                        first_forward_seconds=elapsed,
                    )
                    del model, result
                except Exception as error:
                    case.update(ok=False, error_type=type(error).__name__, error=str(error))
                case["warnings"] = list(dict.fromkeys(str(w.message) for w in caught))
            report["cases"].append(case)
            print(json.dumps(case), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--adapter", default="RX 6600M")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--no-inference-mode", action="store_true")
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--compat", action="store_true")
    args = parser.parse_args()
    report = run_probe(
        args.source,
        args.adapter,
        no_inference_mode=args.no_inference_mode,
        trace=args.trace,
        compat=args.compat,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if all(case["ok"] for case in report["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
