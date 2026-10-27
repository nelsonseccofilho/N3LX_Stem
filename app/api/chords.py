"""On-demand experimental chord timeline, kept separate from user data."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from app.core.config import JOB_ID_RE, JOBS_DIR, MODELS_DIR
from app.core.registry import get as registry_get

router = APIRouter()
logger = logging.getLogger(__name__)
_lock = asyncio.Lock()


def _paths(job_id: str):
    if not JOB_ID_RE.fullmatch(job_id) or registry_get(job_id) is None:
        raise HTTPException(404, "track not found")
    folder = (JOBS_DIR / job_id).resolve()
    if not folder.is_relative_to(JOBS_DIR.resolve()):
        raise HTTPException(404, "track not found")
    return folder, folder / "chords.estimated.json"


@router.get("/{job_id}/chords")
def get_chords(job_id: str):
    _, result = _paths(job_id)
    if not result.is_file():
        raise HTTPException(404, "no chord analysis")
    try:
        value = json.loads(result.read_text(encoding="utf-8"))
        if value.get("version") != 1 or not isinstance(value.get("segments"), list):
            raise ValueError("invalid chord data")
        return value
    except (OSError, ValueError, AttributeError):
        raise HTTPException(500, "invalid chord analysis") from None


def _analyze(job_id: str):
    folder, result = _paths(job_id)
    if result.exists():
        return get_chords(job_id)
    source = folder / "stems" / "mix.wav"
    if not source.is_file() or not source.resolve().is_relative_to(folder):
        raise HTTPException(404, "mixed audio not available")
    model_dir = MODELS_DIR / "lv-chordia-rrherr"
    if not (model_dir / "lv_chordia" / "__init__.py").is_file():
        raise HTTPException(503, "chord model unavailable")
    sys.path.insert(0, str(model_dir))
    try:
        import librosa
        import soundfile
        from lv_chordia import load_ensemble, recognize
        info = soundfile.info(str(source))
        if info.duration > 1200:
            raise HTTPException(422, "track exceeds 20 minutes")
        audio, sr = librosa.load(str(source), sr=22050, mono=True)
        if len(audio) < sr:
            raise ValueError("audio too short")
        segments = recognize(load_ensemble(use_gpu=False), audio, ["C:maj", "C:min", "C:7"])
        data = {"version": 1, "model": "lv-chordia ISMIR2019", "device": "cpu",
                "estimated": True, "duration": len(audio) / sr, "segments": segments}
        # Publish a fully-written file without replacing an existing one.
        fd, temporary = tempfile.mkstemp(prefix=".chords-", suffix=".tmp", dir=folder)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False)
            os.link(temporary, result)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return data
    except FileExistsError:
        return get_chords(job_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Chord analysis failed")
        raise HTTPException(500, "chord analysis failed") from None
    finally:
        if str(model_dir) in sys.path:
            sys.path.remove(str(model_dir))


@router.post("/{job_id}/chords")
async def analyze_chords(job_id: str):
    _paths(job_id)
    if _lock.locked():
        raise HTTPException(409, "chord analysis busy")
    async with _lock:
        return await asyncio.to_thread(_analyze, job_id)
