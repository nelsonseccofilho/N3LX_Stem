"""Generated lyrics are independent of user edits and source audio."""
import json
import sys

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import karaoke as k
from app.main import app
from app.pipeline import lyrics_retime
from tests.test_karaoke_service import _job


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    job, work = _job(tmp_path)
    monkeypatch.setattr(k, "JOBS_DIR", tmp_path)
    monkeypatch.setattr(k, "registry_get", lambda ident: job if ident == job.id else None)
    monkeypatch.setattr(lyrics_retime, "_RUNS", {})
    monkeypatch.setattr(k, "_karaoke_runs", {})
    (work / "lyrics_timing.json").write_text(json.dumps({"v": 1, "words": []}))
    return TestClient(app), job, work


def test_delete_is_sidecar_only_and_regeneration_can_start(prepared):
    client, job, work = prepared
    before = {p: p.read_bytes() for p in [work / "lyrics.json", work / "stems/vocals.wav"]}
    response = client.delete(f"/api/jobs/{job.id}/karaoke/timing")
    assert response.status_code == 200
    assert not (work / "lyrics_timing.json").exists()
    assert len(list(work.glob("lyrics_timing.deleted-*.json"))) == 1
    assert all(p.read_bytes() == original for p, original in before.items())
    assert client.get(f"/api/jobs/{job.id}/karaoke/status").json()["available"] is False
    assert k.claim_run(job.id) is not None


def test_delete_refuses_a_running_lyrics_job(prepared):
    client, job, work = prepared
    assert k.claim_run(job.id)
    assert client.delete(f"/api/jobs/{job.id}/karaoke/timing").status_code == 409
    assert (work / "lyrics_timing.json").exists()
    assert not list(work.glob("lyrics_timing.deleted-*.json"))


def test_delete_refuses_symlink_paths(prepared, monkeypatch):
    client, job, work = prepared
    original = k.Path.is_symlink
    monkeypatch.setattr(k.Path, "is_symlink", lambda p: True if p.name == "lyrics_timing.json" else original(p))
    assert client.delete(f"/api/jobs/{job.id}/karaoke/timing").status_code == 409
    assert (work / "lyrics_timing.json").exists()


def test_explicit_models_are_resolved_without_silent_downgrade(tmp_path, monkeypatch):
    monkeypatch.setattr(k, "aligned_worker_resources", lambda: (tmp_path / "python", tmp_path / "worker"))
    medium = tmp_path / "ggml-medium.bin"
    large = tmp_path / "ggml-large-v3.bin"
    medium.write_bytes(b"model")
    monkeypatch.setenv("N3LX_WHISPER_CLI", sys.executable)
    monkeypatch.setenv("N3LX_WHISPER_MODEL", str(medium))
    monkeypatch.delenv("N3LX_WHISPER_LARGE_MODEL", raising=False)
    monkeypatch.delenv("N3LX_WHISPER_MEDIUM_MODEL", raising=False)
    monkeypatch.setattr(k, "ffmpeg_executable", lambda: "ffmpeg")
    with pytest.raises(HTTPException) as problem:
        k._configuration("large-v3")
    assert problem.value.status_code == 503
    large.write_bytes(b"model")
    assert k._configuration("large-v3")[1] == large
    assert k._configuration("medium")[1] == medium
    with pytest.raises(HTTPException) as problem:
        k._configuration("../../other")
    assert problem.value.status_code == 422


@pytest.mark.parametrize("outcome", ["done", "failed", "cancelled"])
def test_regeneration_removes_old_result_before_worker_and_never_reuses_it(prepared, monkeypatch, outcome):
    import asyncio
    from pathlib import Path
    from starlette.requests import Request
    from tests.test_karaoke_service import _fake_timing
    client, job, work = prepared
    original = (work / "lyrics_timing.json").read_bytes()
    preserved = {p: p.read_bytes() for p in [work / "lyrics.json", work / "stems/vocals.wav"]}
    monkeypatch.setattr(k, "_configuration", lambda name, language="pt": ("worker", Path("ggml-large-v3.bin"), "ffmpeg"))
    def generate(*args, **kwargs):
        assert not (work / "lyrics_timing.json").exists()
        kwargs["phase_changed"]("transcribe")
        if outcome == "failed":
            raise k.KaraokeTimingError("synthetic failure")
        return _fake_timing()
    monkeypatch.setattr(k, "generate_timing", generate)
    async def scenario():
        monkeypatch.setattr(k, "_pipeline_lock", asyncio.Lock())
        async def receive():
            return {"type": "http.request", "body": b'{"replace": true, "model": "large-v3"}'}
        request = Request({"type": "http", "headers": []}, receive)
        response = await k.generate_karaoke(job.id, request)
        assert response.status_code == 202
        assert not (work / "lyrics_timing.json").exists()
        status = k.karaoke_status(job.id)
        assert status["state"] == "running" and status["phase"] == "queued"
        assert status["available"] is False and status["elapsed_seconds"] >= 0
        if outcome == "cancelled":
            assert k.cancel_karaoke(job.id)["cancel_requested"]
        await asyncio.gather(*list(k._active_tasks))
    asyncio.run(scenario())
    assert list(work.glob("lyrics_timing.regenerated-*.json"))[0].read_bytes() == original
    assert all(p.read_bytes() == value for p, value in preserved.items())
    status = k.karaoke_status(job.id)
    assert status["state"] == {"cancelled": "idle"}.get(outcome, outcome)
    assert status["available"] is (outcome == "done")
    if outcome == "done":
        assert json.loads((work / "lyrics_timing.json").read_text())["model"] == "large-v3"


def test_regeneration_configuration_failure_keeps_existing_result(prepared, monkeypatch):
    client, job, work = prepared
    def unavailable(name, language="pt"):
        raise HTTPException(503, "worker unavailable")
    monkeypatch.setattr(k, "_configuration", unavailable)
    assert client.post(f"/api/jobs/{job.id}/karaoke/generate", json={"replace": True, "model": "large-v3"}).status_code == 503
    assert (work / "lyrics_timing.json").exists()
    assert not list(work.glob("lyrics_timing.regenerated-*.json"))


def test_language_validation_happens_before_old_json_is_archived(prepared):
    client, job, work = prepared
    for value in ("es", None, ["en"]):
        response = client.post(f"/api/jobs/{job.id}/karaoke/generate", json={"replace": True, "language": value})
        assert response.status_code == 422
        assert (work / "lyrics_timing.json").exists()
        assert not list(work.glob("lyrics_timing.regenerated-*.json"))


def test_english_does_not_require_portuguese_aligner(tmp_path, monkeypatch):
    model = tmp_path / "ggml-large-v3.bin"
    model.write_bytes(b"test")
    monkeypatch.setenv("N3LX_WHISPER_CLI", sys.executable)
    monkeypatch.setenv("N3LX_WHISPER_MODEL", str(model))
    monkeypatch.delenv("N3LX_WHISPER_LARGE_MODEL", raising=False)
    def missing(): raise k.KaraokeTimingError("missing aligner")
    monkeypatch.setattr(k, "aligned_worker_resources", missing)
    monkeypatch.setattr(k, "ffmpeg_executable", lambda: "ffmpeg")
    assert k._configuration("large-v3", "en")[1] == model
    with pytest.raises(HTTPException) as problem: k._configuration("large-v3", "pt")
    assert problem.value.status_code == 503


def test_english_request_reaches_worker_and_preserves_previous_json(prepared, monkeypatch):
    import asyncio
    from pathlib import Path
    from starlette.requests import Request
    from tests.test_karaoke_service import _fake_timing
    client, job, work = prepared
    old = (work / "lyrics_timing.json").read_bytes()
    selected = []
    monkeypatch.setattr(k, "_configuration", lambda name, language="pt": ("worker", Path("ggml-large-v3.bin"), "ffmpeg"))
    def generate(*args, **kwargs):
        selected.append(kwargs["language"])
        return {**_fake_timing(), "language": kwargs["language"]}
    monkeypatch.setattr(k, "generate_timing", generate)
    async def scenario():
        monkeypatch.setattr(k, "_pipeline_lock", asyncio.Lock())
        async def receive():
            return {"type": "http.request", "body": b'{"replace":true,"model":"large-v3","language":"en"}'}
        response = await k.generate_karaoke(job.id, Request({"type": "http", "headers": []}, receive))
        assert response.status_code == 202
        assert k.karaoke_status(job.id)["language"] == "en"
        await asyncio.gather(*list(k._active_tasks))
    asyncio.run(scenario())
    assert selected == ["en"]
    assert json.loads((work / "lyrics_timing.json").read_text())["language"] == "en"
    assert list(work.glob("lyrics_timing.regenerated-*.json"))[0].read_bytes() == old
