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

case "${N3LX_C33_FUNCTIONAL:-0}" in
  0) report_cycle=C32 ;;
  1) report_cycle=C33 ;;
  *) echo 'BLOCKED: unsupported QA scenario' >&2; exit 1 ;;
esac

report="$(mktemp -d "$output_parent/${report_cycle}-Electron-XXXXXXXX")"
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

# Register cleanup before starting. Browser SSE streams can take a short
# time to drain after Electron closes. Wait (bounded) for the authenticated,
# exact runtime and library to become idle before requesting cooperative stop.
# Never stop a foreign/active process or retry starting over an occupied port.
cleanup() {
  result=$?
  trap - EXIT
  echo '=== C32: cooperative QA teardown ==='
  released=0
  if qa_backend verify-free > /dev/null 2>&1; then
    echo 'PASS: QA port already free'
    released=1
  else
    for ((attempt=1; attempt<=30; attempt++)); do
      if qa_backend check-ready > "$report/teardown-ready.log" 2>&1; then
        if qa_backend stop > "$report/teardown-stop.log" 2>&1 &&
           qa_backend verify-free > "$report/teardown-verify.log" 2>&1; then
          echo 'PASS: owned QA backend stopped and port released'
          released=1
        else
          cat "$report/teardown-stop.log" >&2 || true
          echo 'WARNING: cooperative stop did not release port' >&2
        fi
        break
      fi
      if ! qa_backend status > "$report/teardown-status.json" 2> "$report/teardown-status.err"; then
        echo 'BLOCKED: QA port no longer identifies an owned backend' >&2
        cat "$report/teardown-status.err" >&2
        break
      fi
      # Even a recognized server may have workers/requests: never force stop.
      sleep 0.5
    done
  fi
  if [[ "$released" != 1 ]]; then
    echo 'BLOCKED: QA port remains occupied; no forced termination' >&2
    [[ ! -f "$report/teardown-status.json" ]] || cat "$report/teardown-status.json" >&2
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

if [[ "$report_cycle" == C33 ]]; then
  # Synthetic silent video permits the REAL MP4 mux route to be exercised.
  # Files remain entirely inside the disposable QA data directory.
  command -v ffmpeg >/dev/null || { echo 'BLOCKED: ffmpeg required' >&2; exit 1; }
  command -v ffprobe >/dev/null || { echo 'BLOCKED: ffprobe required' >&2; exit 1; }
  ffmpeg -nostdin -hide_banner -loglevel error -y     -f lavfi -i 'color=c=black:s=160x90:r=10'     -t 2 -an -c:v mpeg4 -pix_fmt yuv420p     "$report/data/jobs/e2e0cafebabe/video.mp4"
fi

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
echo "PASS: ${report_cycle} Electron renderer QA"
