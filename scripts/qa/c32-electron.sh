#!/usr/bin/env bash
# Windows Git Bash. Never adopt/kill a foreign server or access the personal library.
set -euo pipefail

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
runtime="${N3LX_C32_RUNTIME:-$HOME/Git/N3LX_Stem}"
python="$runtime/.venv/Scripts/python.exe"
electron="$runtime/desktop-app/node_modules/electron/dist/electron.exe"
output_parent="${N3LX_C32_OUTPUTS:-$HOME/Git/N3LX_Stem-Releases}"

[[ -f "$python" && -f "$electron" ]] || {
  echo 'BLOCKED: existing Python and Electron are required' >&2
  exit 1
}
node -e "require.resolve('playwright', { paths: [process.argv[1]] })" "$runtime" >/dev/null
[[ -f "$repo/desktop/src-tauri/icons/icon.ico" ]] || {
  echo 'BLOCKED: desktop icon is missing' >&2
  exit 1
}
[[ -d "$output_parent" ]] || {
  echo 'BLOCKED: existing QA output parent is required' >&2
  exit 1
}

report="$(mktemp -d "$output_parent/C32-Electron-XXXXXXXX")"
mkdir -p "$report/data/jobs" "$report/shell/desktop-app" "$report/shell/desktop/src-tauri/icons"
cp "$repo/desktop-app/main.cjs" "$repo/desktop-app/preload.cjs" \
   "$repo/desktop-app/package.json" "$report/shell/desktop-app/"
cp "$repo/desktop/src-tauri/icons/icon.ico" "$report/shell/desktop/src-tauri/icons/"

unset STEMDECK_JOBS_DIR STEMDECK_DATA_DIR STEMDECK_DEFAULT_JOBS_DIR \
      STEMDECK_CACHE_DIR STEMDECK_LOGS_DIR STEMDECK_MODELS_DIR \
      STEMDECK_DOWNLOADS_DIR STEMDECK_SETTINGS_MIRROR STEMDECK_REGISTRY_FILE

port="$(node "$repo/scripts/qa/available-port.mjs")"

qa_backend() {
  "$python" -B "$repo/scripts/backend_control.py" "$1" \
    --port "$port" --runtime "$runtime" --data "$report/data"
}

# Register cleanup before starting. On a failed/partial start, the controller
# refuses to stop anything without an authenticated matching receipt.
cleanup() {
  result=$?
  trap - EXIT
  echo '=== C32: cooperative QA teardown ==='
  if ! qa_backend stop; then
    echo 'WARNING: QA backend may still be running; no forced termination' >&2
    result=1
  elif ! qa_backend verify-free; then
    echo 'WARNING: QA port still occupied; no forced termination' >&2
    result=1
  fi
  echo "Evidence: $report"
  echo "QA port: $port"
  exit "$result"
}
trap cleanup EXIT

# The candidate check can race. The controller is the final authority:
# its restart safely stops owned idle processes, verifies free port, starts
# and checks health, and BLOCKS on foreign/busy processes.
qa_backend verify-free
"$python" -B "$repo/tests/e2e/seed.py" "$report/data/jobs" > "$report/seed.log"
qa_backend restart > "$report/backend-start.log"
qa_backend status > "$report/backend-status.json"

"$python" - "$port" <<'PY'
import json
import sys
from urllib.request import urlopen
base = 'http://127.0.0.1:' + sys.argv[1]
with urlopen(base + '/api/health', timeout=10) as response:
    health = json.load(response)
with urlopen(base + '/api/jobs', timeout=10) as response:
    jobs = json.load(response)
assert health['product'] == 'N3LX_Stem'
assert sorted(job['job_id'] for job in jobs) == ['e2e0cafebabe', 'e2e0deadbeef']
print('PASS: isolated backend, exactly 2 synthetic jobs')
PY

revision="$(git -C "$repo" rev-parse HEAD)"
C32_ROOT="$(cygpath -w "$repo")" \
C32_RUNTIME="$(cygpath -w "$runtime")" \
C32_REPORT="$(cygpath -w "$report")" \
C32_PORT="$port" C32_REVISION="$revision" \
node "$repo/scripts/qa/c32-electron.mjs" 2>&1 | tee "$report/electron.log"
echo 'PASS: C32 Electron renderer smoke QA'
