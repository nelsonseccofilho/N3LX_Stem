#!/usr/bin/env python3
"""Read-only rc.10 parity triage of an existing verified local source checkpoint.

Uses checkpoint copies and Git object reads. Writes only filename/status metadata
to a NEW directory outside the repository. No music, install, merge or cleanup.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4

BRANCH = "release/v0.21.0-rc.10"
LOCAL_HEAD = "a7c151565b7bd7609f91eef10e00d5daa5221985"
KNOWN_SEVEN = frozenset({
    "app/api/karaoke.py", "app/main.py", "app/pipeline/karaoke_timing.py",
    "scripts/Start-N3LX_Stem.ps1", "static/index.html",
    "static/js/i18n.js", "static/js/lyrics.js",
})
BANNED_PARTS = frozenset({
    "data", "jobs", "_workspace", "node_modules", ".venv", ".venv-directml",
    "models", "weights", ".git", "__pycache__",
})
BANNED_EXTENSIONS = frozenset({
    ".wav", ".flac", ".mp3", ".m4a", ".ogg", ".opus", ".onnx",
    ".safetensors", ".pt", ".pth", ".ckpt",
})


def git(repo: Path, *args: str, allow_missing: bool = False) -> bytes | None:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=60, check=False)
    if proc.returncode == 0:
        return proc.stdout
    # Git uses different messages when the path exists in the working tree
    # but is absent from a historical commit. Do not hide unrelated failures.
    missing = (b"does not exist in" in proc.stderr
               or b"exists on disk, but not in" in proc.stderr)
    if allow_missing and proc.returncode == 128 and missing:
        return None
    raise RuntimeError(f"git {' '.join(args[:2])} failed (exit {proc.returncode}); no retry")


def safe_relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError("invalid manifest path")
    name = PurePosixPath(value)
    if (name.is_absolute() or ".." in name.parts or "." in name.parts
            or any(":" in part or part.lower() in BANNED_PARTS for part in name.parts)
            or name.suffix.lower() in BANNED_EXTENSIONS):
        raise ValueError("unsafe or non-source manifest path")
    return name


def read_no_link(root: Path, relative: PurePosixPath) -> bytes:
    loc = root
    for part in relative.parts:
        loc = loc / part
        if loc.is_symlink() or (hasattr(loc, "is_junction") and loc.is_junction()):
            raise ValueError("checkpoint source contains a link or junction")
    if not loc.is_file():
        raise ValueError("checkpoint source copy missing")
    return loc.read_bytes()


def same(a: bytes | None, b: bytes | None) -> bool:
    if a is None or b is None:
        return a is b
    if a == b:
        return True
    if b"\0" in a or b"\0" in b:
        return False
    return a.replace(b"\r\n", b"\n") == b.replace(b"\r\n", b"\n")


def classify(local: bytes, base: bytes | None, candidate: bytes | None) -> str:
    if candidate is None:
        return "LOCAL_ONLY_FILE_ABSENT_IN_CANDIDATE"
    if same(local, candidate):
        return "EQUIVALENT_CONTENT_OR_EOL"
    if base is None:
        return "INDEPENDENT_ADDITION_REVIEW"
    if same(candidate, base):
        return "LOCAL_CHANGE_NOT_IN_CANDIDATE"
    if same(local, base):
        return "CANDIDATE_CHANGE_ONLY"
    return "BOTH_CHANGED_SEMANTIC_REVIEW"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repository", type=Path, required=True)
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--reports-root", type=Path, required=True)
    args = ap.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.candidate):
        raise ValueError("candidate must be a pinned 40-character SHA")
    repo = args.repository.resolve(strict=True)
    checkpoint = args.checkpoint.resolve(strict=True)
    reports = args.reports_root.resolve(strict=True)
    if not (repo / ".git").exists():
        raise ValueError("repository is not a Git checkout")
    if repo == checkpoint or repo in checkpoint.parents or repo == reports or repo in reports.parents:
        raise ValueError("checkpoint and reports must be outside the checkout")
    marker = (checkpoint / "STATUS.txt").read_text(encoding="utf-8-sig").strip()
    if not marker.startswith("CHECKPOINT_VERIFIED: local source copies and tracked patch saved with hashes."):
        raise ValueError("checkpoint is not verified")
    manifest = json.loads((checkpoint / "manifest.json").read_text(encoding="utf-8-sig"))
    if manifest.get("local_head") != LOCAL_HEAD:
        raise ValueError("checkpoint uses an unexpected local HEAD")
    if git(repo, "rev-parse", "HEAD").decode().strip() != LOCAL_HEAD:
        raise ValueError("original checkout HEAD changed; stop to inspect")
    entries = manifest.get("files")
    if not isinstance(entries, list) or len(entries) != manifest.get("saved_file_count"):
        raise ValueError("manifest count disagrees with saved source copies")
    deleted = manifest.get("tracked_deleted_paths_in_patch", [])
    if len(entries) + len(deleted) != (manifest.get("tracked_changed_paths", -1)
                                      + manifest.get("untracked_paths", -1)):
        raise ValueError("manifest tracked/untracked counts disagree")
    # Verify every checkpoint source hash before making a report or fetching.
    saved: dict[str, bytes] = {}
    for entry in entries:
        name = safe_relative(entry["path"])
        if str(name) in saved or entry.get("kind") not in ("tracked", "untracked"):
            raise ValueError("duplicate manifest path or invalid kind")
        data = read_no_link(checkpoint / "source-files", name)
        if (len(data) != entry["bytes"]
                or hashlib.sha256(data).hexdigest() != entry["sha256"]):
            raise ValueError(f"checkpoint hash or byte count mismatch: {name}")
        saved[str(name)] = data
    patch = checkpoint / "tracked-working-tree.patch"
    if patch.is_symlink() or not patch.is_file():
        raise ValueError("tracked source patch missing or a link")
    if hashlib.sha256(patch.read_bytes()).hexdigest() != manifest.get("patch_sha256"):
        raise ValueError("tracked source patch hash mismatch")
    print(f"CHECKPOINT_VERIFIED_FILES: {len(saved)}", flush=True)
    # Fetch metadata/objects only: no checkout, stash, reset, clean or merge.
    git(repo, "fetch", "--no-tags", "origin", f"refs/heads/{BRANCH}")
    actual = git(repo, "rev-parse", "FETCH_HEAD").decode().strip()
    if actual != args.candidate:
        raise ValueError("candidate advanced; inspect the new SHA before continuing")
    git(repo, "merge-base", "--is-ancestor", LOCAL_HEAD, actual)
    rows = []
    for name, source in sorted(saved.items()):
        base = git(repo, "show", f"{LOCAL_HEAD}:{name}", allow_missing=True)
        candidate = git(repo, "show", f"{actual}:{name}", allow_missing=True)
        rows.append({
            "path": name,
            "scope": "ALREADY_REVIEWED_SEVEN" if name in KNOWN_SEVEN else "PENDING_OTHER_FILES",
            "outcome": classify(source, base, candidate),
        })
    pending = [r for r in rows if r["scope"] == "PENDING_OTHER_FILES"]
    counts = collections.Counter(r["outcome"] for r in pending)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report = reports / f"rc10-parity-triage-{stamp}-{uuid4().hex[:8]}"
    report.mkdir(exist_ok=False)
    with (report / "summary.tsv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=("path", "scope", "outcome"), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# rc.10 source parity triage — review required", "",
        f"Candidate: {actual}", f"Checkpoint local HEAD: {LOCAL_HEAD}",
        f"Checkpoint source copies hash-verified: {len(saved)}",
        f"Previously reviewed seven paths: {sum(r['scope'] == 'ALREADY_REVIEWED_SEVEN' for r in rows)}",
        f"Other paths requiring triage: {len(pending)}", "",
        "## Classification of other paths", "",
    ]
    for key in (
        "LOCAL_ONLY_FILE_ABSENT_IN_CANDIDATE", "LOCAL_CHANGE_NOT_IN_CANDIDATE",
        "INDEPENDENT_ADDITION_REVIEW", "BOTH_CHANGED_SEMANTIC_REVIEW",
        "CANDIDATE_CHANGE_ONLY", "EQUIVALENT_CONTENT_OR_EOL",
    ):
        lines.append(f"- {key}: {counts[key]}")
    lines += [
        "", "Equal files or textually mergeable content do NOT prove functional parity.",
        "This metadata report contains no source file contents or personal audio.",
        "No checkout, music, models, EXE or release artifacts were changed.",
        "Keep the existing checkpoint; do not merge, clean or publish yet.",
    ]
    (report / "RESULT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("PARITY_TRIAGE_COMPLETE_REVIEW_REQUIRED")
    print(f"OTHER_FILES: {len(pending)}")
    for key, number in sorted(counts.items()):
        print(f"{key}: {number}")
    print(f"REPORT: {report}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"PARITY_TRIAGE_STOP: {exc}", file=sys.stderr)
        sys.exit(2)
