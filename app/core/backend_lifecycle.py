"""Opt-in local lifecycle control. Installed only by the controlled launcher."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse


def source_hashes(root: Path) -> dict[str, str]:
    names = (
        "app/main.py",
        "app/core/backend_lifecycle.py",
        "app/controlled_server.py",
        "app/api/karaoke.py",
        "app/pipeline/karaoke_timing.py",
        "app/pipeline/karaoke_diagnostics.py",
    )
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}


def busy_reasons() -> list[str]:
    from app.core import registry
    from app.core.stems_location import is_relocating
    from app.pipeline import guitar_detail, jobqueue, lyrics_retime, runner

    reasons = []
    if runner._pipeline_lock.locked():
        reasons.append("pipeline")
    with jobqueue._lock:
        if jobqueue._queue or jobqueue._running_id:
            reasons.append("queue")
    with lyrics_retime._RUNS_LOCK:
        if any(run.state == "running" for run in lyrics_retime._RUNS.values()):
            reasons.append("lyrics_or_karaoke")
    if any(
        run.status in {"running", "queued", "cancelling"} for run in guitar_detail._runs.values()
    ):
        reasons.append("guitar")
    if any(
        job.status in {"queued", "processing", "downloading", "analyzing", "separating"}
        or job.vocal_split == "running"
        for job in registry.all_jobs().values()
    ):
        reasons.append("jobs")
    with registry._lock:
        if any(proc.poll() is None for proc in registry._procs.values()):
            reasons.append("workers")
    if is_relocating():
        reasons.append("relocation")
    return reasons


def install_control(app, *, token: str, identity: dict, stop, busy=busy_reasons):
    """Drain all HTTP requests before checking workers, then ask Uvicorn to exit.

    A bearer token plus loopback peer is required. Browser Origin is rejected.
    No OS signals or process termination are used. In-flight streaming responses
    count as activity until their final body is sent.
    """
    if len(token) < 32:
        raise ValueError("lifecycle token is too short")
    state = {"draining": False, "inflight": 0}
    prefix = "/api/backend-control"

    class ControlMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                return await self.app(scope, receive, send)
            request = Request(scope, receive)
            path = scope.get("path", "")
            if path.startswith(prefix):
                authenticated = (
                    request.client is not None
                    and request.client.host in {"127.0.0.1", "::1"}
                    and "origin" not in request.headers
                    and secrets.compare_digest(
                        request.headers.get("authorization", "").encode(),
                        ("Bearer " + token).encode(),
                    )
                )
                if not authenticated:
                    response = JSONResponse({"detail": "unauthorized"}, status_code=401)
                elif path == prefix + "/status" and request.method == "GET":
                    response = JSONResponse({**identity, **state, "busy": busy()})
                elif path == prefix + "/stop" and request.method == "POST":
                    if state["draining"]:
                        response = JSONResponse({"detail": "already stopping"}, status_code=409)
                    else:
                        state["draining"] = True
                        try:
                            reasons = busy()
                            if reasons or state["inflight"]:
                                state["draining"] = False
                                response = JSONResponse(
                                    {
                                        "detail": "busy",
                                        "busy": reasons,
                                        "requests": state["inflight"],
                                    },
                                    status_code=409,
                                )
                            else:
                                response = JSONResponse(
                                    {"state": "stopping", "pid": identity["pid"]}, status_code=202
                                )
                                asyncio.get_running_loop().call_later(0.1, stop)
                        except Exception:
                            state["draining"] = False
                            raise
                else:
                    response = JSONResponse({"detail": "not found"}, status_code=404)
                response.headers["Cache-Control"] = "no-store"
                return await response(scope, receive, send)
            if state["draining"]:
                return await JSONResponse({"detail": "backend stopping"}, status_code=503)(
                    scope, receive, send
                )
            state["inflight"] += 1
            try:
                await self.app(scope, receive, send)
            finally:
                state["inflight"] -= 1

    app.add_middleware(ControlMiddleware)
    return state
