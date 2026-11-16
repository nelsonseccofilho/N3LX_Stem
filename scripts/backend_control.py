"""STOP -> VERIFY -> START -> HEALTH. Never kill or adopt an unknown process."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def port_open(port):
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def request(port, path, token=None, post=False):
    headers = {"Authorization": "Bearer " + token} if token else {}
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=b"" if post else None, headers=headers
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.load(response)


def verified(args, control):
    if not control.is_file():
        raise RuntimeError("no controlled-instance receipt; legacy server needs manual bootstrap")
    receipt = json.loads(control.read_text(encoding="utf-8"))
    state = request(args.port, "/api/backend-control/status", receipt["token"])
    if (
        state["instance"] != receipt["instance"]
        or state["port"] != args.port
        or Path(state["root"]).resolve() != ROOT
        or Path(state["data"]).resolve() != args.data.resolve()
    ):
        raise RuntimeError("backend identity mismatch; no action taken")
    health = request(args.port, "/api/health")
    if health.get("pid") != state["pid"] or health.get("product") != "N3LX_Stem":
        raise RuntimeError("health identity mismatch; no action taken")
    return receipt, state


def check_loaded(args, control):
    _, state = verified(args, control)
    if Path(state["python"]).resolve() != (args.runtime / ".venv/Scripts/python.exe").resolve():
        raise RuntimeError("interpreter differs from requested runtime")
    if Path(state["jobs"]).resolve() != (args.data / "jobs").resolve():
        raise RuntimeError("jobs directory differs from requested library")
    for name, digest in state["source_sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError("loaded code differs from workspace: " + name)
    return state


def stop(args, control):
    if not port_open(args.port):
        return
    receipt, state = verified(args, control)
    if state["busy"] or state["inflight"]:
        raise RuntimeError("backend busy; nothing stopped")
    request(args.port, "/api/backend-control/stop", receipt["token"], post=True)
    deadline = time.monotonic() + 30
    while port_open(args.port):
        if time.monotonic() > deadline:
            raise RuntimeError(
                "port still occupied after cooperative stop; no force, no new server"
            )
        time.sleep(0.2)
    print("STOP + VERIFY: port released")


def start(args, control):
    if port_open(args.port):
        raise RuntimeError("port occupied; existing server will not be adopted or stopped")
    python = args.runtime / ".venv" / "Scripts" / "python.exe"
    if not python.is_file() or not args.data.is_dir():
        raise RuntimeError("existing runtime and data directory are required")
    settings_file = args.data / "settings.json"
    if settings_file.is_file():
        stored = json.loads(settings_file.read_text(encoding="utf-8")).get("jobs_dir")
        if stored and Path(stored).expanduser().resolve() != (args.data / "jobs").resolve():
            raise RuntimeError("stored jobs_dir conflicts with requested data; resolve explicitly")
    for other in control.parent.glob("*.json"):
        if other.stem.isdigit() and int(other.stem) != args.port and port_open(int(other.stem)):
            raise RuntimeError("another controlled port for this library is occupied")
    shared = args.runtime.parent / "_workspace"
    env = os.environ.copy()
    env.update(
        {
            "STEMDECK_DATA_DIR": str(args.data),
            "STEMDECK_DEFAULT_JOBS_DIR": str(args.data / "jobs"),
            "STEMDECK_CACHE_DIR": str(args.data / "cache"),
            "STEMDECK_LOGS_DIR": str(args.data / "logs"),
            "STEMDECK_MODELS_DIR": str(args.data / "models"),
            "STEMDECK_DOWNLOADS_DIR": str(args.data / "downloads"),
            "TORCH_HOME": str(args.data / "cache/torch"),
            "XDG_CACHE_HOME": str(args.data / "cache"),
            "STEMDECK_PERSIST_LIBRARY": "1",
            "PYTHONIOENCODING": "utf-8",
            "STEMDECK_DIRECTML_PYTHON": str(args.runtime / ".venv-directml/Scripts/python.exe"),
            "STEMDECK_DIRECTML_ADAPTER": env.get("STEMDECK_DIRECTML_ADAPTER", "RX 6600M"),
            "STEMDECK_DEMUCS_DEVICE": "directml",
            "STEMDECK_SEPARATION_PROFILE": "complete",
            "STEMDECK_SEPARATION_QUALITY": "best",
        }
    )
    if (
        env.get("STEMDECK_JOBS_DIR")
        and Path(env["STEMDECK_JOBS_DIR"]).resolve() != (args.data / "jobs").resolve()
    ):
        raise RuntimeError("STEMDECK_JOBS_DIR conflicts with requested data; resolve explicitly")
    for key, value in {
        "N3LX_WHISPER_CLI": shared / "tools/whisper.cpp/build-vulkan-nmake/bin/whisper-cli.exe",
        "N3LX_WHISPER_LARGE_MODEL": shared / "models/ggml-large-v3.bin",
        "N3LX_WHISPER_GPU_HOME": args.runtime.parent / "NELX-Whisper-GPU",
        "N3LX_WHISPER_GPU_PYTHON": shared / "venvs/whispergpu/Scripts/python.exe",
    }.items():
        env.setdefault(key, str(value))
    env.setdefault("N3LX_WHISPER_MODEL", env["N3LX_WHISPER_LARGE_MODEL"])
    env.setdefault("STEMDECK_SAM_SOURCE", str(args.runtime.parent / "sam-audio-amd"))
    if not Path(env["N3LX_WHISPER_CLI"]).is_file():
        fallback = args.runtime / "tools/whisper.cpp/whisper-cli.exe"
        if fallback.is_file():
            env["N3LX_WHISPER_CLI"] = str(fallback)
    for name in ("ffmpeg", "ffprobe"):
        executable = shutil.which(name)
        if not executable:
            raise RuntimeError(name + " unavailable")
        env["STEMDECK_" + name.upper()] = executable
    control.parent.mkdir(parents=True, exist_ok=True)
    receipt = {"token": secrets.token_hex(32), "instance": secrets.token_hex(16)}
    # The control file belongs in the user's private data directory, never static/.
    # Do not print its bearer token or put it on the process command line.
    temporary = control.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        os.chmod(temporary, 0o600)
        json.dump(receipt, handle)
    temporary.replace(control)
    log_path = control.parent / ("server-" + receipt["instance"] + ".log")
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [
                str(python),
                "-B",
                "-m",
                "app.controlled_server",
                "--port",
                str(args.port),
                "--control-file",
                str(control),
            ],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("server exited; inspect " + str(log_path))
        try:
            _, state = verified(args, control)
        except (OSError, ValueError, KeyError):
            time.sleep(0.5)
            continue
        for name, digest in state["source_sha256"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
                raise RuntimeError("source differs from loaded snapshot")
        if Path(state["jobs"]).resolve() != (args.data / "jobs").resolve():
            raise RuntimeError(
                "effective library differs from requested library; inspect configuration"
            )
        print(json.dumps({"result": "START + HEALTH CHECK", **state}, indent=2))
        return
    raise RuntimeError("health timeout; inspect log; no forced termination")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("status", "check-ready", "verify-free", "start", "stop", "restart")
    )
    parser.add_argument("--port", type=int, default=8159)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    args.runtime, args.data = args.runtime.resolve(), args.data.resolve()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    control = args.data / "backend-control" / f"{args.port}.json"
    try:
        if args.action == "status":
            print(json.dumps(verified(args, control)[1], indent=2))
        elif args.action == "check-ready":
            state = check_loaded(args, control)
            if state["busy"] or state["inflight"]:
                raise RuntimeError("backend busy; no restart")
            print(json.dumps({"pid": state["pid"], "instance": state["instance"], "busy": []}))
        elif args.action == "verify-free":
            if port_open(args.port):
                raise RuntimeError("port is still occupied; no new server")
            print("VERIFY: port released")
        else:
            # Serialize controllers; no automatic stale-lock deletion.
            control.parent.mkdir(parents=True, exist_ok=True)
            lock = control.parent / "controller.lock"
            with lock.open("x"):
                pass
            try:
                if args.action in {"stop", "restart"}:
                    stop(args, control)
                if args.action in {"start", "restart"}:
                    start(args, control)
            finally:
                lock.unlink(missing_ok=True)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print("BLOCKED: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
