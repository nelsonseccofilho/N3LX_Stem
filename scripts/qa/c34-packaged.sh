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

if [[ "${N3LX_C35_AUDIO:-0}" == "1" ]]; then
  qa_script="c35-audio.mjs"
  report_prefix="C35-Audio"
else
  qa_script="c34-packaged.mjs"
  report_prefix="C34-Windows"
fi
report="$(mktemp -d "$output_parent/$report_prefix-XXXXXXXX")"
mkdir -p "$report/data/jobs" "$report/profile" "$report/exports"
port="$(node "$repo/scripts/qa/available-port.mjs")"
package=""
qa_backend() {
  "$python" -B "$package/resources/stemdeck/scripts/backend_control.py" "$1" \
    --port "$port" --runtime "$runtime" --data "$report/data"
}
# Shared function is tested against simulated asynchronous shutdown transitions.
source "$repo/scripts/qa/c34-teardown.sh"
cleanup() {
  code=$?
  trap - EXIT
  echo '=== C34: cooperative teardown ==='
  if [[ -n "$package" && -f "$package/resources/stemdeck/scripts/backend_control.py" ]]; then
    # A packaged backend can disappear between verify-free and status; only a
    # verified free port counts as PASS, and only a verified idle owner may stop.
    if ! c34_safe_teardown "$report"; then
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
node "$repo/scripts/qa/$qa_script" 2>&1 | tee "$report/packaged-electron.log"
echo 'PASS: C34 packaged native test finished'
