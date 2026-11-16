"""Uvicorn entry point with explicit, authenticated cooperative shutdown."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import uvicorn

from app.core.backend_lifecycle import install_control, source_hashes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--control-file", type=Path, required=True)
    args = parser.parse_args()
    receipt = json.loads(args.control_file.read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[1]
    # Snapshot before imports. The launcher verifies hashes against these values.
    hashes = source_hashes(root)
    from app.core.config import DATA_DIR, JOBS_DIR
    from app.main import app
    from app.pipeline.karaoke_timing import portuguese_alignment_cache

    if source_hashes(root) != hashes:
        raise RuntimeError("source changed during imports; start again")
    identity = {
        "pid": os.getpid(),
        "root": str(root),
        "data": str(DATA_DIR.resolve()),
        "jobs": str(JOBS_DIR.resolve()),
        "python": sys.executable,
        "instance": receipt["instance"],
        "port": args.port,
        "source_sha256": hashes,
        "pt_cache": str(portuguese_alignment_cache() or ""),
        "command": sys.argv,
    }
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=args.port, proxy_headers=False, timeout_graceful_shutdown=10
        )
    )
    install_control(
        app,
        token=receipt["token"],
        identity=identity,
        stop=lambda: setattr(server, "should_exit", True),
    )
    server.run()


if __name__ == "__main__":
    main()
