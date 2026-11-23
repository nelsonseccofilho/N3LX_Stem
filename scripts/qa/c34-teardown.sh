#!/usr/bin/env bash
# Called only by C34 Git Bash package QA and isolated mock tests.
# No kill/adoption: check-ready authenticates controller, exact code, runtime
# and data and refuses a busy backend before stop.
c34_safe_teardown() {
  local report="$1"
  local attempt
  for ((attempt=1; attempt<=30; attempt++)); do
    # The parent watchdog can release the listener at any instant. Check free
    # FIRST on each iteration, even after a failed authenticated status call.
    if qa_backend verify-free > "$report/free.log" 2>&1; then
      echo 'PASS: QA port verified free after packaged close'
      return 0
    fi

    if qa_backend check-ready > "$report/ready.log" 2>&1; then
      if qa_backend stop > "$report/stop.log" 2>&1; then
        if qa_backend verify-free > "$report/verify.log" 2>&1; then
          echo 'PASS: packaged QA backend stopped cooperatively; port released'
          return 0
        fi
      fi
    fi

    # A status request can return ECONNREFUSED after the first free-port check
    # was negative. Do NOT call it a persistent unknown owner until a bounded,
    # passive recheck confirms the port is still not free.
    if ! qa_backend status > "$report/status.json" 2> "$report/status.err"; then
      if qa_backend verify-free > "$report/free-after-status.log" 2>&1; then
        echo 'PASS: QA port released during controller status check'
        return 0
      fi
    fi

    if ((attempt < 30)); then sleep 0.5; fi
  done

  echo 'BLOCKED: QA port was not verified free after bounded grace; no forced termination' >&2
  if [[ -s "$report/status.err" ]]; then
    tail -n 5 "$report/status.err" >&2
  fi
  return 1
}
