"""Benchmark a codec-sized LSTM on ONNX/DirectML, without model weights."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    import numpy as np
    import onnxruntime as ort
    import torch

    if "DmlExecutionProvider" not in ort.get_available_providers():
        raise RuntimeError("DirectML provider is unavailable; CPU execution is not accepted")
    torch.set_num_threads(4)
    torch.manual_seed(42)

    class Wrapper(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = torch.nn.LSTM(512, 512, num_layers=2, batch_first=True).eval()

        def forward(self, x, h, c):
            out, (hn, cn) = self.lstm(x, (h, c))
            return out, hn, cn

    model = Wrapper().eval()
    x, h, c = torch.randn(1, 32, 512), torch.zeros(2, 1, 512), torch.zeros(2, 1, 512)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    graph = args.report.with_suffix(".onnx")
    with torch.no_grad():
        torch.onnx.export(
            model,
            (x, h, c),
            graph,
            opset_version=17,
            input_names=["x", "h", "c"],
            output_names=["out", "hn", "cn"],
            dynamic_axes={"x": {1: "time"}, "out": {1: "time"}},
        )
    options = ort.SessionOptions()
    options.enable_mem_pattern = False
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.enable_profiling = True
    options.profile_file_prefix = str(args.report.with_suffix(".profile"))
    session = ort.InferenceSession(
        str(graph), sess_options=options, providers=[("DmlExecutionProvider", {"device_id": 0})]
    )
    cases = []
    for length in [32, 960]:
        x = torch.randn(1, length, 512)
        with torch.no_grad():
            start = time.perf_counter()
            expected = [v.numpy() for v in model(x, h, c)]
            cpu_elapsed = time.perf_counter() - start
        feeds = {"x": x.numpy(), "h": h.numpy(), "c": c.numpy()}
        session.run(None, feeds)
        start = time.perf_counter()
        actual = session.run(None, feeds)
        elapsed = time.perf_counter() - start
        error = max(float(np.abs(a - b).max()) for a, b in zip(actual, expected, strict=True))
        cases.append(
            {
                "sequence": length,
                "max_abs_error": error,
                "ok": error < 0.0001,
                "cpu_seconds": cpu_elapsed,
                "onnx_dml_seconds_including_host_copy": elapsed,
            }
        )
        if length > 32:
            chunk_h, chunk_c = h.numpy(), c.numpy()
            pieces = []
            start = time.perf_counter()
            for offset in range(0, length, 32):
                chunk_out, chunk_h, chunk_c = session.run(
                    None,
                    {
                        "x": feeds["x"][:, offset : offset + 32],
                        "h": chunk_h,
                        "c": chunk_c,
                    },
                )
                pieces.append(chunk_out)
            elapsed = time.perf_counter() - start
            actual_chunked = [np.concatenate(pieces, axis=1), chunk_h, chunk_c]
            error = max(
                float(np.abs(a - b).max()) for a, b in zip(actual_chunked, expected, strict=True)
            )
            cases.append(
                {
                    "sequence": length,
                    "chunk": 32,
                    "max_abs_error": error,
                    "ok": error < 0.0001,
                    "cpu_seconds": cpu_elapsed,
                    "onnx_dml_seconds_including_host_copy": elapsed,
                }
            )
    profile = json.loads(Path(session.end_profiling()).read_text(encoding="utf-8"))
    providers = sorted(
        {e.get("args", {}).get("provider") for e in profile if e.get("args", {}).get("provider")}
    )
    kernel_ops = sorted(
        {
            (e.get("args", {}).get("op_name"), e.get("args", {}).get("provider"))
            for e in profile
            if e.get("args", {}).get("provider")
        }
    )
    report = {
        "scope": "codec-sized LSTM only, random weights; NOT SAM separation",
        "providers_with_executed_kernels": providers,
        "kernel_ops": kernel_ops,
        "cases": cases,
        "checkpoint_loaded": False,
    }
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    return 0 if providers == ["DmlExecutionProvider"] and all(c["ok"] for c in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
