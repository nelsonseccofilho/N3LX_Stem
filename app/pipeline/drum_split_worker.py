"""Isolated CPU worker for the validated six-piece DrumSep model."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app.core.config import MODELS_DIR
from app.core.process import arm_parent_watchdog

MODEL = "MDX23C-DrumSep-aufr33-jarredou.ckpt"
PIECES = ("kick", "snare", "toms", "hh", "ride", "crash")


def main() -> None:
    os.environ.setdefault("STEMDECK_PARENT_PID", str(os.getppid()))
    arm_parent_watchdog()
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    from audio_separator.separator import Separator

    separator = Separator(
        log_level=30,
        model_file_dir=str(MODELS_DIR / "audio-separator"),
        output_dir=sys.argv[2],
        output_format="WAV",
        use_soundfile=True,
        normalization_threshold=1.0,
        amplification_threshold=0.0,
        use_directml=False,
        mdxc_params={
            "segment_size": 256,
            "override_model_segment_size": False,
            "batch_size": 1,
            "overlap": 4,
            "pitch_shift": 0,
        },
    )
    if separator.torch_device.type != "cpu":
        raise RuntimeError("DrumSep requires the validated CPU backend")
    if not (MODELS_DIR / "audio-separator" / MODEL).is_file():
        raise RuntimeError("DrumSep model missing from the local model cache")
    separator.load_model(model_filename=MODEL)
    separator.separate(sys.argv[1], {n: "drum_" + n for n in PIECES})
    if not all((Path(sys.argv[2]) / ("drum_" + n + ".wav")).is_file() for n in PIECES):
        raise RuntimeError("DrumSep did not produce all six pieces")
    print("DrumSep complete (CPU)", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
