import asyncio
import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import guitar_detail as api
from app.api.stems import _parse_lane_gains
from app.core.guitar_audio import add_window, finish_windows, windows
from app.core.models import Job
from app.core.studio import read_layout
from app.pipeline import guitar_detail as service


@pytest.mark.parametrize("length", [1, 1999, 12000, 12001, 24000, 116727])
def test_overlap_add_covers_edges_and_preserves_stereo_without_seams(length):
    source = np.random.default_rng(7).normal(0, 0.1, (length, 2)).astype(np.float32)
    accumulator = np.zeros_like(source, dtype=np.float64)
    weights = np.zeros(length)
    grid = windows(length, 1000)
    for index, (start, end) in enumerate(grid):
        add_window(
            accumulator,
            weights,
            source[start:end],
            start,
            2000,
            first=index == 0,
            last=index == len(grid) - 1,
        )
        assert 0 < end - start <= 12000
    np.testing.assert_allclose(finish_windows(accumulator, weights), source, atol=3e-8)


def test_uncovered_or_nonfinite_audio_is_rejected():
    with pytest.raises(ValueError):
        finish_windows(np.ones((20, 2)), np.zeros(20))
    with pytest.raises(ValueError):
        windows(20, 1000, seconds=1, overlap=1)
    with pytest.raises(ValueError):
        add_window(
            np.zeros((20, 2)), np.zeros(20), np.full((20, 2), np.nan), 0, 0, first=True, last=True
        )


@pytest.fixture
def song(tmp_path, monkeypatch):
    job = Job(
        id="abcdef123456",
        status="done",
        title="Fixture",
        stems=[{"name": n, "url": f"/{n}.wav"} for n in ("bass", "guitar")],
    )
    directory = tmp_path / job.id
    (directory / "stems").mkdir(parents=True)
    audio = np.random.default_rng(1).normal(0, 0.1, (4096, 2)).astype(np.float32)
    sf.write(directory / "stems/guitar.wav", audio, 44100, subtype="FLOAT")
    monkeypatch.setattr(api, "JOBS_DIR", tmp_path)
    monkeypatch.setattr(api, "get", lambda key: job if key == job.id else None)
    monkeypatch.setattr("app.core.registry.get", lambda key: job if key == job.id else None)
    monkeypatch.setattr("app.core.registry.persist", lambda *args: None)
    monkeypatch.setattr("app.pipeline.collect.merge_stem_peaks", lambda *args: None)
    monkeypatch.setattr(service, "environment", lambda: (tmp_path, Path("python"), True))
    monkeypatch.setattr(service, "_runs", {})
    monkeypatch.setattr(api, "_actions", {})
    app = FastAPI()
    app.include_router(api.router)
    return job, directory, audio, TestClient(app)


def result_for(directory, audio):
    run_id = "a" * 32
    output = directory / "guitar-details" / run_id
    output.mkdir(parents=True)
    for name, factor in (("guitar_lead", 0.4), ("residual_guitar", 0.6)):
        sf.write(output / f"{name}.wav", audio * factor, 44100, subtype="FLOAT")
    receipt = {
        "status": "done",
        "run_id": run_id,
        "applied": False,
        "names": ["guitar_lead", "residual_guitar"],
        "roles": ["lead"],
        "input_sha256": hashlib.sha256((directory / "stems/guitar.wav").read_bytes()).hexdigest(),
    }
    service.atomic_json(directory / "guitar-detail.json", receipt)
    return receipt


@pytest.mark.parametrize(
    "existing_layout",
    [
        None,
        {
            "profile": "complete",
            "active_names": ["bass", "guitar"],
            "labels": {"guitar": "Minha guitarra"},
            "notice": "Keep me",
        },
    ],
)
def test_apply_and_restore_are_reversible_and_never_modify_original(song, existing_layout):
    job, directory, audio, client = song
    original_bytes = (directory / "stems/guitar.wav").read_bytes()
    original_stems = list(job.stems)
    if existing_layout:
        service.atomic_json(directory / "studio.json", existing_layout)
    receipt = result_for(directory, audio)
    response = client.post(f"/{job.id}/guitar-detail/apply")
    assert response.status_code == 200 and response.json()["applied"]
    assert read_layout(directory)["active_names"] == ["bass", *receipt["names"]]
    assert "guitar" in {stem["name"] for stem in job.stems}
    assert (directory / "stems/guitar.wav").read_bytes() == original_bytes
    assert client.post(f"/{job.id}/guitar-detail", json={"roles": ["lead"]}).status_code == 409
    assert client.post(f"/{job.id}/guitar-detail/original").status_code == 200
    assert job.stems == original_stems
    assert (directory / "stems/guitar.wav").read_bytes() == original_bytes
    for name in receipt["names"]:
        assert not (directory / "stems" / f"{name}.wav").exists()
        assert (directory / "guitar-details" / receipt["run_id"] / f"{name}.wav").is_file()
    if existing_layout:
        assert json.loads((directory / "studio.json").read_text()) == existing_layout
    else:
        assert not (directory / "studio.json").exists()


def test_changed_source_or_incomplete_results_cannot_replace_mix(song):
    job, directory, audio, client = song
    result_for(directory, audio)
    (directory / "stems/guitar.wav").write_bytes(b"changed")
    assert client.post(f"/{job.id}/guitar-detail/apply").status_code == 409
    assert not (directory / "studio.json").exists()
    assert not service.read_result(directory)["applied"]


def test_endpoints_validate_readiness_roles_and_environment(song, monkeypatch):
    job, directory, audio, client = song
    assert client.get("/bad-id/guitar-detail").status_code == 404
    assert client.post(f"/{job.id}/guitar-detail", json={"roles": []}).status_code == 422
    assert client.post(f"/{job.id}/guitar-detail", json={"roles": ["overdub"]}).status_code == 422
    monkeypatch.setattr(service, "environment", lambda: (None, None, False))
    assert client.post(f"/{job.id}/guitar-detail", json={"roles": ["lead"]}).status_code == 503
    job.trashed_at = 1
    assert client.get(f"/{job.id}/guitar-detail").status_code == 409


def test_original_guitar_cannot_be_summed_with_estimates():
    for part in service.GUITAR_LABELS:
        with pytest.raises(HTTPException) as error:
            _parse_lane_gains(f"guitar,{part}", "1,1")
        assert error.value.status_code == 422
    assert _parse_lane_gains("guitar_lead,residual_guitar", "1,1")[0] == [
        "guitar_lead",
        "residual_guitar",
    ]


def test_default_zip_and_unpitched_complement_exclude_grouped_guitar(song, monkeypatch):
    from app.api import stems as api_stems
    from app.core.config import STEM_NAMES

    job, directory, audio, _ = song
    monkeypatch.setattr(api_stems, "JOBS_DIR", directory.parent)
    monkeypatch.setattr(api_stems, "registry_get", lambda _: job)
    for name in (*STEM_NAMES, "original"):
        if name != "guitar":
            sf.write(directory / "stems" / f"{name}.wav", audio, 44100, subtype="FLOAT")
    result_for(directory, audio)
    service.apply(job, directory)
    app = FastAPI()
    app.include_router(api_stems.router)
    client = TestClient(app)
    response = client.get(f"/jobs/{job.id}/stems/all.zip")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == 3
        assert not any(name.endswith("_guitar.wav") for name in archive.namelist())
    assert client.get(f"/jobs/{job.id}/stems/all.zip?stems=guitar,guitar_lead").status_code == 422
    lanes, _ = api_stems._expand_render_lanes(
        job.id, ["original", "guitar_lead", "residual_guitar"], [1, 1, 1], [0, 0, 0]
    )
    assert not any(lane.path.name == "guitar.wav" for lane in lanes)


@pytest.mark.asyncio
async def test_worker_receipt_is_not_applied_automatically_and_concurrent_start_is_rejected(
    song, monkeypatch
):
    job, directory, audio, _ = song

    class Finished:
        returncode = 0
        stdout = asyncio.StreamReader()

        async def wait(self):
            return 0

    async def spawn(*args, **kwargs):
        output = Path(args[args.index("--output") + 1])
        output.mkdir(parents=True)
        receipt = result_for(directory, audio)
        (directory / "guitar-detail.json").unlink()
        (output / "result.json").write_text(json.dumps(receipt))
        proc = Finished()
        proc.stdout.feed_data(b'@@GUITAR@@{"phase":"done","percent":100}\n')
        proc.stdout.feed_eof()
        return proc

    monkeypatch.setattr("app.pipeline.runner._pipeline_lock", asyncio.Lock())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    run = service.start(job, directory, ["lead"])
    with pytest.raises(ValueError):
        service.start(job, directory, ["lead"])
    await run.task
    assert run.status == "done"
    assert not service.read_result(directory)["applied"]
    assert not (directory / "studio.json").exists()
    assert [s["name"] for s in job.stems] == ["bass", "guitar"]


@pytest.mark.asyncio
async def test_cancel_and_shutdown_wait_for_worker_exit(song, monkeypatch):
    job, directory, _, _ = song
    started, ended = asyncio.Event(), asyncio.Event()

    class Running:
        returncode = None
        stdout = asyncio.StreamReader()

        def terminate(self):
            self.returncode = -1
            self.stdout.feed_eof()
            ended.set()

        async def wait(self):
            await ended.wait()
            return self.returncode

    async def spawn(*args, **kwargs):
        started.set()
        return Running()

    monkeypatch.setattr("app.pipeline.runner._pipeline_lock", asyncio.Lock())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    run = service.start(job, directory, ["lead"])
    await started.wait()
    service.cancel(job.id)
    assert run.status == "cancelling"
    await service.shutdown()
    assert ended.is_set() and run.status == "cancelled"
    assert not (directory / "guitar-detail.json").exists()
