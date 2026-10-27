"""On-demand task safety: no Whisper model or private audio needed."""
import asyncio
import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace

from app.api import karaoke as k


def _run(state="running"):
    return SimpleNamespace(state=state, started=False, ended=Event(), cancel=Event())


def _job(tmp_path: Path):
    job = SimpleNamespace(id="abcdef123456", status="done")
    work = tmp_path / job.id
    (work / "stems").mkdir(parents=True)
    (work / "stems" / "vocals.wav").write_bytes(b"unchanged audio")
    (work / "lyrics.json").write_text('{"manual":"preserve"}', encoding="utf-8")
    return job, work


def _fake_timing(*args, **kwargs):
    return {
        "v": 1, "engine": "whisper.cpp", "timing_status": "machine_unverified",
        "words": [
            {"text": "Eu", "start": 0, "end": .2},
            {"text": "vou", "start": .3, "end": .5},
            {"text": "cantar", "start": .6, "end": 1.0},
        ],
        "lrc_preview": "[00:00.00]<00:00.00>Eu",
    }


def test_karaoke_generation_does_not_touch_lyrics_or_stems(tmp_path, monkeypatch):
    job, work = _job(tmp_path)
    run = _run()
    monkeypatch.setattr(k, "registry_get", lambda _id: job)
    monkeypatch.setattr(k, "generate_timing", _fake_timing)
    monkeypatch.setattr(k, "_pipeline_lock", asyncio.Lock())
    before = (work / "stems" / "vocals.wav").read_bytes()
    asyncio.run(k._generate(job, work, run, False, "worker", Path("model"), "ffmpeg"))
    assert run.ended.is_set() and run.state == "done"
    assert json.loads((work / "lyrics_timing.json").read_text())["words"][2]["text"] == "cantar"
    assert (work / "lyrics.json").read_text() == '{"manual":"preserve"}'
    assert (work / "stems" / "vocals.wav").read_bytes() == before


def test_cancelled_before_gpu_lock_writes_nothing(tmp_path, monkeypatch):
    job, work = _job(tmp_path)
    run = _run()
    run.cancel.set()
    monkeypatch.setattr(k, "registry_get", lambda _id: job)
    monkeypatch.setattr(k, "_pipeline_lock", asyncio.Lock())
    asyncio.run(k._generate(job, work, run, False, "worker", Path("model"), "ffmpeg"))
    assert run.ended.is_set() and run.state == "idle"
    assert not (work / "lyrics_timing.json").exists()
