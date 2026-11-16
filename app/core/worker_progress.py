"""Progress protocol for isolated model workers; counts completed iterations."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections import deque
from contextlib import contextmanager


@contextmanager
def report_iterations(target, *, passes: int = 1):
    original = target.tqdm
    pass_number = 0

    def measured(iterable, *args, **kwargs):
        nonlocal pass_number
        part = pass_number
        pass_number += 1
        try:
            total = len(iterable)
        except TypeError:
            total = None

        def emit(completed):
            if not total or part >= passes:
                return
            record = {
                "fraction": (part + completed / total) / passes,
                "completed": completed,
                "total": total,
                "pass": part + 1,
                "passes": passes,
            }
            print("@@PROGRESS@@" + json.dumps(record), file=sys.stderr, flush=True)

        emit(0)
        for completed, item in enumerate(iterable, 1):
            yield item
            emit(completed)

    target.tqdm = measured
    try:
        yield
    finally:
        target.tqdm = original


def run_progress_worker(job, cmd, timeout):
    from app.core.processing_progress import consume_progress
    from app.core.registry import set_proc

    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8:replace",
        "STEMDECK_PARENT_PID": str(os.getpid()),
    }
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    set_proc(job.id, proc)
    tail = deque(maxlen=40)

    def read():
        for line in proc.stderr:
            if not consume_progress(job, line.strip()):
                tail.append(line)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
            raise
    finally:
        reader.join(timeout=10)
        set_proc(job.id, None)
    return subprocess.CompletedProcess(cmd, code, b"", "".join(tail).encode("utf-8"))
