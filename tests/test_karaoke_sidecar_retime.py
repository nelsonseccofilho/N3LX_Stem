"""Safe reuse of existing WhisperX timestamps for corrected PT/EN lyrics.

Pure fixtures: no downloads, GPU work, transcription or personal audio.
"""
import json
import os
from pathlib import Path

import pytest

from app.pipeline import lyrics_retime as retime


@pytest.fixture
def job_dir(tmp_path: Path) -> Path:
    stems = tmp_path / "stems"
    stems.mkdir()
    (stems / "vocals.wav").write_bytes(b"fixture vocals")
    return tmp_path


def example_timing(job_dir: Path, language: str) -> dict:
    stamp = retime._vocals_stamp(job_dir)
    assert stamp
    return {
        "v": 1,
        "engine": "whisperx",
        "language": language,
        "alignment_backend": "cpu",
        "gpu_verified": True,
        "vocals": stamp,
        "words": [
            {"text": "A", "start": 22.0, "end": 22.2},
            {"text": "first", "start": 22.3, "end": 22.6},
            {"text": "line", "start": 22.7, "end": 23.0},
        ],
    }


@pytest.mark.parametrize("language", ["pt", "en"])
def test_reuses_verified_language_specific_words(job_dir: Path, language: str):
    (job_dir / "lyrics_timing.json").write_text(
        json.dumps(example_timing(job_dir, language)), encoding="utf-8")
    found = retime.read_karaoke_transcript(job_dir, language)
    assert found and found["language"] == language
    assert found["words"][0] == {"text": "A", "start": 22.0, "end": 22.2}
    assert found["refined"] is True


def test_missing_or_stale_vocals_signature_is_rejected(job_dir: Path):
    path = job_dir / "lyrics_timing.json"
    data = example_timing(job_dir, "pt")
    data["vocals"][0] += 2
    path.write_text(json.dumps(data), encoding="utf-8")
    assert retime.read_karaoke_transcript(job_dir, "pt") is None


def test_other_language_never_reuses_wrong_words(job_dir: Path):
    (job_dir / "lyrics_timing.json").write_text(
        json.dumps(example_timing(job_dir, "en")), encoding="utf-8")
    assert retime.read_karaoke_transcript(job_dir, "pt") is None


@pytest.mark.parametrize("field,value", [
    ("engine", "whisper.cpp"),
    ("gpu_verified", False),
    ("alignment_backend", "whisper_word_timestamps"),
])
def test_rejects_non_whisperx_backend(job_dir: Path, field, value):
    data = example_timing(job_dir, "pt")
    data[field] = value
    (job_dir / "lyrics_timing.json").write_text(json.dumps(data), encoding="utf-8")
    assert retime.read_karaoke_transcript(job_dir, "pt") is None


def test_non_monotonic_word_times_are_rejected(job_dir: Path):
    data = example_timing(job_dir, "pt")
    data["words"][2]["start"] = 20.0
    (job_dir / "lyrics_timing.json").write_text(json.dumps(data), encoding="utf-8")
    assert retime.read_karaoke_transcript(job_dir, "pt") is None


def test_legacy_sidecar_must_be_newer_than_vocals(job_dir: Path):
    data = example_timing(job_dir, "pt")
    del data["vocals"]
    path = job_dir / "lyrics_timing.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert retime.read_karaoke_transcript(job_dir, "pt") is not None
    vocal = job_dir / "stems" / "vocals.wav"
    later = path.stat().st_mtime_ns + 2_000_000_000
    os.utime(vocal, ns=(later, later))
    assert retime.read_karaoke_transcript(job_dir, "pt") is None


def test_reusing_sidecar_does_not_spawn_asr(monkeypatch, job_dir: Path):
    (job_dir / "lyrics_timing.json").write_text(
        json.dumps(example_timing(job_dir, "pt")), encoding="utf-8")

    def must_not_transcribe(*args, **kwargs):
        raise AssertionError("ASR must not run when cached WhisperX words are valid")

    monkeypatch.setattr(retime, "_hear", must_not_transcribe)
    seen = []
    words, refined = retime._transcribe(
        None, job_dir, "pt", cancelled=lambda: False,
        report=lambda phase, value: seen.append((phase, value)))
    assert len(words) == 3 and refined is True
    assert seen == [("transcribe", 100)]
