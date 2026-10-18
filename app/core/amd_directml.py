"""Local opt-in DirectML worker, isolated from the application's Torch 2.6."""

from __future__ import annotations

import functools
import json
import logging
import os
import subprocess
from pathlib import Path

log = logging.getLogger("stemdeck.directml")


def directml_python() -> str:
    return os.environ.get("STEMDECK_DIRECTML_PYTHON", "").strip()


def select_device():
    import torch
    import torch_directml

    wanted = os.environ.get("STEMDECK_DIRECTML_ADAPTER", "").casefold()
    devices = [
        (i, torch_directml.device_name(i).rstrip("\x00"))
        for i in range(torch_directml.device_count())
    ]
    candidates = [(i, name) for i, name in devices if not wanted or wanted in name.casefold()]
    if not candidates:
        raise RuntimeError(f"DirectML adapter {wanted!r} not found; detected: {devices}")
    index, name = candidates[0]
    device = torch_directml.device(index)
    result = (torch.ones(4).to(device) * 3).cpu()
    if not torch.equal(result, torch.full((4,), 3.0)):
        raise RuntimeError("DirectML compute probe failed")
    return device, name


@functools.lru_cache(maxsize=8)
def _probe(python: str, adapter: str) -> bool:
    try:
        result = subprocess.run(
            [python, str(Path(__file__).resolve())],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=45,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            check=True,
        )
        return bool(json.loads(result.stdout)["available"])
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        log.warning("DirectML probe failed: %s", exc)
        return False


def directml_available() -> bool:
    python = directml_python()
    return bool(
        python
        and Path(python).is_file()
        and _probe(python, os.environ.get("STEMDECK_DIRECTML_ADAPTER", ""))
    )


def configure_demucs():
    """FFT/complex tensors stay on CPU; real-valued neural layers run on DML.

    Demucs 4.0.1 already uses this division for MPS. DML also lacks complex
    tensors, so apply the same boundary only inside the isolated DML worker.
    Installed upstream packages and the CPU worker are left intact.
    """
    import torch
    from demucs.htdemucs import HTDemucs

    device, name = select_device()
    spec, mask, ispec = HTDemucs._spec, HTDemucs._mask, HTDemucs._ispec

    def cpu_spec(self, x):
        return spec(self, x.cpu())

    def cpu_mask(self, z, m):
        return mask(self, z.cpu(), m.cpu())

    def cpu_ispec(self, z, *args, **kwargs):
        return ispec(self, z.cpu(), *args, **kwargs).to(device)

    HTDemucs._spec = cpu_spec
    HTDemucs._mask = cpu_mask
    HTDemucs._ispec = cpu_ispec
    torch.set_num_threads(max(1, int(os.environ.get("STEMDECK_DIRECTML_CPU_THREADS", "4"))))
    import sys

    print(
        f"DirectML: {name}; neural network on GPU, complex audio transforms on CPU",
        file=sys.stderr,
        flush=True,
    )
    return device


if __name__ == "__main__":
    import sys

    if "--worker" in sys.argv:
        # Running -m app.pipeline.demucs_worker imports pipeline/__init__.py,
        # which eagerly imports the whole backend. The GPU environment only
        # needs Demucs, so execute the worker file without that package init.
        import runpy

        root = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(root))
        worker = root / "app" / "pipeline" / "demucs_worker.py"
        sys.argv = [str(worker), "directml"]
        runpy.run_path(str(worker), run_name="__main__")
    else:
        _, name = select_device()
        print(json.dumps({"available": True, "adapter": name}))
