# C27.10H validation — 2026-11-17

Branch: fix/c2710h-initial-header. Production API PID 24480 remained running.
Edge intercepts HTML/CSS/JS from this worktree; non-GET requests are blocked.
No audio, lyric, sidecar or library mutation is authorized by these tests.

## Cinema

`node tests/karaoke-visual-qa.mjs` exercises CPM22 with the existing API.
1920x1080, 1440x900, 1366x786: fullscreen entry/exit, focus return,
Escape, unique pitch controls, G→A (+2), G→F (-2), reset G.
At 1920: instrumental at 75s and 83s; preview at 78.5s and 88s;
end message at 229s. Preview has no singing word. Seek reconstructs state.
Playback crosses 80.3s; paused clock and word DOM remain stable for 500ms.
This validates presentation against stored timings, not acoustic accuracy.
Evidence: ../karaoke-gap-evidence (screenshots and temporal-results.json).

## Header

`tests/c2710h-header.mjs`: cold/reload/cache-clear/warm, delayed modules,
JS disabled import via keyboard, idempotent observers, selection, playback.
Recorded first/final form heights: 40/40, 40/40, 110/110 pixels.
At 1366 topbar reserves 120px; controls remain inside card and above body.
Selected-track reload returns the empty Studio; automatic restore is not asserted.
Evidence: ../c2710h-final-complete/results.json and associated screenshots.

No merge/push. Header and Cinema must be reviewed as separate commits.
Chord panel remains out of scope: existing lv-chordia data are estimated.

## PR #27 integration

Integrated by fast-forward: Cinema `af3c57e`, header `8f8bb19`.
Integration branch: `integration/c27-consolidated-20261116`.
Local main remains `7b905c0`; remote main observed at `1ca88e1`.
Python integration selection: 28 passed, 1 skipped (not counted as PASS).
Browser suites rerun against integration worktree assets, production API read-only.
Header integration evidence: ../c2710h-integrated-evidence.
The redundant diagnostics backup is removed only from tracking; the local
copy and Git history remain available, and all its top-level definitions
exist in the production module. No library files are part of these commits.
Hosted CI jobs have an upstream-only repository condition in ci.yml and
therefore skipped jobs do not certify this fork. No protection was disabled.
Temporary inspection/staging scripts remain untracked, outside the PR.
