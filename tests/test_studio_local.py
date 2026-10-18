import json

import pytest
from fastapi import HTTPException

from app.api.stems import _expand_render_lanes, _parse_lane_gains, effective_pitch
from app.core.registry import _recover_done_job
from app.core.studio import DRUM_STEMS, read_layout


def test_no_parent_drums_or_master_can_be_summed_twice():
    for names in ("drums,drum_kick", "reaper_master,studio_01"):
        with pytest.raises(HTTPException) as error:
            _parse_lane_gains(names, "1,1")
        assert error.value.status_code == 422
    assert _parse_lane_gains("drum_kick,drum_snare", "1,0.8")[0] == ["drum_kick", "drum_snare"]
    assert all(effective_pitch(n, 5) == 0 for n in DRUM_STEMS)


def test_import_recovers_after_registry_loss_and_keeps_track_labels(tmp_path):
    job_dir = tmp_path / "abcdef123456"
    stems = job_dir / "stems"
    stems.mkdir(parents=True)
    (stems / "studio_01.wav").touch()
    (stems / "drum_kick.wav").touch()
    (job_dir / "metadata.json").write_text(json.dumps({"title": "REAPER session"}))
    (job_dir / "studio.json").write_text(
        json.dumps(
            {
                "labels": {"studio_01": "Bass", "../bad": "ignore"},
                "percussion_names": ["studio_01", "../bad"],
            }
        )
    )
    job = _recover_done_job(job_dir)
    assert {s["name"] for s in job.stems} == {"studio_01", "drum_kick"}
    layout = read_layout(job_dir)
    assert layout["labels"] == {"studio_01": "Bass"}
    assert layout["percussion_names"] == ["studio_01"]
    (job_dir / "studio.json").write_text("broken json")
    assert read_layout(job_dir) is None


def test_imported_percussion_stays_unpitched_in_exports(tmp_path, monkeypatch):
    import app.api.stems as mod

    job_dir = tmp_path / "abcdef123456"
    stems = job_dir / "stems"
    stems.mkdir(parents=True)
    (stems / "studio_06.wav").touch()
    (job_dir / "studio.json").write_text(json.dumps({"percussion_names": ["studio_06"]}))
    from app.core.models import Job

    monkeypatch.setattr(mod, "registry_get", lambda _: Job(id="abcdef123456", status="done"))
    monkeypatch.setattr(mod, "JOBS_DIR", tmp_path)
    lanes, _ = _expand_render_lanes("abcdef123456", ["studio_06"], [1], [5])
    assert lanes[0].pitch == 0
