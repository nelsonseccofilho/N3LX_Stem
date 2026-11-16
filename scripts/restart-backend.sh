#!/usr/bin/env bash
# One Git Bash entry point. Python handles authenticated API and Windows spawning.
set -euo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
runtime="${N3LX_RUNTIME:-C:/Users/Nelson Secco/Git/N3LX_Stem}"
data="${N3LX_DATA:-C:/Users/Nelson Secco/Git/N3LX_Stem-Releases/c21-biblioteca-completa-qa/data}"
port="${N3LX_PORT:-8159}"
if (( $# != 0 )); then
  printf '%s\n' 'This production command takes no arguments; edit a copy for isolated testing.' >&2
  exit 2
fi
cd "$repo"
python scripts/backend_control.py check-ready --port "$port" --runtime "$runtime" --data "$data"
python scripts/backend_control.py stop --port "$port" --runtime "$runtime" --data "$data"
python scripts/backend_control.py verify-free --port "$port" --runtime "$runtime" --data "$data"
python scripts/backend_control.py start --port "$port" --runtime "$runtime" --data "$data"
python scripts/backend_control.py status --port "$port" --runtime "$runtime" --data "$data"
