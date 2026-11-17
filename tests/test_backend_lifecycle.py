import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.backend_lifecycle import busy_reasons, install_control
from scripts import backend_control as control

TOKEN = "t" * 64
AUTH = {"Authorization": "Bearer " + TOKEN}


def application(busy=lambda: []):
    app = FastAPI()

    @app.get("/normal")
    async def normal():
        return {"ok": True}

    stopped = []
    state = install_control(
        app, token=TOKEN, identity={"pid": 123}, stop=lambda: stopped.append(True), busy=busy
    )
    return app, state, stopped


@pytest.mark.parametrize(
    "host,headers",
    [
        ("127.0.0.1", {}),
        ("127.0.0.1", {"Authorization": "Bearer wrong"}),
        ("127.0.0.1", {**AUTH, "Origin": "http://localhost"}),
        ("10.0.0.1", {**AUTH, "X-Forwarded-For": "127.0.0.1"}),
    ],
)
def test_unauthorized_cannot_stop(host, headers):
    app, state, stopped = application()
    with TestClient(app, client=(host, 1234)) as client:
        assert client.post("/api/backend-control/stop", headers=headers).status_code == 401
        assert not state["draining"] and not stopped
        assert client.get("/normal").status_code == 200


def test_busy_rejects_stop_and_allows_normal_requests():
    app, state, stopped = application(lambda: ["worker"])
    with TestClient(app, client=("127.0.0.1", 1234)) as client:
        assert client.post("/api/backend-control/stop", headers=AUTH).status_code == 409
        assert client.get("/normal").status_code == 200
        assert not stopped and not state["draining"]


def test_cooperative_stop_drains_and_calls_callback():
    async def scenario():
        app, state, stopped = application()
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/backend-control/stop", headers=AUTH)
            assert response.status_code == 202
            assert (await client.get("/normal")).status_code == 503
            assert (await client.post("/api/backend-control/stop", headers=AUTH)).status_code == 409
            await asyncio.sleep(0.15)
            assert stopped == [True]
            assert state["draining"]

    asyncio.run(scenario())


def test_actual_inflight_request_blocks_shutdown():
    async def scenario():
        app, state, stopped = application()
        entered, release = asyncio.Event(), asyncio.Event()

        @app.get("/slow")
        async def slow():
            entered.set()
            await release.wait()
            return {}

        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            pending = asyncio.create_task(client.get("/slow"))
            await entered.wait()
            response = await client.post("/api/backend-control/stop", headers=AUTH)
            assert response.status_code == 409 and response.json()["requests"] == 1
            release.set()
            await pending
            assert not state["inflight"] and not state["draining"] and not stopped

    asyncio.run(scenario())


def test_busy_detection_checks_real_registries(monkeypatch):
    from app.core import registry, stems_location
    from app.pipeline import guitar_detail, jobqueue, lyrics_retime, runner

    monkeypatch.setattr(runner, "_pipeline_lock", SimpleNamespace(locked=lambda: False))
    monkeypatch.setattr(jobqueue, "_queue", [])
    monkeypatch.setattr(jobqueue, "_running_id", None)
    monkeypatch.setattr(lyrics_retime, "_RUNS", {})
    monkeypatch.setattr(guitar_detail, "_runs", {})
    monkeypatch.setattr(registry, "all_jobs", lambda: {})
    monkeypatch.setattr(registry, "_procs", {})
    monkeypatch.setattr(stems_location, "is_relocating", lambda: False)
    assert busy_reasons() == []
    monkeypatch.setattr(guitar_detail, "_runs", {"g": SimpleNamespace(status="cancelling")})
    monkeypatch.setattr(registry, "_procs", {"w": SimpleNamespace(poll=lambda: None)})
    monkeypatch.setattr(lyrics_retime, "_RUNS", {"l": SimpleNamespace(state="running")})
    monkeypatch.setattr(
        registry, "all_jobs", lambda: {"j": SimpleNamespace(status="queued", vocal_split="none")}
    )
    assert set(busy_reasons()) == {"guitar", "workers", "lyrics_or_karaoke", "jobs"}


def test_occupied_port_never_starts_or_adopts(monkeypatch, tmp_path):
    monkeypatch.setattr(control, "port_open", lambda port: True)
    monkeypatch.setattr(
        control.subprocess, "Popen", lambda *a, **kw: pytest.fail("must not launch")
    )
    with pytest.raises(RuntimeError, match="occupied"):
        control.start(SimpleNamespace(port=8159), tmp_path / "receipt.json")


def test_legacy_stop_fails_without_sending_request(monkeypatch, tmp_path):
    monkeypatch.setattr(control, "port_open", lambda port: True)
    monkeypatch.setattr(control, "request", lambda *a, **kw: pytest.fail("must not send"))
    with pytest.raises(RuntimeError, match="manual bootstrap"):
        control.stop(SimpleNamespace(port=8159), tmp_path / "receipt.json")


def test_wrong_identity_never_stops(monkeypatch, tmp_path):
    receipt = tmp_path / "receipt.json"
    receipt.write_text('{"token":"redacted", "instance":"expected"}')
    monkeypatch.setattr(control, "port_open", lambda port: True)
    calls = []

    def request(*args, **kwargs):
        calls.append((args, kwargs))
        return {"instance": "other"}

    monkeypatch.setattr(control, "request", request)
    with pytest.raises(RuntimeError, match="identity mismatch"):
        control.stop(SimpleNamespace(port=8159), receipt)
    assert len(calls) == 1 and not calls[0][1].get("post")
