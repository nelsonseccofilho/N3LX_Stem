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
import uuid
from datetime import datetime, timezone
from pathlib import Path
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


def _parse_whisper_cpp(source: dict[str, Any]) -> list[dict[str, Any]]:
    chunks = source.get("transcription")
    if not isinstance(chunks, list) or len(chunks) > MAX_WORDS * 2:
        raise KaraokeTimingError("whisper.cpp transcription must be a bounded list")
    words: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict) or not isinstance(chunk.get("offsets"), dict):
            raise KaraokeTimingError(f"invalid transcription chunk {index}")
        offsets = chunk["offsets"]
        start = _finite(offsets.get("from"), "offset.from") / 1000
        end = _finite(offsets.get("to"), "offset.to") / 1000
        if end < start:
            raise KaraokeTimingError("segment ends before it starts")
        text = _clean_text(chunk.get("text"))
        if not text or _SPECIAL.fullmatch(text):
            continue
        # -ml 1 yields individual words or punctuation; never interpolate
        # unknown individual timestamps from a multiword segment.
        if len(text.split()) > 1:
            raise KaraokeTimingError("multiword segment: use whisper-cli -ml 1")
        if not _WORD.search(text):
            if words:
                words[-1]["text"] += text
                words[-1]["end"] = max(words[-1]["end"], end)
            continue
        words.append({"text": text, "start": start, "end": end})
        if len(words) > MAX_WORDS:
            raise KaraokeTimingError("too many words")
    return words


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
        words = _parse_whisper_cpp(source)
        engine = "whisper.cpp"
    elif "segments" in source:
        words = _parse_whisperx(source)
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


def generate_timing(
    audio: Path, *, whisper_cli: str, model: Path, ffmpeg: str = "ffmpeg",
    timeout: int = 3600,
) -> dict[str, Any]:
    """Process isolated audio, with no automatic model install or CPU fallback."""
    audio, model = Path(audio), Path(model)
    if not audio.is_file() or not model.is_file():
        raise KaraokeTimingError("audio or Whisper model not found")
    cli = _checked_executable(whisper_cli, "whisper-cli")
    ffmpeg_bin = _checked_executable(ffmpeg, "ffmpeg")
    with tempfile.TemporaryDirectory(prefix="n3lx-karaoke-") as tmp:
        root = Path(tmp)
        wav = root / "vocals16.wav"
        result_prefix = root / "transcription"
        ff = subprocess.run(
            [ffmpeg_bin, "-nostdin", "-v", "error", "-y", "-i", str(audio),
             "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
            capture_output=True, timeout=180, check=False,
        )
        if ff.returncode or not wav.is_file():
            raise KaraokeTimingError("ffmpeg failed to prepare vocal audio")
        # Deliberately no --vad: known segment/token timestamp mapping issue.
        args = [cli, "-m", str(model), "-f", str(wav), "-l", "auto", "-t", "4",
                "-dev", "0", "-ml", "1", "-sow", "-ojf", "-of", str(result_prefix)]
        proc = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
        json_path = result_prefix.with_suffix(".json")
        if proc.returncode or not json_path.is_file():
            raise KaraokeTimingError("whisper-cli did not produce a valid JSON result")
        if json_path.stat().st_size > MAX_BYTES:
            raise KaraokeTimingError("Whisper JSON exceeds the size limit")
        timing = normalize_timing(json.loads(json_path.read_text(encoding="utf-8")))
        timing["requested_device"] = "vulkan_device_0"
        timing["gpu_verified"] = False  # Check independent hardware logs.
        timing["lrc_preview"] = enhanced_lrc(timing["words"])
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
