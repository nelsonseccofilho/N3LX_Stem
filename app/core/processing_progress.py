"""Measured stage progress, separate from estimated overall completion."""

from __future__ import annotations

import math
import time

from app.core.models import FINISHED_STATUSES, Job, _set

COMPLETE_STEPS = ("prepare", "analyze", "separate", "vocals", "drums", "reconstruct", "finalize")
BASIC_STEPS = ("prepare", "analyze", "separate", "finalize")


def begin_step(job: Job, step: str) -> None:
    now = time.time()
    value = {} if step == "prepare" else dict(job.processing)
    if value.get("step") == step:
        return
    finished = dict(value.get("finished", {}))
    if value.get("step"):
        finished.setdefault(value["step"], "done")
    value.update(
        step=step,
        fraction=None,
        started_at=value.get("started_at", now),
        step_started_at=now,
        finished=finished,
        counters=None,
    )
    _set(job, processing=value)


def warn_step(job: Job) -> None:
    value = dict(job.processing)
    if value.get("step"):
        value["finished"] = {**value.get("finished", {}), value["step"]: "warning"}
        _set(job, processing=value)


def clear_fraction(job: Job) -> None:
    if job.processing:
        _set(job, processing={**job.processing, "fraction": None, "counters": None})


def consume_progress(job: Job, line: str) -> bool:
    if not line.startswith("@@PROGRESS@@"):
        return False
    import json

    try:
        counters = json.loads(line[len("@@PROGRESS@@") :])
        fraction = float(counters["fraction"])
        if not math.isfinite(fraction) or not 0 <= fraction <= 1:
            return True
        if job.processing and job.status not in FINISHED_STATUSES:
            value = {**job.processing, "fraction": fraction, "counters": counters}
            _set(job, processing=value)
    except (ValueError, KeyError, TypeError):
        pass
    return True


def snapshot(job: Job) -> dict | None:
    value = job.processing
    if not value or not isinstance(value, dict):
        return None
    steps = COMPLETE_STEPS if job.separation_profile == "complete" else BASIC_STEPS
    current = value.get("step")
    if current not in steps:
        return None
    index = steps.index(current)
    terminal = job.status in FINISHED_STATUSES
    done = job.status == "done"
    end = value.get("finished_at", time.time())
    finished = value.get("finished", {})
    states = []
    for i, name in enumerate(steps):
        state = finished.get(name, "done" if done or i < index else "pending")
        if i == index and not done:
            state = job.status if terminal else "running"
        states.append({"id": name, "state": state})
    return {
        "step": current,
        "step_number": index + 1,
        "total_steps": len(steps),
        "completed_steps": sum(s["state"] in ("done", "warning") for s in states),
        "fraction": 1.0 if done else value.get("fraction"),
        "started_at": value.get("started_at"),
        "step_started_at": value.get("step_started_at"),
        "elapsed_seconds": max(0, end - value.get("started_at", end)),
        "step_elapsed_seconds": max(0, end - value.get("step_started_at", end)),
        "terminal": terminal,
        "steps": states,
        "counters": value.get("counters"),
    }
