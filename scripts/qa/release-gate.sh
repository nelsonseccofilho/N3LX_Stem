#!/usr/bin/env bash
# One Windows Git Bash command per release candidate; no installs or user-data edits.
set -euo pipefail
repo="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
runtime="$HOME/Git/N3LX_Stem"
out="$HOME/Git/N3LX_Stem-Releases"
python="$runtime/.venv/Scripts/python.exe"
[[ -f "$python" ]] || { echo 'BLOCKED: existing Windows Python required' >&2; exit 1; }
# Parse Python before creating any QA directories or starting a backend.
"$python" -B -c 'import ast,pathlib,sys;ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))' \
  "$repo/scripts/qa/release-gate.py"
"$python" -B "$repo/tests/qa/test_release_output_paths.py"
# Optional first argument: a previous ReleaseGate report, to resume ONLY the
# blocked browser E2E while cryptographically/revision-checking prior results.
[[ $# -le 1 ]] || { echo 'Usage: release-gate.sh [prior-ReleaseGate-directory]' >&2; exit 2; }
if [[ $# -eq 1 ]]; then
  prior="$(cygpath -w "$1")"
  exec "$python" -B "$repo/scripts/qa/release-gate.py" \
    --runtime "$runtime" --out-root "$out" --resume-from "$prior"
fi
exec "$python" -B "$repo/scripts/qa/release-gate.py" \
  --runtime "$runtime" --out-root "$out"
