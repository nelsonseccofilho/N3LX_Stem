"""Opt-in karaoke sidecar API. Never re-run Demucs or DrumSep.

The existing lyrics_retime run registry and pipeline lock serialize GPU work
and provide cancellation/deletion safety for Windows audio file handles.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.core.config import JOB_ID_RE, JOBS_DIR, ffmpeg_executable
from app.core.registry import get as registry_get
from app.pipeline.karaoke_timing import MAX_BYTES, KaraokeTimingError, aligned_worker_resources, generate_timing, store_timing
from app.pipeline.lyrics_retime import cancel_run, claim_run, current_run
from app.pipeline.runner import _pipeline_lock

router = APIRouter(tags=["karaoke"])
logger = logging.getLogger("stemdeck.karaoke")
_active_tasks: set[asyncio.Task] = set()
_karaoke_runs: dict[str, object] = {}
_SIDE_CAR = "lyrics_timing.json"


def _job(job_id: str):
    if not JOB_ID_RE.fullmatch(job_id):
        raise HTTPException(status_code=404, detail="job not found")
    job = registry_get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    root = JOBS_DIR.resolve()
    job_dir = (JOBS_DIR / job_id).resolve()
    if not job_dir.is_relative_to(root):
        raise HTTPException(status_code=404, detail="job not found")
    return job, job_dir


def _vocals(job_dir: Path) -> Path:
    stem = job_dir / "stems" / "vocals.wav"
    if not stem.resolve().is_relative_to(job_dir) or not stem.is_file():
        raise HTTPException(status_code=409, detail="no vocals stem")
    return stem


def _configuration(model_name: str | None = None, language: str = "pt") -> tuple[str, Path, str]:
    cli = os.environ.get("N3LX_WHISPER_CLI", "").strip()
    model = Path(os.environ.get("N3LX_WHISPER_MODEL", "").strip())
    if model_name is not None:
        if model_name not in {"large-v3", "medium"}:
            raise HTTPException(status_code=422, detail="unsupported Whisper model")
        model = Path(os.environ.get(
            "N3LX_WHISPER_LARGE_MODEL" if model_name == "large-v3" else "N3LX_WHISPER_MEDIUM_MODEL",
            str(model.parent / f"ggml-{model_name}.bin"),
        ))
    if not cli or not shutil.which(cli) or not model.is_file():
        raise HTTPException(status_code=503, detail="Vulkan Whisper worker not configured")
    if language not in {"pt", "en"}:
        raise HTTPException(status_code=422, detail="unsupported karaoke language")
    if language == "pt":
        try:
            aligned_worker_resources()
        except KaraokeTimingError:
            raise HTTPException(status_code=503, detail="WhisperGPU alignment environment not configured") from None
    return cli, model, ffmpeg_executable()


def _archive_timing(job_dir: Path, reason: str) -> None:
    """Remove the active sidecar, keeping a private recovery copy."""
    path = job_dir / _SIDE_CAR
    if path.is_symlink() or not path.resolve().is_relative_to(job_dir):
        raise HTTPException(status_code=409, detail="invalid timing path")
    if path.exists():
        if not path.is_file():
            raise HTTPException(status_code=409, detail="invalid timing sidecar")
        path.replace(path.with_name(f"{path.stem}.{reason}-{uuid.uuid4().hex}.json"))


def _phase(run, phase: str) -> None:
    run.karaoke_phase = phase
    run.karaoke_phase_started = time.monotonic()


async def _generate(job, job_dir: Path, run, replace: bool, cli: str, model: Path, ffmpeg: str, language: str = "pt") -> None:
    def cancelled() -> bool:
        return run.cancel.is_set() or registry_get(job.id) is not job

    try:
        async with _pipeline_lock:
            run.started = True
            if cancelled():
                run.state = "idle"
                return
            _phase(run, "prepare")
            audio = _vocals(job_dir)
            before = (audio.stat().st_size, audio.stat().st_mtime_ns)
            timing = await asyncio.to_thread(
                generate_timing, audio, whisper_cli=cli, model=model,
                ffmpeg=ffmpeg, cancelled=cancelled, phase_changed=lambda phase: _phase(run, phase), language=language,
            )
            if cancelled():
                run.state = "idle"
                return
            after = (audio.stat().st_size, audio.stat().st_mtime_ns)
            if before != after:
                raise KaraokeTimingError("vocals changed during transcription")
            _phase(run, "finalize")
            timing["model"] = model.stem.removeprefix("ggml-")
            output = job_dir / _SIDE_CAR
            await asyncio.to_thread(store_timing, output, timing, replace=replace)
            run.state = "done"
            _phase(run, "done")
    except KaraokeTimingError as exc:
        if cancelled():
            run.state = "idle"
        else:
            run.state = "failed"
            logger.warning("[%s] karaoke generation failed: %s", job.id, exc)
    except Exception:
        run.state = "failed"
        logger.exception("[%s] karaoke generation error", job.id)
    finally:
        run.ended.set()


@router.post("/{job_id}/karaoke/generate")
async def generate_karaoke(job_id: str, request: Request) -> JSONResponse:
    """Start an opt-in sidecar generation; never run any stem extractor."""
    job, job_dir = _job(job_id)
    if job.status != "done":
        raise HTTPException(status_code=409, detail="job not ready")
    _vocals(job_dir)
    if request.headers.get("content-length", "").isdigit() and int(request.headers["content-length"]) > 1024:
        raise HTTPException(status_code=413, detail="request too large")
    raw = await request.body()
    if len(raw) > 1024:
        raise HTTPException(status_code=413, detail="request too large")
    try:
        body = json.loads(raw) if raw.strip() else {}
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail="invalid JSON") from None
    if (not isinstance(body, dict) or
            any(k not in {"replace", "model", "language"} for k in body) or
            type(body.get("replace", False)) is not bool):
        raise HTTPException(status_code=422, detail="expected optional boolean replace")
    model_name = body.get("model")
    if model_name is not None and model_name not in ("large-v3", "medium"):
        raise HTTPException(status_code=422, detail="unsupported Whisper model")
    language = body.get("language", "pt")
    if not isinstance(language, str) or language not in {"pt", "en"}:
        raise HTTPException(status_code=422, detail="unsupported karaoke language")
    cli, model, ffmpeg = _configuration(model_name, language)
    replace = body.get("replace", False)
    if (job_dir / _SIDE_CAR).exists() and not replace:
        raise HTTPException(status_code=409, detail="timing exists; request replace to regenerate")
    run = claim_run(job_id)
    if run is None:
        raise HTTPException(status_code=409, detail="lyrics processing already running")
    try:
        if replace:
            _archive_timing(job_dir, "regenerated")
    except Exception:
        run.state = "idle"
        run.ended.set()
        raise
    run.karaoke_language = language
    run.karaoke_started = time.monotonic()
    _phase(run, "queued")
    _karaoke_runs[job_id] = run
    task = asyncio.create_task(_generate(job, job_dir, run, replace, cli, model, ffmpeg, language))
    _active_tasks.add(task)
    task.add_done_callback(_active_tasks.discard)
    return JSONResponse({"state": "running", "job_id": job_id}, status_code=202)


@router.get("/{job_id}/karaoke/status")
def karaoke_status(job_id: str) -> dict:
    _, job_dir = _job(job_id)
    run = _karaoke_runs.get(job_id)
    if run is not current_run(job_id):
        run = None
    output = job_dir / _SIDE_CAR
    language_models = {}
    for language in ("pt", "en"):
        language_models[language] = []
        for name in ("large-v3", "medium"):
            try:
                _configuration(name, language)
                language_models[language].append(name)
            except HTTPException:
                pass
    models = language_models["pt"]
    now = time.monotonic()
    return {
        "state": run.state if run is not None else "idle",
        "available": output.is_file(), "models": models, "language_models": language_models,
        "language": getattr(run, "karaoke_language", None) if run is not None else None,
        "phase": getattr(run, "karaoke_phase", "queued") if run is not None else None,
        "elapsed_seconds": round(max(0, now - getattr(run, "karaoke_started", now))),
        "phase_elapsed_seconds": round(max(0, now - getattr(run, "karaoke_phase_started", now))),
        "cancel_requested": bool(run is not None and run.cancel.is_set()),
    }


@router.post("/{job_id}/karaoke/cancel")
def cancel_karaoke(job_id: str) -> dict:
    _job(job_id)
    run = _karaoke_runs.get(job_id)
    if run is None or run is not current_run(job_id) or run.state != "running":
        return {"cancel_requested": False}
    return {"cancel_requested": cancel_run(job_id)}


def _timing(job_id: str) -> dict:
    _, job_dir = _job(job_id)
    path = job_dir / _SIDE_CAR
    if not path.resolve().is_relative_to(job_dir) or not path.is_file():
        raise HTTPException(status_code=404, detail="timing not available")
    if path.stat().st_size > MAX_BYTES:
        raise HTTPException(status_code=422, detail="timing exceeds size limit")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(status_code=422, detail="invalid timing sidecar") from None
    if not isinstance(data, dict) or data.get("v") != 1:
        raise HTTPException(status_code=422, detail="invalid timing sidecar")
    return data


@router.get("/{job_id}/karaoke/timing")
def karaoke_json(job_id: str) -> dict:
    return _timing(job_id)


@router.get("/{job_id}/karaoke/lrc", response_class=PlainTextResponse)
def karaoke_lrc(job_id: str) -> str:
    value = _timing(job_id).get("lrc_preview")
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=404, detail="LRC preview not available")
    return value


@router.delete("/{job_id}/karaoke/timing")
def delete_karaoke(job_id: str) -> dict:
    """Remove only the generated sidecar; preserve manual lyrics, stems and a backup."""
    _, job_dir = _job(job_id)
    run = claim_run(job_id)
    if run is None:
        raise HTTPException(status_code=409, detail="lyrics processing already running")
    _karaoke_runs[job_id] = run
    run.started = True
    try:
        _archive_timing(job_dir, "deleted")
        return {"state": "idle", "available": False}
    finally:
        run.state = "idle"
        run.ended.set()
