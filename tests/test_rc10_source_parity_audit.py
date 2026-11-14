"""Synthetic, network-free regression checks for the rc.10 source parity auditor."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "windows" / "Audit-Local-Source-Parity-rc10.py"
spec = importlib.util.spec_from_file_location("rc10_source_parity_audit", SCRIPT)
audit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(audit)


@pytest.mark.parametrize("local,base,candidate,expected", [
    (b"same\r\n", b"same\n", b"same\n", "EQUIVALENT_CONTENT_OR_EOL"),
    (b"local", b"base", None, "LOCAL_ONLY_FILE_ABSENT_IN_CANDIDATE"),
    (b"local", None, b"remote", "INDEPENDENT_ADDITION_REVIEW"),
    (b"local", b"base", b"base", "LOCAL_CHANGE_NOT_IN_CANDIDATE"),
    (b"base", b"base", b"remote", "CANDIDATE_CHANGE_ONLY"),
    (b"local", b"base", b"remote", "BOTH_CHANGED_SEMANTIC_REVIEW"),
])
def test_classification(local, base, candidate, expected):
    assert audit.classify(local, base, candidate) == expected


@pytest.mark.parametrize("path", [
    "../private.txt", "data/music.mp3", "app/models/model.bin",
    r"app\\..\secret", "/absolute", "static/js/../../data/music.txt",
    "app/private.onnx", "app/.git/config",
])
def test_manifest_path_fails_closed(path):
    with pytest.raises(ValueError):
        audit.safe_relative(path)


def git(*args, cwd):
    completed = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
        timeout=30,
    )
    return completed.stdout.strip()


def test_end_to_end_private_snapshot_and_read_only_source(tmp_path, monkeypatch):
    bare = tmp_path / "remote.git"
    repo = tmp_path / "checkout"
    candidate = tmp_path / "release-builder"
    checkpoint = tmp_path / "checkpoint"
    reports = tmp_path / "reports"
    checkpoint.mkdir()
    reports.mkdir()
    git("init", "--bare", str(bare), cwd=tmp_path)
    git("clone", str(bare), str(repo), cwd=tmp_path)
    git("config", "user.name", "Local fixture", cwd=repo)
    git("config", "user.email", "fixture@example.invalid", cwd=repo)
    for name, text in {"shared.txt": "base\n", "local.txt": "base\n", "same.txt": "same\n"}.items():
        (repo / name).write_text(text)
    git("add", ".", cwd=repo)
    git("commit", "-m", "base", cwd=repo)
    local_sha = git("rev-parse", "HEAD", cwd=repo)
    git("push", "origin", "HEAD:refs/heads/main", cwd=repo)

    git("clone", "-b", "main", str(bare), str(candidate), cwd=tmp_path)
    git("config", "user.name", "Release fixture", cwd=candidate)
    git("config", "user.email", "fixture@example.invalid", cwd=candidate)
    git("checkout", "-b", audit.BRANCH, cwd=candidate)
    (candidate / "shared.txt").write_text("candidate\n")
    (candidate / "added.txt").write_text("remote added\n")
    git("add", ".", cwd=candidate)
    git("commit", "-m", "release candidate", cwd=candidate)
    release_sha = git("rev-parse", "HEAD", cwd=candidate)
    git("push", "origin", "HEAD:refs/heads/" + audit.BRANCH, cwd=candidate)

    (repo / "shared.txt").write_text("local\n")
    (repo / "local.txt").write_text("local\n")
    (repo / "same.txt").write_bytes(b"same\r\n")
    (repo / "added.txt").write_text("local added\n")
    snapshots = [
        ("shared.txt", "tracked"), ("local.txt", "tracked"),
        ("same.txt", "tracked"), ("added.txt", "untracked"),
    ]
    (checkpoint / "source-files").mkdir()
    entries = []
    for name, kind in snapshots:
        data = (repo / name).read_bytes()
        (checkpoint / "source-files" / name).write_bytes(data)
        entries.append({
            "path": name, "kind": kind, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    patch = checkpoint / "tracked-working-tree.patch"
    git("diff", "--binary", "HEAD", "--output=" + str(patch), "--",
        "shared.txt", "local.txt", "same.txt", cwd=repo)
    (checkpoint / "manifest.json").write_text(json.dumps({
        "local_head": local_sha, "files": entries, "saved_file_count": 4,
        "tracked_changed_paths": 3, "untracked_paths": 1,
        "tracked_deleted_paths_in_patch": [],
        "patch_sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
    }))
    (checkpoint / "STATUS.txt").write_bytes(
        b"\xef\xbb\xbfCHECKPOINT_VERIFIED: local source copies and tracked patch saved with hashes."
    )
    monkeypatch.setattr(audit, "LOCAL_HEAD", local_sha)
    monkeypatch.setattr(sys, "argv", [
        "audit", "--repository", str(repo), "--checkpoint", str(checkpoint),
        "--candidate", release_sha, "--reports-root", str(reports),
    ])
    assert audit.main() == 0
    report = next(reports.glob("rc10-parity-triage-*"))
    with (report / "summary.tsv").open() as file:
        outcomes = {row["path"]: row["outcome"] for row in csv.DictReader(file, delimiter="\t")}
    assert outcomes == {
        "shared.txt": "BOTH_CHANGED_SEMANTIC_REVIEW",
        "local.txt": "LOCAL_CHANGE_NOT_IN_CANDIDATE",
        "same.txt": "EQUIVALENT_CONTENT_OR_EOL",
        "added.txt": "INDEPENDENT_ADDITION_REVIEW",
    }
    assert (repo / "shared.txt").read_text() == "local\n"
    assert (repo / "added.txt").read_text() == "local added\n"
    assert len(list(reports.iterdir())) == 1
