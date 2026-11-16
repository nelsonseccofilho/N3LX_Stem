from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app.core.models import Job, _set
from app.core.processing_progress import begin_step, consume_progress, snapshot, warn_step
from app.core.worker_progress import report_iterations, run_progress_worker


def test_steps_count_completed_work_without_inventing_a_percent():
    job = Job(id="abcdef123456", separation_profile="complete", status="analyzing")
    begin_step(job, "prepare")
    begin_step(job, "analyze")
    value = snapshot(job)
    assert value["step_number"] == 2 and value["total_steps"] == 6
    assert value["fraction"] is None and value["completed_steps"] == 1
    assert job.to_queue_state()["processing"]["step"] == "analyze"
    assert job.progress_indeterminate
    consume_progress(job, '@@PROGRESS@@{"fraction":0.4}')
    assert snapshot(job)["fraction"] == 0.4 and not job.progress_indeterminate
    assert Job.from_record(job.to_record()).processing == job.processing


def test_warning_cancel_and_finished_states_remain_truthful():
    job = Job(id="abcdef123456", separation_profile="complete", status="separating")
    begin_step(job, "drums")
    warn_step(job)
    begin_step(job, "reconstruct")
    _set(job, status="cancelled")
    value = snapshot(job)
    assert value["steps"][3]["state"] == "warning"
    assert value["steps"][4]["state"] == "cancelled"
    assert value["steps"][5]["state"] == "pending"
    assert value["fraction"] is None
    assert value["elapsed_seconds"] == snapshot(job)["elapsed_seconds"]


def test_basic_plan_and_retry_reset_do_not_inherit_old_completion():
    job = Job(id="abcdef123456", status="separating")
    begin_step(job, "finalize")
    _set(job, status="done")
    assert snapshot(job)["completed_steps"] == 4
    assert snapshot(job)["fraction"] == 1
    begin_step(job, "prepare")
    _set(job, status="analyzing")
    value = snapshot(job)
    assert value["completed_steps"] == 0 and value["fraction"] is None
    assert not snapshot(Job(id="abcdef123456"))


def test_iteration_protocol_counts_all_passes_and_restores_the_library(capsys):
    def original(value):
        return value

    module = SimpleNamespace(tqdm=original)
    with report_iterations(module, passes=2):
        assert list(module.tqdm(range(2))) == [0, 1]
        assert list(module.tqdm(range(3))) == [0, 1, 2]
    records = [
        json.loads(line[len("@@PROGRESS@@") :]) for line in capsys.readouterr().err.splitlines()
    ]
    assert records[0]["fraction"] == 0 and records[-1]["fraction"] == 1
    assert [r["fraction"] for r in records] == sorted(r["fraction"] for r in records)
    assert records[-1]["completed"] == records[-1]["total"] == 3
    assert module.tqdm is original
    with pytest.raises(RuntimeError), report_iterations(module):
        raise RuntimeError("model failed")
    assert module.tqdm is original


def test_invalid_worker_counter_never_changes_the_visible_percent():
    job = Job(id="abcdef123456", status="separating")
    begin_step(job, "separate")
    for line in ('@@PROGRESS@@{"fraction":2}', '@@PROGRESS@@{"fraction":NaN}', "@@PROGRESS@@bad"):
        assert consume_progress(job, line)
    assert snapshot(job)["fraction"] is None
    assert not consume_progress(job, "a diagnostic line")


def test_streamed_child_progress_and_timeout_are_observable():
    job = Job(id="abcdef123456", status="separating")
    job.separation_profile = "complete"
    begin_step(job, "drums")
    result = run_progress_worker(
        job,
        [
            sys.executable,
            "-u",
            "-c",
            "import sys; print('@@PROGRESS@@'+chr(123)+chr(34)+'fraction'+chr(34)+':0.5'+chr(125),file=sys.stderr)",
        ],
        5,
    )
    assert result.returncode == 0 and snapshot(job)["fraction"] == 0.5
    with pytest.raises(subprocess.TimeoutExpired):
        run_progress_worker(job, [sys.executable, "-c", "import time; time.sleep(10)"], 0.05)


def test_old_extraction_keeps_seven_steps_and_new_pipeline_exposes_guitar_device():
    # Old persisted jobs remain readable using the historic seven-step plan.
    old = Job(
        id="abcdef123456", status="done", separation_profile="complete",
        processing={"step": "finalize", "started_at": 1, "step_started_at": 2},
    )
    old_state = snapshot(old)
    assert old_state is not None
    assert old_state["total_steps"] == 7
    assert "guitars" not in [s["id"] for s in old_state["steps"]]

    # New jobs no longer launch an automatic guitar or vocal pass.
    job = Job(id="abcdef123456", status="separating", separation_profile="complete")
    begin_step(job, "prepare")
    begin_step(job, "drums")
    state = snapshot(job)
    assert state is not None
    assert state["step"] == "drums"
    assert [s["id"] for s in state["steps"]] == [
        "prepare", "analyze", "separate", "drums", "reconstruct", "finalize",
    ]
    assert state["fraction"] is None


def test_saved_eight_step_plan_keeps_its_original_order():
    from app.core.processing_progress import PREVIOUS_COMPLETE_STEPS

    job = Job(
        id="abcdef123456", status="done", separation_profile="complete",
        processing={
            "step": "finalize", "plan": list(PREVIOUS_COMPLETE_STEPS),
            "started_at": 1, "step_started_at": 2,
        },
    )
    restored = Job.from_record(job.to_record())
    historical = snapshot(restored)
    assert historical is not None
    assert [s["id"] for s in historical["steps"]] == list(PREVIOUS_COMPLETE_STEPS)
    assert historical["completed_steps"] == 8

    # A *new processing attempt* starts with today's six-step plan; the saved
    # historical record above was verified before the reset.
    begin_step(restored, "prepare")
    restarted = snapshot(restored)
    assert restarted is not None
    assert [s["id"] for s in restarted["steps"]] == [
        "prepare", "analyze", "separate", "drums", "reconstruct", "finalize",
    ]
    assert restarted["total_steps"] == 6
