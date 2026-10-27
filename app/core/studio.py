"""Additional lanes from validated local multitrack imports."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import EXTRA_STEM_NAMES, STEM_NAMES

DRUM_STEMS = ("drum_kick", "drum_snare", "drum_toms", "drum_hh", "drum_ride", "drum_crash")
DETAIL_LABELS = dict(
    zip(DRUM_STEMS, ("Bumbo", "Caixa", "Tons", "Chimbal", "Ride", "Crash"), strict=True)
)
DETAIL_LABELS.update(
    residual_mix="Resíduo da separação",
    residual_drums="Resíduo da bateria",
    drum_recovery="Recuperação seletiva da bateria",
    residual_drums_refined="Resíduo restante da bateria",
    residual_vocals="Resíduo vocal",
    guitar_lead="Guitarra solo estimada",
    guitar_acoustic="Violão estimado",
    guitar_rhythm="Guitarra base estimada",
    residual_guitar="Outras guitarras / sobras",
)
STUDIO_NAMES = (*DETAIL_LABELS, *(f"studio_{n:02}" for n in range(1, 33)), "reaper_master")
STUDIO_LABELS = {
    **DETAIL_LABELS,
    **{f"studio_{n:02}": f"Pista {n:02}" for n in range(1, 33)},
    "reaper_master": "Master REAPER",
}


def read_layout(job_dir: Path) -> dict | None:
    try:
        value = json.loads((job_dir / "studio.json").read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return None
        labels = value.get("labels", {})
        return {
            "labels": {
                k: str(v)[:100]
                for k, v in labels.items()
                if k in (*STEM_NAMES, *EXTRA_STEM_NAMES, *STUDIO_NAMES)
            },
            "notice": str(value.get("notice", ""))[:500],
            "profile": value.get("profile", "standard"),
            "active_names": [
                n
                for n in value.get("active_names", [])
                if n in (*STEM_NAMES, *EXTRA_STEM_NAMES, *STUDIO_NAMES)
            ],
            "percussion_names": [n for n in value.get("percussion_names", []) if n in STUDIO_NAMES],
        }
    except (OSError, ValueError, TypeError, AttributeError):
        return None
