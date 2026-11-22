# C32 — Port lifecycle / Electron QA

The production controller in `scripts/backend_control.py` already implements
authenticated ownership checks, busy/in-flight protection, cooperative stop,
verification of free port, start and health check. It never adopts or kills an
unknown process. **Do not restart the personal backend solely for QA.**

Run `bash scripts/qa/c32-electron.sh` in **Git Bash** on Windows.
It selects an available ephemeral loopback port (never 8159 or 8162), runs
`verify-free` and the existing guarded `restart` path. If an unknown
process wins a race for the candidate, the controller blocks instead of
terminating it. Teardown invokes cooperative `stop` followed by `verify-free`
even on failure; an occupied port remains a reported failure, not an excuse
for force-killing the process.

The script creates a unique `C32-Electron-XXXXXXXX` directory outside
Git with two synthetic jobs, an isolated shell/profile, logs, renderer
screenshots for 1920x1080, 1440x900 and 1366x786, and
`electron-qa.json`. It does not download models or generate karaoke.
It requires an existing Python AMD runtime, installed Electron, and Playwright
in the runtime's node_modules. It does not install dependencies or delete
old evidence.

This is **Electron development renderer smoke QA**, not native Win32 window
resizing, the packaged installer, complete playback/export acceptance,
acoustic alignment certification, or a hosted CI pass. No pass is claimed
until execution on the actual Windows development machine.

## Automated tests

`node --test tests/js/qa-port-selection.test.mjs`

Checks free candidate selection, occupied-port rejection without terminating
the owner, invalid ports and bounded failure. The existing Python suites
`tests/test_backend_lifecycle.py` and `tests/test_restart_backend_sh.py`
cover authenticated stop, busy/in-flight refusal and ordered restart.

## Framework rule

1. Verify ownership and running tasks before stopping any process.
2. Stop only owned idle instances cooperatively; verify free port before start.
3. Never kill, adopt or overwrite an unknown instance or real job directory.
4. Choose a different free QA port instead of interfering with personal ports.
5. Verify PID/identity, data directory, health and job IDs after startup.
6. Keep logs/evidence on failure and never treat skipped CI as passing.
