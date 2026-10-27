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
