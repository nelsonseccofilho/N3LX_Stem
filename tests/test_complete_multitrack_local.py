from __future__ import annotations

import json
import shutil
import subprocess

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.core.config import STEM_NAMES
from app.core.models import Job, JobCancelled
from app.core.studio import DRUM_STEMS
from app.pipeline import complete_multitrack as mod


@pytest.fixture
def audio(tmp_path, monkeypatch):
    stems = tmp_path / "stems"
    stems.mkdir()
    t = np.arange(4096) / 44100
    for i, name in enumerate(STEM_NAMES, 1):
        signal = 0.025 * np.sin(2 * np.pi * i * 110 * t)
        sf.write(
            stems / (name + ".wav"),
            np.column_stack([signal, signal * 0.9]),
            44100,
            subtype="PCM_24",
        )
    source = tmp_path / "source.wav"
    total = sum(sf.read(stems / (n + ".wav"), always_2d=True)[0] for n in STEM_NAMES)
    sf.write(source, total, 44100, subtype="FLOAT")

    def decode(job, cmd, timeout):
        shutil.copy2(source, cmd[-1])
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(mod, "run_registered", decode)
    return source, stems


def test_complete_pipeline_reconstructs_audio_and_excludes_parents(audio, monkeypatch):
    source, stems = audio

    def vocals(job, directory):
        data, sr = sf.read(directory / "vocals.wav", always_2d=True)
        for name, gain in zip(mod.VOICE_STEMS, [0.85, 0.12], strict=True):
            # A slightly short output verifies padding without shifting its start.
            sf.write(directory / (name + ".wav"), data[:-3] * gain, sr, subtype="PCM_24")

    def drums(job, directory, scratch):
        data, sr = sf.read(directory / "drums.wav", always_2d=True)
        for name in DRUM_STEMS:
            sf.write(scratch / (name + ".wav"), data * 0.15, sr, subtype="PCM_24")

    monkeypatch.setattr(mod, "split_vocals", vocals)
    monkeypatch.setattr(mod, "_split_drums", drums)
    job = Job(id="abcdef123456", separation_profile="complete")
    mod.complete_multitrack(job, source, stems)
    layout = json.loads((stems.parent / "studio.json").read_text(encoding="utf-8"))
    names = layout["active_names"]
    assert len(names) == 15 and "vocals" not in names and "drums" not in names
    total = sum(sf.read(stems / (n + ".wav"), always_2d=True)[0] for n in names)
    original, _ = sf.read(source, always_2d=True)
    assert np.max(np.abs(total - original)) < 1e-7
    assert len({sf.info(stems / (n + ".wav")).frames for n in names}) == 1
    assert job.vocal_split == "done" and not job.separation_warnings


def test_optional_model_failures_keep_base_groups_and_report_warnings(audio, monkeypatch):
    source, stems = audio

    def fail(*args):
        raise RuntimeError("model failure")

    monkeypatch.setattr(mod, "split_vocals", fail)
    monkeypatch.setattr(mod, "_split_drums", fail)
    job = Job(id="abcdef123456", separation_profile="complete")
    mod.complete_multitrack(job, source, stems)
    assert job.vocal_split == "error" and len(job.separation_warnings) == 2
    assert set(STEM_NAMES) <= set(mod.active_names(stems))
    layout = json.loads((stems.parent / "studio.json").read_text(encoding="utf-8"))
    assert "Atenção" in layout["notice"]
    assert len(layout["active_names"]) == 7


def test_cancellation_never_becomes_an_optional_warning(audio, monkeypatch):
    source, stems = audio

    def cancel(*args):
        raise JobCancelled()

    monkeypatch.setattr(mod, "split_vocals", cancel)
    job = Job(id="abcdef123456", separation_profile="complete")
    with pytest.raises(JobCancelled):
        mod.complete_multitrack(job, source, stems)
    assert not (stems.parent / "studio.json").exists()


def test_default_profile_is_persisted_and_captured_on_submission(monkeypatch):
    import app.api.jobs as jobs
    from app.core import settings
    from app.main import app

    captured = []
    monkeypatch.setattr(
        jobs, "registry_register_if_capacity", lambda job, limit: captured.append(job) or True
    )
    monkeypatch.setattr(jobs, "registry_persist", lambda *a: None)
    monkeypatch.setattr(jobs.jobqueue, "enqueue", lambda *a: None)
    client = TestClient(app)
    response = client.post("/api/settings", json={"separation_profile": "complete"})
    assert response.status_code == 200 and response.json()["separation_profile"] == "complete"
    monkeypatch.setattr(settings, "_state", None)
    assert settings.get_separation_profile() == "complete"
    response = client.post(
        "/api/jobs", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "stems": ["bass"]}
    )
    assert response.status_code == 200
    assert captured[0].separation_profile == "complete"
    assert set(captured[0].selected_stems) == set(STEM_NAMES)
    settings.set_separation_profile("standard")
    assert captured[0].separation_profile == "complete"
    assert Job.from_record(captured[0].to_record()).separation_profile == "complete"
    assert Job.from_record({"id": "abcdef123456"}).separation_profile == "standard"
    assert client.post("/api/settings", json={"separation_profile": "bad"}).status_code == 422


def test_additional_passes_do_not_claim_a_completed_percentage():
    job = Job(id="abcdef123456", separation_profile="complete", status="separating", progress=1.0)
    job.stage_message = "Separating six drum pieces (CPU)..."
    assert job.to_state()["progress_indeterminate"]
    assert job.to_queue_state()["progress_indeterminate"]
    job.status = "done"
    assert not job.to_state()["progress_indeterminate"]


def test_already_cancelled_job_never_launches_an_extra_model(audio, monkeypatch):
    source, stems = audio

    def unexpected(*args):
        pytest.fail("Cancelled job must not launch a worker")

    monkeypatch.setattr(mod, "split_vocals", unexpected)
    job = Job(id="abcdef123456", separation_profile="complete", cancel_requested=True)
    with pytest.raises(JobCancelled):
        mod.complete_multitrack(job, source, stems)


def test_launcher_profile_default_respects_saved_choice(monkeypatch):
    from app.core import settings

    monkeypatch.setattr(settings, "_ensure", lambda: {})
    monkeypatch.setenv("STEMDECK_SEPARATION_PROFILE", "complete")
    assert settings.get_separation_profile() == "complete"
    monkeypatch.setattr(settings, "_ensure", lambda: {"separation_profile": "standard"})
    assert settings.get_separation_profile() == "standard"
    monkeypatch.setattr(settings, "_ensure", lambda: {})
    monkeypatch.setenv("STEMDECK_SEPARATION_PROFILE", "invalid")
    assert settings.get_separation_profile() == "standard"
