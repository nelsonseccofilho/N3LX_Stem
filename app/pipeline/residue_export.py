"""Non-destructive export of exactly three aligned residue WAVs.

The three buckets refer to *already published* residual signals. Original stems
and studio manifests are never changed. A missing category is a silent WAV of
the track's duration, not an invented or inferred residual.
"""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

import numpy as np
import soundfile as sf

BLOCK = 65536
OUTPUT_NAMES = (
    "residuos_vozes",
    "residuos_musica",
    "residuos_bateria",
)


def residue_groups(published: set[str]) -> dict[str, tuple[str, ...]]:
    """Select non-overlapping residuals from the active multitrack layout.

    Drums: two refined files are a partition of the original drum residual,
    so they must NEVER be summed alongside residual_drums. When the refinement
    wasn't fully published, use only the original drum residual.
    """
    refined = {"drum_recovery", "residual_drums_refined"}
    drum = (
        ("drum_recovery", "residual_drums_refined")
        if refined <= published
        else (("residual_drums",) if "residual_drums" in published else ())
    )
    return {
        "residuos_vozes": ("residual_vocals",) if "residual_vocals" in published else (),
        "residuos_musica": tuple(
            name for name in ("residual_mix", "residual_guitar") if name in published
        ),
        "residuos_bateria": drum,
    }


def _write_bucket(
    reference: sf._SoundFileInfo, inputs: list[Path], output: Path
) -> None:
    """Block-wise lossless floating-point sum, with strict time-grid checks."""
    with ExitStack() as stack:
        readers = [stack.enter_context(sf.SoundFile(path)) for path in inputs]
        for reader in readers:
            if (
                reader.samplerate,
                reader.channels,
                reader.frames,
            ) != (
                reference.samplerate,
                reference.channels,
                reference.frames,
            ):
                raise ValueError("Residue stems have incompatible audio grids")
        writer = stack.enter_context(
            sf.SoundFile(
                output,
                "w",
                samplerate=reference.samplerate,
                channels=reference.channels,
                format="WAV",
                subtype="FLOAT",
            )
        )
        remaining = reference.frames
        while remaining:
            n = min(BLOCK, remaining)
            mixed = np.zeros((n, reference.channels), dtype=np.float64)
            for reader in readers:
                samples = reader.read(n, dtype="float64", always_2d=True)
                if samples.shape != mixed.shape or not np.isfinite(samples).all():
                    raise ValueError("Residue input has invalid or incomplete samples")
                mixed += samples
            if not np.isfinite(mixed).all():
                raise ValueError("Residue sum contains non-finite samples")
            writer.write(mixed)
            remaining -= n


def write_residue_archive(
    stems_dir: Path, archive: Path, published: set[str], prefix: str = ""
) -> None:
    """Produce three WAV members; no modifications to any existing stem."""
    groups = residue_groups(published)
    if not any(groups.values()):
        raise ValueError("No published residual signals found")

    # The canonical base drum stem is always present for full-mode jobs, even
    # when a detailed drum pass fails; it fixes the shared duration/grid.
    reference_file = stems_dir / "drums.wav"
    if not reference_file.is_file():
        raise FileNotFoundError("Canonical drums stem is not available")
    reference = sf.info(reference_file)

    import tempfile

    with tempfile.TemporaryDirectory(prefix="stemdeck_residues_") as temporary:
        with ZipFile(archive, "w", ZIP_STORED, allowZip64=True) as zf:
            for bucket in OUTPUT_NAMES:
                paths = [stems_dir / f"{name}.wav" for name in groups[bucket]]
                if not all(path.is_file() for path in paths):
                    raise FileNotFoundError(f"Missing published residue in {bucket}")
                output = Path(temporary) / f"{bucket}.wav"
                _write_bucket(reference, paths, output)
                member = f"{prefix}_{bucket}.wav" if prefix else f"{bucket}.wav"
                zf.write(output, arcname=member)
