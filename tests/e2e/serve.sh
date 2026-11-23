#!/usr/bin/env bash
#
# Boot a StemDeck backend for the browser tests, against a throwaway jobs
# directory seeded with one finished track.
#
# Everything the app writes is redirected into that directory, so a test run can
# never read, modify or delete a developer's real library. The directory is
# recreated on every run, so state cannot leak between runs either.

set -euo pipefail

PORT="${1:-8123}"
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK_DIR="${STEMDECK_E2E_DIR:-${TMPDIR:-/tmp}/stemdeck-e2e}"

if [[ "${STEMDECK_E2E_ISOLATED:-0}" == "1" ]]; then
  # Single-release gate uses a never-before-used scratch directory. Reject
  # symlinks and existing directories instead of deleting any previous data.
  [[ -n "${N3LX_RELEASE_REPORT_DIR:-}" ]] || {
    echo 'BLOCKED: isolated browser QA requires report root' >&2; exit 1;
  }
  expected="$N3LX_RELEASE_REPORT_DIR/browser-scratch"
  [[ "$WORK_DIR" == "$expected" && ! -e "$WORK_DIR" && ! -L "$WORK_DIR" ]] || {
    echo 'BLOCKED: browser scratch must be a new exclusive release path' >&2; exit 1;
  }
  mkdir -p "$WORK_DIR/jobs" "$WORK_DIR/data"
else
  # Legacy test runner's established contract is unchanged.
  rm -rf "$WORK_DIR"
  mkdir -p "$WORK_DIR/jobs" "$WORK_DIR/data"
fi

if [[ "${STEMDECK_E2E_ISOLATED:-0}" == "1" ]]; then
  # Reuse verified installed Python and uvicorn. 'uv run' is unnecessary
  # here and often absent from PATH on the Windows installation.
  [[ -n "${N3LX_RELEASE_PYTHON:-}" && -f "$N3LX_RELEASE_PYTHON" ]] || {
    echo 'BLOCKED: isolated backend needs installed Python' >&2; exit 1;
  }
  python_cmd=( "$N3LX_RELEASE_PYTHON" -B )
  backend_cmd=( "$N3LX_RELEASE_PYTHON" -B -m uvicorn )
else
  python_cmd=( uv run python )
  backend_cmd=( uv run uvicorn )
fi

"${python_cmd[@]}" "${REPO_ROOT}/tests/e2e/seed.py" "$WORK_DIR/jobs" >/dev/null

cd "$REPO_ROOT"
exec env \
    STEMDECK_JOBS_DIR="$WORK_DIR/jobs" \
    STEMDECK_DATA_DIR="$WORK_DIR/data" \
    STEMDECK_CACHE_DIR="$WORK_DIR/data/cache" \
    STEMDECK_LOGS_DIR="$WORK_DIR/data/logs" \
    STEMDECK_MODELS_DIR="$WORK_DIR/data/models" \
    STEMDECK_DOWNLOADS_DIR="$WORK_DIR/data/downloads" \
    STEMDECK_ACOUSTID_CHECK_KEY=0 \
    STEMDECK_DISCOGS_CHECK_TOKEN=0 \
    "${backend_cmd[@]}" app.main:app \
        --host 127.0.0.1 \
        --port "$PORT" \
        --log-level warning \
        --timeout-graceful-shutdown 2
