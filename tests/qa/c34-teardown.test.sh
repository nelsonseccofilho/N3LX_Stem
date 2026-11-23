#!/usr/bin/env bash
# Pure mock state-machine tests: no ports opened or real processes modified.
set -euo pipefail
repo="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
source "$repo/scripts/qa/c34-teardown.sh"
scratch="$(mktemp -d)"
# The production helper's delay is not necessary when transitions are mocked.
sleep() { :; }
scenario=""
checks=0
stops=0
closed=0
status_calls=0

qa_backend() {
  local action="$1"
  case "$action" in
    verify-free)
      checks=$((checks+1))
      case "$scenario" in
        free) return 0 ;;
        race|stoprace) ((checks>=2)) ;;
        owned) ((closed==1)) ;;
        foreign|busy) return 1 ;;
        *) return 1 ;;
      esac
      ;;
    check-ready)
      [[ "$scenario" == owned || "$scenario" == stoprace ]]
      ;;
    stop)
      stops=$((stops+1))
      if [[ "$scenario" == owned ]]; then
        closed=1
        return 0
      fi
      return 1
      ;;
    status)
      status_calls=$((status_calls+1))
      [[ "$scenario" == busy ]]
      ;;
    *) return 1 ;;
  esac
}

run_case() {
  local name="$1" expected_status="$2" expected_stops="$3"
  scenario="$name"
  checks=0;stops=0;closed=0;status_calls=0
  local out="$scratch/$name"
  mkdir -p "$out"
  local status=0
  c34_safe_teardown "$out" > "$out/output.log" 2>&1 || status=$?
  [[ "$status" == "$expected_status" ]] || {
    echo "FAIL $name: exit $status expected $expected_status"
    cat "$out/output.log"
    exit 1
  }
  [[ "$stops" == "$expected_stops" ]] || {
    echo "FAIL $name: stop calls $stops expected $expected_stops"
    exit 1
  }
  if [[ "$expected_status" == 0 ]]; then
    grep -q '^PASS:' "$out/output.log" || exit 1
  else
    grep -q '^BLOCKED:' "$out/output.log" || exit 1
  fi
  echo "PASS C34 teardown: $name"
}

run_case free 0 0
run_case race 0 0
run_case owned 0 1
run_case stoprace 0 1
run_case foreign 1 0
run_case busy 1 0
echo "PASS C34 teardown: 6/6 isolated contract cases"
echo "Evidence: $scratch"
