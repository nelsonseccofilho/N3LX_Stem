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


# Only module names from this allowlist can be written to diagnostic JSON.
_KNOWN_DEPENDENCIES = frozenset({
    "torch", "torchaudio", "torchvision", "whisperx", "transformers",
    "numpy", "scipy", "onnxruntime", "accelerate", "soundfile",
    "librosa", "huggingface_hub", "faster_whisper",
})
_MISSING_MODULE_RE = re.compile(
    r"\bno module named\s+['\"]?([a-zA-Z_][a-zA-Z0-9_.]*)", re.IGNORECASE
)
_WORKER_STAGE_RE = re.compile(r"\[([1-4])/4\]")
_EXPLICIT_VULKAN_FAILURE = re.compile(
    r"\bvulkan\b.*\b(?:failed|failure|error|unavailable)\b"
    r"|\b(?:failed|failure|error)\b.*\bvulkan\b", re.IGNORECASE
)
_EXPLICIT_ALIGNMENT_FAILURE = re.compile(
    r"\b(?:align|alignment|whisperx)\b.*\b(?:failed|failure|error)\b"
    r"|\b(?:failed|failure|error)\b.*\b(?:align|alignment|whisperx)\b",
    re.IGNORECASE,
)
_EXPLICIT_FFMPEG_FAILURE = re.compile(
    r"\bffmpeg\b.*\b(?:failed|failure|error)\b"
    r"|\b(?:failed|failure|error)\b.*\bffmpeg\b", re.IGNORECASE
)
_WORKER_ARG_ERROR = re.compile(
    r"\b(?:unrecognized arguments|invalid choice|arguments are required)\b",
    re.IGNORECASE,
)


def analyze_worker_failure(log_text: str) -> dict[str, str | None]:
    """Produce only fixed labels and allowlisted metadata from worker output.

    Do not infer that Vulkan failed merely because the log contains 'Vulkan'
    somewhere and a separate error elsewhere. Generic errors remain unknown.
    Raw messages may contain lyrics, paths or sensitive text: never persist them.
    """
    matches = _ERROR_CLASS_RE.findall(log_text)
    exception_type = matches[-1] if matches else None

    module_match = _MISSING_MODULE_RE.search(log_text)
    module = None
    if module_match:
        candidate = module_match.group(1).split(".")[0].lower()
        if candidate in _KNOWN_DEPENDENCIES:
            module = candidate

    lines = log_text.splitlines()
    # Stage marker is an observation, not proof that a stage completed.
    stage_markers = _WORKER_STAGE_RE.findall(log_text)
    last_stage = f"{stage_markers[-1]}/4" if stage_markers else None

    # Only the terminal portion can identify a subsystem-specific failure.
    # Earlier Vulkan startup information followed by unrelated errors is not
    # evidence that the GPU or Vulkan was at fault.
    terminal_lines = lines[-48:]
    if module_match or exception_type == "ModuleNotFoundError":
        category, basis = "missing_python_dependency", "python_exception"
    elif exception_type == "ImportError":
        category, basis = "python_dependency_import_error", "python_exception"
    elif exception_type == "PermissionError" or any(
        "winerror 32" in line.casefold() for line in terminal_lines
    ):
        category, basis = "file_locked_or_permission_denied", "python_exception"
    elif exception_type == "MemoryError" or any(
        "out of memory" in line.casefold() for line in terminal_lines
    ):
        category, basis = "out_of_memory", "python_exception_or_message"
    elif exception_type == "FileNotFoundError":
        category, basis = "missing_file", "python_exception"
    elif any(
        "offline" in line.casefold()
        and ("model" in line.casefold() or "cache" in line.casefold())
        for line in terminal_lines
    ):
        category, basis = "model_unavailable_offline", "explicit_log_line"
    elif any(_WORKER_ARG_ERROR.search(line) for line in terminal_lines):
        category, basis = "worker_argument_error", "explicit_log_line"
    elif any(_EXPLICIT_ALIGNMENT_FAILURE.search(line) for line in terminal_lines):
        category, basis = "alignment_error", "explicit_log_line"
    elif any(_EXPLICIT_VULKAN_FAILURE.search(line) for line in terminal_lines):
        category, basis = "vulkan_error", "explicit_log_line"
    elif any(_EXPLICIT_FFMPEG_FAILURE.search(line) for line in terminal_lines):
        category, basis = "audio_preparation_error", "explicit_log_line"
    else:
        category, basis = "worker_failure_unclassified", "insufficient_evidence"
    return {
        "category_hint": category,
        "exception_type": exception_type,
        "missing_dependency": module,
        "last_worker_stage_marker": last_stage,
        "classification_basis": basis,
    }


def classify_worker_failure(log_text: str) -> tuple[str, str | None]:
    """Backward-compatible category/exception contract for existing tests."""
    analysis = analyze_worker_failure(log_text)
    return analysis["category_hint"], analysis["exception_type"]


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
        analysis = analyze_worker_failure(_worker_log_tail(logfile))
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
            "category_hint": analysis["category_hint"],
            "exception_type": analysis["exception_type"],
            "missing_dependency": analysis["missing_dependency"],
            "last_worker_stage_marker": analysis["last_worker_stage_marker"],
            "classification_basis": analysis["classification_basis"],
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
