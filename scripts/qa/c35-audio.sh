#!/usr/bin/env bash
# C35 package audio QA, runs only the new driver using C34 safe lifecycle.
set -euo pipefail
repo="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
N3LX_C35_AUDIO=1 bash "$repo/scripts/qa/c34-packaged.sh"
