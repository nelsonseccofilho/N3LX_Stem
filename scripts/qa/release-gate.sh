#!/usr/bin/env bash
# One Windows Git Bash command per release candidate; no installs or user-data edits.
set -euo pipefail
repo="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
runtime="$HOME/Git/N3LX_Stem"
out="$HOME/Git/N3LX_Stem-Releases"
python="$runtime/.venv/Scripts/python.exe"
[[ -f "$python" ]] || { echo 'BLOCKED: existing Windows Python required' >&2; exit 1; }
exec "$python" -B "$repo/scripts/qa/release-gate.py" \
  --runtime "$runtime" --out-root "$out"
