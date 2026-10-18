"""Fetch published assets through audio-separator's model registry."""

from __future__ import annotations

import os
from pathlib import Path

from audio_separator.separator import Separator

root = Path(__file__).resolve().parents[1]
data = Path(os.environ.get("STEMDECK_DATA_DIR", str(root / "data")))
models = data / "models" / "audio-separator"
models.mkdir(parents=True, exist_ok=True)
separator = Separator(model_file_dir=str(models), use_directml=False, log_level=30)
for model in ("UVR_MDXNET_KARA_2.onnx", "MDX23C-DrumSep-aufr33-jarredou.ckpt"):
    separator.download_model_files(model)
    print("Available:", model, flush=True)
print("Model terms and attribution: docs/models.md and docs/N3LX_STEM.md")
