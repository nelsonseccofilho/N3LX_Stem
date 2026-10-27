"""Opt-in, independent karaoke timing via whisper.cpp.

Does not modify stems, playlists or the canonical lyrics.json.
Writes a versioned sidecar for later reconciliation with lyrics_retime.
No VAD: some whisper.cpp versions mix token and segment timebases when VAD
removes silence. Machine timestamps remain unverified until audio QA.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable
from typing import Any

MAX_WORDS = 30_000
MAX_BYTES = 8 * 1024 * 1024
MAX_DURATION = 6 * 3600.0
_SPECIAL = re.compile(r"^\[_(?:BEG|TT_\d+|SOT|EOT|NOSPEECH).*\]$")
_WORD = re.compile(r"\w", re.UNICODE)


class KaraokeTimingError(ValueError):
    """Input rejected before persisting karaoke timing."""


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise KaraokeTimingError(f"{label}: expected a numeric timestamp")
    out = float(value)
    if not math.isfinite(out) or out < 0 or out > MAX_DURATION:
        raise KaraokeTimingError(f"{label}: invalid timestamp")
    return out


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        raise KaraokeTimingError("word text must be a string")
    text = " ".join(value.split()).strip()
    if len(text) > 120:
        raise KaraokeTimingError("word text is too long")
    if any(x in text for x in "<>[]"):
        raise KaraokeTimingError("word text contains reserved LRC syntax")
    return text


def _finite_ms(value: Any, label: str) -> float:
    """Convert whisper.cpp milliseconds before checking seconds bounds."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise KaraokeTimingError(f"{label}: expected a numeric timestamp")
    return _finite(value / 1000.0, label)

def _parse_whisper_cpp(source: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """Read actual -ojf JSON: segment-level timestamps and optional tokens.

    Segment timestamps alone are NOT word timecodes. Prefer each token's own
    offsets, and join token fragments until a whitespace-delimited word begins.
    Reject ambiguous multiword segments without timestamped tokens.
    """
    chunks = source.get("transcription")
    if not isinstance(chunks, list) or len(chunks) > MAX_WORDS * 2:
        raise KaraokeTimingError("whisper.cpp transcription must be a bounded list")
    words: list[dict[str, Any]] = []
    invalid_tokens = 0
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict) or not isinstance(chunk.get("offsets"), dict):
            raise KaraokeTimingError(f"invalid transcription chunk {index}")
        offsets = chunk["offsets"]
        seg_start = _finite_ms(offsets.get("from"), "segment.from")
        seg_end = _finite_ms(offsets.get("to"), "segment.to")
        if seg_end < seg_start:
            raise KaraokeTimingError("segment ends before it starts")
        # -ml 1 -sow: a single-word segment has its own timestamps.
        # Prefer those over possibly inverted experimental token offsets.
        segment_text = chunk.get("text")
        if (
            isinstance(segment_text, str)
            and len(segment_text.split()) == 1
            and _WORD.search(segment_text)
            and not any(ch in segment_text for ch in "<>[]")
        ):
            words.append({
                "text": _clean_text(segment_text),
                "start": seg_start,
                "end": seg_end,
            })
            if len(words) > MAX_WORDS:
                raise KaraokeTimingError("too many words")
            continue
        tokens = chunk.get("tokens")
        if isinstance(tokens, list) and tokens:
            if len(tokens) > MAX_WORDS * 4:
                raise KaraokeTimingError("segment has too many tokens")
            current: dict[str, Any] | None = None
            for token in tokens:
                if not isinstance(token, dict) or not isinstance(token.get("text"), str):
                    raise KaraokeTimingError("invalid full JSON token")
                raw = token["text"]
                stripped = raw.strip()
                if not stripped or _SPECIAL.fullmatch(stripped):
                    continue
                piece = _clean_text(raw)
                if not piece:
                    continue
                if len(piece.split()) > 1:
                    raise KaraokeTimingError("multiword token has no per-word timecodes")
                toff = token.get("offsets")
                if not isinstance(toff, dict):
                    # A token without its own timing cannot become a word.
                    if not _WORD.search(piece):
                        continue
                    raise KaraokeTimingError("word token lacks timestamps")
                start = _finite_ms(toff.get("from"), "token.from")
                end = _finite_ms(toff.get("to"), "token.to")
                if end < start:
                    invalid_tokens += 1
                    continue
                if not _WORD.search(piece):
                    if current is not None:
                        current["text"] += piece
                        current["end"] = max(current["end"], end)
                    continue
                boundary = (current is None or raw[0].isspace()
                            or start - current["end"] > 0.35)
                if boundary:
                    if current is not None:
                        words.append(current)
                    current = {"text": piece, "start": start, "end": end}
                else:
                    # Wordpieces such as " en", "con", "trar" must be joined,
                    # not interpreted as three different words.
                    current["text"] += piece
                    current["end"] = max(current["end"], end)
            if current is not None:
                words.append(current)
        else:
            text = _clean_text(chunk.get("text"))
            if not text or _SPECIAL.fullmatch(text):
                continue
            if len(text.split()) > 1:
                raise KaraokeTimingError("multiword segment has no token timecodes")
            if not _WORD.search(text):
                if words:
                    words[-1]["text"] += text
                    words[-1]["end"] = max(words[-1]["end"], seg_end)
                continue
            words.append({"text": text, "start": seg_start, "end": seg_end})
        if len(words) > MAX_WORDS:
            raise KaraokeTimingError("too many words")
    if invalid_tokens > max(2, len(words) // 20):
        raise KaraokeTimingError(
            f"too many inverted token timestamps ({invalid_tokens})"
        )
    return words, invalid_tokens


def _parse_whisperx(source: dict[str, Any]) -> list[dict[str, Any]]:
    segments = source.get("segments")
    if not isinstance(segments, list) or len(segments) > MAX_WORDS:
        raise KaraokeTimingError("segments must be a bounded list")
    words = []
    for segment in segments:
        if not isinstance(segment, dict) or not isinstance(segment.get("words"), list):
            raise KaraokeTimingError("segment has no word timestamps")
        for item in segment["words"]:
            if not isinstance(item, dict):
                raise KaraokeTimingError("invalid word")
            text = _clean_text(item.get("word", item.get("text")))
            if not text:
                continue
            if item.get("start") is None or item.get("end") is None:
                raise KaraokeTimingError("word has no alignment timestamp")
            words.append({
                "text": text,
                "start": _finite(item["start"], "word.start"),
                "end": _finite(item["end"], "word.end"),
            })
            if len(words) > MAX_WORDS:
                raise KaraokeTimingError("too many words")
    return words


def normalize_timing(source: dict[str, Any]) -> dict[str, Any]:
    """Normalize actual word timestamps; do not invent times."""
    if not isinstance(source, dict):
        raise KaraokeTimingError("expected transcription JSON object")
    if "transcription" in source:
        words, invalid_tokens = _parse_whisper_cpp(source)
        engine = "whisper.cpp"
    elif "segments" in source:
        words = _parse_whisperx(source)
        invalid_tokens = 0
        engine = "whisperx"
    else:
        raise KaraokeTimingError("unrecognized transcription JSON format")
    if len(words) < 3:
        raise KaraokeTimingError("insufficient timestamped words")
    previous = -1.0
    for word in words:
        if word["end"] < word["start"]:
            raise KaraokeTimingError("word ends before it starts")
        if word["start"] < previous - 0.02:
            raise KaraokeTimingError("word timestamps are not chronological")
        previous = max(previous, word["start"])
    language = source.get("language")
    if not isinstance(language, str):
        result = source.get("result")
        language = result.get("language") if isinstance(result, dict) else None
    language = language if isinstance(language, str) and len(language) <= 16 else None
    return {
        "v": 1, "engine": engine, "language": language,
        "timing_status": "machine_unverified", "words": words,
        "skipped_inverted_tokens": invalid_tokens,
    }


def lrc_stamp(seconds: float) -> str:
    centiseconds = round(seconds * 100)
    return f"{centiseconds // 6000:02d}:{(centiseconds % 6000) // 100:02d}.{centiseconds % 100:02d}"


def enhanced_lrc(words: list[dict[str, Any]], *, pause_sec: float = 0.75) -> str:
    """Machine transcript preview, not the user's verified lyrics."""
    if not words:
        return ""
    lines: list[str] = []
    line: list[dict[str, Any]] = []
    for word in words:
        if line and (word["start"] - line[-1]["end"] >= pause_sec or len(line) >= 9):
            lines.append(_lrc_line(line))
            line = []
        line.append(word)
    if line:
        lines.append(_lrc_line(line))
    return "\n".join(lines)


def _lrc_line(words: list[dict[str, Any]]) -> str:
    result = f"[{lrc_stamp(words[0]['start'])}]"
    for idx, word in enumerate(words):
        result += f"<{lrc_stamp(word['start'])}>{word['text']}"
        if idx + 1 < len(words):
            result += " "
    return result + f"<{lrc_stamp(words[-1]['end'])}>"


def store_timing(destination: Path, timing: dict[str, Any], *, replace: bool = False) -> Path | None:
    """Write atomically. Replacements preserve a uniquely named old version."""
    destination = Path(destination)
    if destination.is_symlink():
        raise KaraokeTimingError("destination cannot be a symlink")
    if destination.exists() and not replace:
        raise KaraokeTimingError("timing already exists: regeneration needs replace=True")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    backup: Path | None = None
    try:
        with temp.open("x", encoding="utf-8", newline="\n") as f:
            json.dump(timing, f, ensure_ascii=False, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        if destination.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = destination.with_name(
                f"{destination.stem}.backup-{stamp}-{uuid.uuid4().hex[:8]}.json"
            )
            shutil.copy2(destination, backup)
        os.replace(temp, destination)
        return backup
    finally:
        temp.unlink(missing_ok=True)


def _checked_executable(value: str, label: str) -> str:
    resolved = shutil.which(value)
    if not resolved:
        raise KaraokeTimingError(f"{label} not found: {value}")
    return resolved


def _run_command(
    argv: list[str], *, timeout: float,
    cancelled: Callable[[], bool] | None = None,
) -> int:
    """Terminate workers reliably on cancel/timeout, including Windows."""
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    started = time.monotonic()
    try:
        while proc.poll() is None:
            if cancelled is not None and cancelled():
                raise KaraokeTimingError("karaoke generation cancelled")
            if time.monotonic() - started > timeout:
                raise KaraokeTimingError("karaoke worker exceeded its timeout")
            time.sleep(0.15)
        return int(proc.returncode)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def aligned_worker_resources() -> tuple[Path, Path]:
    """Use the already-installed NELX worker; never download or fall back."""
    root = Path(os.environ.get("N3LX_WHISPER_GPU_HOME", str(Path.home() / "NELX-Whisper-GPU"))).expanduser().resolve()
    python = root / "venv" / "Scripts" / "python.exe"
    script = root / "transcrever_gpu.py"
    required = (python, script, root / "alinhamento_directml.py",
                root / "alinhamento_directml_worker.py",
                root / "experimentos" / "diarizacao-directml" / "venv" / "Scripts" / "python.exe",
                root / "experimentos" / "alinhamento-directml" / "modelo" / "onnx" / "model.onnx",
                root / "experimentos" / "alinhamento-directml" / "modelo" / "vocab.json")
    if not all(path.is_file() for path in required):
        raise KaraokeTimingError("WhisperGPU alignment environment not configured")
    return python, script


def _terminate_worker_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        # The isolated worker launches whisper and DirectML children. Stop the
        # entire tree before releasing the processing lock or removing temp files.
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        import signal
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def _generate_english_timing(audio: Path, cli: str, model: Path, ffmpeg: str,
                             timeout: int, cancelled, phase_changed) -> dict[str, Any]:
    """English: explicit Whisper Vulkan word timestamps, without PT aligner."""
    ffmpeg_bin = _checked_executable(ffmpeg, "ffmpeg")
    with tempfile.TemporaryDirectory(prefix="n3lx-english-") as tmp:
        root = Path(tmp)
        wav = root / "vocals16.wav"
        prefix = root / "transcription"
        if phase_changed: phase_changed("prepare")
        code = _run_command([ffmpeg_bin, "-nostdin", "-v", "error", "-y", "-i", str(audio),
                             "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
                            timeout=180, cancelled=cancelled)
        if code or not wav.is_file(): raise KaraokeTimingError("ffmpeg failed to prepare vocal audio")
        if phase_changed: phase_changed("transcribe")
        log_path = root / "vulkan.log"
        with log_path.open("w", encoding="utf-8") as log:
            if cancelled is not None and cancelled():
                raise KaraokeTimingError("karaoke generation cancelled")
            proc = subprocess.Popen([cli, "-m", str(model), "-f", str(wav), "-l", "en", "-t", "6",
                                     "-dev", "0", "-ml", "1", "-sow", "-ojf", "-of", str(prefix)],
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=os.name != "nt")
            started = time.monotonic()
            try:
                while proc.poll() is None:
                    if cancelled is not None and cancelled(): raise KaraokeTimingError("karaoke generation cancelled")
                    if time.monotonic() - started > timeout: raise KaraokeTimingError("karaoke worker exceeded its timeout")
                    time.sleep(.3)
                code = proc.returncode
            finally:
                _terminate_worker_tree(proc)
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        if code or not re.search(r"use gpu\s*=\s*1", log_text) or "using Vulkan0 backend" not in log_text:
            raise KaraokeTimingError("English Vulkan recognition failed or GPU not verified")
        output = prefix.with_suffix(".json")
        if not output.is_file() or output.stat().st_size > MAX_BYTES:
            raise KaraokeTimingError("Whisper did not produce bounded JSON")
        try: result = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc: raise KaraokeTimingError("Whisper returned unreadable JSON") from exc
        if phase_changed: phase_changed("finalize")
        timing = normalize_timing(result)
        if timing.get("language") != "en": raise KaraokeTimingError("Whisper returned unexpected language")
        timing.update({"lrc_preview": enhanced_lrc(timing["words"]), "requested_device": "vulkan_device_0",
                       "gpu_verified": True, "alignment_backend": "whisper_word_timestamps"})
        return timing


def generate_timing(
    audio: Path, *, whisper_cli: str, model: Path, ffmpeg: str = "ffmpeg",
    timeout: int = 3600,
    cancelled: Callable[[], bool] | None = None,
    phase_changed: Callable[[str], None] | None = None,
    language: str = "pt",
) -> dict[str, Any]:
    """Recognize vocals in the selected language with an explicit GPU route."""
    audio, model = Path(audio), Path(model)
    if not audio.is_file() or not model.is_file():
        raise KaraokeTimingError("audio or Whisper model not found")
    cli = _checked_executable(whisper_cli, "whisper-cli")
    _checked_executable(ffmpeg, "ffmpeg")
    if language == "en":
        return _generate_english_timing(audio, cli, model, ffmpeg, timeout, cancelled, phase_changed)
    if language != "pt":
        raise KaraokeTimingError("unsupported karaoke language")
    python, worker = aligned_worker_resources()
    model_name = model.stem.removeprefix("ggml-")
    if model_name not in {"large-v3", "medium"}:
        raise KaraokeTimingError("unsupported Whisper model")
    with tempfile.TemporaryDirectory(prefix="n3lx-whispergpu-") as tmp:
        output = Path(tmp)
        logfile = output / "worker.log"
        command = [str(python), str(worker), str(audio), "--model", model_name,
                   "--whisper-model", str(model), "--whisper-cli", cli,
                   "--device", "vulkan", "--gpu", "0", "--language", "pt",
                   "--threads", "6", "--no-diarize", "--no-preload-align",
                   "--output-format", "json", "--output-profile", "quality",
                   "--output-dir", str(output)]
        env = os.environ.copy()
        env.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                    "HF_HUB_DISABLE_TELEMETRY": "1", "PYTHONIOENCODING": "utf-8",
                    "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"})
        if phase_changed:
            phase_changed("prepare")
        with logfile.open("w", encoding="utf-8") as log:
            if cancelled is not None and cancelled():
                raise KaraokeTimingError("karaoke generation cancelled")
            proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                    env=env, start_new_session=os.name != "nt")
            started = time.monotonic()
            phase = "prepare"
            try:
                while proc.poll() is None:
                    if cancelled is not None and cancelled():
                        raise KaraokeTimingError("karaoke generation cancelled")
                    if time.monotonic() - started > timeout:
                        raise KaraokeTimingError("karaoke worker exceeded its timeout")
                    # Only phase markers are read; no transcript text is logged.
                    text = logfile.read_text(encoding="utf-8", errors="replace")
                    current = "align" if "[3/4]" in text else "transcribe" if "[2/4]" in text else "prepare"
                    if current != phase and phase_changed:
                        phase_changed(current)
                    phase = current
                    time.sleep(0.3)
                code = proc.returncode
            finally:
                _terminate_worker_tree(proc)
        if code != 0:
            raise KaraokeTimingError(f"WhisperGPU alignment failed (exit {code})")
        results = list(output.glob("*.integrado.json"))
        reports = list(output.glob("*.qualidade.json"))
        if len(results) != 1 or len(reports) != 1 or results[0].stat().st_size > MAX_BYTES or reports[0].stat().st_size > MAX_BYTES:
            raise KaraokeTimingError("WhisperGPU did not produce bounded JSON and quality report")
        try:
            result = json.loads(results[0].read_text(encoding="utf-8"))
            report = json.loads(reports[0].read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise KaraokeTimingError("WhisperGPU returned unreadable JSON") from exc
        if (report.get("etapas", {}).get("alinhamento") != "ok" or
            report.get("backend_alinhamento") != "onnx_directml_confirmado" or
            report.get("gpu_reconhecimento") != "vulkan_confirmado_pelo_log"):
            raise KaraokeTimingError("Vulkan recognition or DirectML alignment not verified")
        if phase_changed:
            phase_changed("finalize")
        timing = normalize_timing(result)
        timing["lrc_preview"] = enhanced_lrc(timing["words"])
        timing["requested_device"] = "vulkan_device_0"
        timing["gpu_verified"] = True
        timing["alignment_backend"] = "onnx_directml_confirmado"
        timing["alignment_alerts"] = report.get("total_alertas")
        return timing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="N3LX isolated karaoke timing")
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--whisper-cli", required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)
    if args.output.is_file() and not args.replace:
        parser.error("output exists; use --replace to preserve its previous version")
    try:
        timing = generate_timing(
            args.audio, whisper_cli=args.whisper_cli,
            model=args.model, ffmpeg=args.ffmpeg,
        )
        backup = store_timing(args.output, timing, replace=args.replace)
    except (KaraokeTimingError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        parser.exit(2, f"KARAOKE_TIMING_FAILED: {exc}\n")
    print(json.dumps({
        "state": "generated", "words": len(timing["words"]),
        "output": str(args.output),
        "backup": str(backup) if backup else None, "gpu_verified": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
