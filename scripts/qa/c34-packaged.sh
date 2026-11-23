#!/usr/bin/env bash
# C34 packaged Windows native smoke. Git Bash only, synthetic library only.
set -euo pipefail
repo="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
runtime="$HOME/Git/N3LX_Stem"
custom_runtime="$(printenv N3LX_C34_RUNTIME || true)"
if [[ -n "$custom_runtime" ]]; then runtime="$custom_runtime"; fi
output_parent="$HOME/Git/N3LX_Stem-Releases"
custom_output="$(printenv N3LX_C34_OUTPUTS || true)"
if [[ -n "$custom_output" ]]; then output_parent="$custom_output"; fi
python="$runtime/.venv/Scripts/python.exe"
[[ -f "$python" && -f "$runtime/.venv-directml/Scripts/python.exe" ]] || {
  echo 'BLOCKED: existing AMD environments required' >&2; exit 1;
}
[[ -f "$runtime/desktop-app/node_modules/electron/dist/electron.exe" ]] || {
  echo 'BLOCKED: installed Electron runtime required' >&2; exit 1;
}
[[ -d "$output_parent" ]] || { echo 'BLOCKED: output root missing' >&2; exit 1; }
command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null || {
  echo 'BLOCKED: ffmpeg/ffprobe required' >&2; exit 1;
}
node -e "require.resolve('playwright',{paths:[process.argv[1]]})" "$runtime" >/dev/null
[[ -z "$(git -C "$repo" status --porcelain)" ]] || {
  echo 'BLOCKED: source worktree not clean' >&2; exit 1;
}

report="$(mktemp -d "$output_parent/C34-Windows-XXXXXXXX")"
mkdir -p "$report/data/jobs" "$report/profile" "$report/exports"
port="$(node "$repo/scripts/qa/available-port.mjs")"
package=""
qa_backend() {
  "$python" -B "$package/resources/stemdeck/scripts/backend_control.py" "$1" \
    --port "$port" --runtime "$runtime" --data "$report/data"
}
cleanup() {
  code=$?
  trap - EXIT
  echo '=== C34: cooperative teardown ==='
  if [[ -n "$package" && -f "$package/resources/stemdeck/scripts/backend_control.py" ]]; then
    released=0
    if qa_backend verify-free > /dev/null 2>&1; then
      echo 'PASS: QA port already free'
      released=1
    else
      for ((attempt=1; attempt<=30; attempt++)); do
        if qa_backend check-ready > "$report/ready.log" 2>&1; then
          if qa_backend stop > "$report/stop.log" 2>&1 &&
             qa_backend verify-free > "$report/verify.log" 2>&1; then
            echo 'PASS: packaged QA backend stopped cooperatively; port released'
            released=1
          else
            cat "$report/stop.log" >&2 || true
          fi
          break
        fi
        if ! qa_backend status > "$report/status.json" 2> "$report/status.err"; then
          echo 'BLOCKED: port owner cannot be verified' >&2
          cat "$report/status.err" >&2
          break
        fi
        sleep 0.5
      done
    fi
    if [[ "$released" != 1 ]]; then
      echo 'BLOCKED: QA port still occupied; no forced termination' >&2
      [[ ! -f "$report/status.json" ]] || cat "$report/status.json" >&2
      code=1
    fi
  fi
  echo "Evidence: $report"
  echo "QA port: $port"
  exit "$code"
}
trap cleanup EXIT

echo '=== C34: build authentic Windows update from committed worktree ==='
rev="$(git -C "$repo" rev-parse HEAD)"
"$python" -B "$repo/scripts/build-windows-update.py" \
  --source "$repo" --installation "$runtime" --output "$report/bundle" \
  > "$report/package-build.json"
version="$("$python" -B -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8"))["version"])' "$repo/desktop-app/package.json")"
package="$report/bundle/N3LX_Stem-Windows-Update-$version"
test -f "$package/N3LX_Stem.exe"
test -f "$package/resources/stemdeck/scripts/backend_control.py"
"$python" -B - "$package" "$rev" <<'PY'
import hashlib,json,sys
from pathlib import Path
package=Path(sys.argv[1])
info=json.loads((package/'build-info.json').read_text(encoding='utf-8'))
assert info['source_revision']==sys.argv[2]
assert info['kind']=='update-requires-existing-amd-installation'
assert info['includes_python_models_or_user_data'] is False
hashes=json.loads((package/'sha256-manifest.json').read_text(encoding='utf-8'))
assert hashes and 'N3LX_Stem.exe' in hashes
for path,sha in hashes.items():
    p=package/path
    assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==sha,path
    assert not path.startswith(('.venv/','.venv-directml/','data/')),path
print('PASS: packaged source revision and manifest verified')
PY

"$python" -B "$repo/tests/e2e/seed.py" "$report/data/jobs" > "$report/seed.log"
qa_backend verify-free

echo '=== C34: real packaged Electron executable ==='
C34_RUNTIME="$(cygpath -w "$runtime")" \
C34_REPORT="$(cygpath -w "$report")" \
C34_EXE="$(cygpath -w "$package/N3LX_Stem.exe")" \
C34_PORT="$port" C34_REVISION="$rev" \
node "$repo/scripts/qa/c34-packaged.mjs" 2>&1 | tee "$report/packaged-electron.log"
echo 'PASS: C34 packaged native test finished'
