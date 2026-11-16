#!/usr/bin/env bash
# Git Bash entry point; uses an existing Python, installs nothing.
set -euo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec python "$repo/scripts/backend_control.py" "$@"
