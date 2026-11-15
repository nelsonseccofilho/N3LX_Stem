"""Bounded, privacy-safe failure reports for the external karaoke worker.

Never persist raw worker stdout: it may contain transcription text and paths.
This module only records allowlisted failure categories and device requests.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

_MAX_WORKER_LOG_BYTES = 128 * 1024
_MAX_REPORTS = 32
_JOB_ID = re.compile(r"^[a-f0-9]{12,24}$", re.IGNORECASE)
_ALLOWED_PHASES = frozenset({"prepare", "transcribe", "align", "finalize"})
_ERROR_CLASSES = (
    "ModuleNotFoundError", "ImportError", "PermissionError",
    "FileNotFoundError", "MemoryError", "RuntimeError", "OSError",
    "ValueError", "TypeError", "AssertionError", "TimeoutError",
)
_ERROR_CLASS_RE = re.compile(
    r"(?m)^\s*(" + "|".join(_ERROR_CLASSES) + r")\s*:"
)


def _worker_log_tail(path: Path) -> str:
    """Read only a capped tail in memory, without storing or echoing it."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - _MAX_WORKER_LOG_BYTES))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def classify_worker_failure(log_text: str) -> tuple[str, str | None]:
    """Return allowlisted metadata only; raw lyrics/paths never leave memory."""
    normalized = log_text.casefold()
    if "modulenotfounderror" in normalized or "no module named" in normalized:
        category = "missing_python_dependency"
    elif "winerror 32" in normalized or "permissionerror" in normalized:
        category = "file_locked_or_permission_denied"
    elif "out of memory" in normalized or "memoryerror" in normalized:
        category = "out_of_memory"
    elif "no such file or directory" in normalized or "filenotfounderror" in normalized:
        category = "missing_file"
    elif "offline" in normalized and ("model" in normalized or "cache" in normalized):
        category = "model_unavailable_offline"
    elif "vulkan" in normalized and ("failed" in normalized or "error" in normalized):
        category = "vulkan_error"
    elif "align" in normalized and ("failed" in normalized or "error" in normalized):
        category = "alignment_error"
    elif "ffmpeg" in normalized and ("failed" in normalized or "error" in normalized):
        category = "audio_preparation_error"
    else:
        category = "worker_failure_unclassified"

    matches = _ERROR_CLASS_RE.findall(log_text)
    return category, matches[-1] if matches else None


def _log_directory() -> Path:
    configured = os.environ.get("STEMDECK_LOGS_DIR", "").strip()
    if configured:
        return Path(configured).expanduser() / "karaoke-diagnostics"
    data = os.environ.get("STEMDECK_DATA_DIR", "").strip()
    if data:
        return Path(data).expanduser() / "logs" / "karaoke-diagnostics"
    return Path.home() / ".n3lx_stem" / "logs" / "karaoke-diagnostics"


def record_worker_failure(
    *, logfile: Path, audio: Path, language: str, phase: str,
    exit_code: int, alignment_backend: str,
) -> str | None:
    """Best-effort bounded report, never masking the original worker error.

    The ID is safe to include in the backend log. The raw log stays temporary.
    """
    report_path = None
    pending_path = None
    try:
        category, exception_type = classify_worker_failure(_worker_log_tail(logfile))
        job_name = audio.parent.parent.name
        job_id = job_name if _JOB_ID.fullmatch(job_name) else None
        report_id = uuid.uuid4().hex[:12]
        root = _log_directory()
        root.mkdir(parents=True, exist_ok=True)
        report_path = root / f"karaoke-failure-{report_id}.json"
        pending_path = root / f".karaoke-failure-{report_id}.tmp"
        report = {
            "schema": 1,
            "diagnostic_id": report_id,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "job_id": job_id,
            "status": "failed",
            "language": language if language in {"pt", "en"} else "unknown",
            "last_observed_phase": phase if phase in _ALLOWED_PHASES else "unknown",
            "exit_code": int(exit_code),
            "category_hint": category,
            "exception_type": exception_type,
            "requested_recognition_backend": "vulkan:0",
            "requested_alignment_backend": (
                alignment_backend if alignment_backend in {"cpu", "directml"} else "unknown"
            ),
            "gpu_execution_verified": False,
        }
        with pending_path.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=True, sort_keys=True)
            handle.write("\n")
        pending_path.replace(report_path)

        # Only manage reports created by this module. No personal files touched.
        reports = sorted(
            root.glob("karaoke-failure-*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for old in reports[_MAX_REPORTS:]:
            try:
                old.unlink()
            except OSError:
                pass
        return report_id
    except (OSError, ValueError):
        if pending_path is not None:
            try:
                pending_path.unlink(missing_ok=True)
            except OSError:
                pass
        # Diagnostics must never change the outcome of a karaoke operation.
        return None
