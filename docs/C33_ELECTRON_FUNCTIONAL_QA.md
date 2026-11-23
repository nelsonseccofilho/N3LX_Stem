# C33.1 — Electron functional integration QA (synthetic library)

This extends the **already validated C32** Git Bash launcher rather than
introducing a second lifecycle mechanism. No personal port, job, or app profile
is used. The C32 renderer-only smoke remains unchanged when the new scenario
flag is absent.

## Running on the Windows development host

In a clean checkout/worktree of the C33 branch, with the existing runtime:

`N3LX_C32_RUNTIME="$HOME/Git/N3LX_Stem" N3LX_C33_FUNCTIONAL=1 bash scripts/qa/c32-electron.sh`

The harness selects a new free loopback port, starts only the controlled isolated
backend with two synthetic jobs, seeds a **silent 2-second black video** in that
QA directory, opens the real development Electron app and runs the C32
three-viewport smoke. Then `c33-functional.mjs` runs:

1. Six-second synthetic WAV playback: clock advances, Stop resets.
2. Mixer mute/solo toggles through the actual Electron UI.
3. Loop bounds edited and read back from the UI.
4. Real API WAV PCM16 stereo mixdown, including numeric hard-left pan check.
5. Real API MP4 mux containing both video and audio streams; both exported files
   verified using the host's existing FFprobe.

The only new files written at runtime are in a unique
`C33-Electron-XXXXXXXX` directory outside the repository:
synthetic tracks, test video, API-exported WAV and MP4, screenshots and logs.
The same C32 teardown closes the SSE, waits for requests, checks identity,
stops cooperatively and verifies the test port was released. Never force-stop
a service or use the real music library to run this test.

This verifies the renderer, UI interaction and short synthetic exports; it does
**not** certify the installed Windows release, hardware sound output,
full-length export performance, vocal separation accuracy, or GPU inference.

## Gate and review

- Confirm four port-selection tests and shell/Node syntax tests.
- Require `electron-qa.json` with `scenario: C33-functional`,
  `passed: true` and nine result entries (3 renderer sizes + 6 functional assertions).
  There are six functional entries: playback, mixer, loop, WAV, MP4; the
  renderer sizes are three. Total eight entries.
- Require `PASS: owned QA backend stopped and port released`.
- The previous C33 base gate on main had 20/20 Python export/transpose tests,
  12/12 loop, 8/8 transport, 21/21 pitch and volume controls PASS. Those are
  historical baseline results, not a replacement for this live integration run.

Keep the PR draft until the actual Windows QA output is available. CI jobs may
be skipped under the repo's billing guard; skipped is not PASS.
