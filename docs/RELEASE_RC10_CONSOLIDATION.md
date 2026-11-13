# v0.21.0-rc.10 — consolidated Windows update candidate

**State: DRAFT, not merged or published.**
Source base: main 1ca88e17d37ecf72e932cecd0a0570ae5949ed98.

## Scope reconciled

- PR #21: version/pinned Electron 44.3.0, isolated one-shot local release preflight,
  desktop-backend lifecycle tests, drum FLOAT and 3-residue export QA.
  The old D:\git rc.9-only preparation script is superseded by
  scripts/windows/Prepare-Windows-Release-rc10.ps1 with default paths under
  the current user profile and exact SHA verification.
- PR #22: shared _workspace Whisper Vulkan and Large v3, modern
  NELX-Whisper-GPU CLI, real CPU alignment label for Portuguese,
  fail-closed result verification, single model in UI/API.
- PR #23: Electron storage preferences, independently configurable
  exports directory and storage dialog; backend guard on populated stems library.

## Deliberately excluded

- The user's dirty local checkout (HEAD a7c1515 with many tracked/untracked
  edits) has NOT been reconciled into this branch. A local checkpoint and
  reviewed comparison are required before asserting functional completeness.
- Existing ~46GB music library has NOT been migrated to D:.
- No changes or deletions of music, project exports, venvs, shared models,
  reusable tests, temporary backups or old releases.
- No standalone installer under Program Files: the update still requires
  an installed AMD/Python runtime.
- No proven Windows ML inference, GPU alignment performance, singing-quality
  accuracy, packaged EXE smoke test, or publicly accessible rc.10 release.

## Read-only local checkout review (required before claiming completeness)

Before running the Windows package preflight, inspect the dirty checkout without
checking out, resetting, stashing, cleaning or moving files. Download and
review `scripts/windows/Inspect-Local-Checkout-rc10.ps1` from the
**exact rc.10 commit** in GitHub first: the dirty local checkout may not yet
contain this new script. Save the downloaded script **outside the repository**,
then run it from PowerShell:

```powershell
& "<downloaded-path>\Inspect-Local-Checkout-rc10.ps1" `
  -Repository "$HOME\Git\N3LX_Stem" `
  -ExpectedSha "<40-character-reviewed-rc10-SHA>"
```

The inspector fetches branch metadata, verifies the exact SHA and common
ancestor, inventories tracked/untracked source changes and identifies paths
also modified by rc.10. It writes a unique **private local** report containing
`inventory.json`, `RESULT.md` and a patch of modified **tracked source** files.
This is **not a complete backup**: untracked source files are listed but not
copied. Preserve them separately before any destructive Git operation.
No music, stems, data folders, GPU models, installs, local worktree files or
existing releases are modified. Do not upload the private patch to GitHub.
**Comparison correction (cycle 4, 13 Nov 2026):** the first inventory
reported 98 overlapping paths because it measured the candidate against the
local HEAD `a7c1515`, which is 69 commits behind remote main. Those 98 paths
are NOT verified conflicts. The revised inspector fetches remote main metadata,
compares only `remote-main..rc.10` for candidate-specific changes, and reports
older main-history overlaps separately. It also includes root build/config
paths when cataloging source. A second, new private report is intentional; the
first report remains unchanged. Neither report is a complete backup.

A zero-overlap list does not prove functional equivalence; review all local
commits and uncommitted changes against rc.10 before signing off completeness.

### Cycle 5 correction — PowerShell Git wrapper

The first local checkpoint attempt stopped with `failed (exit 1); no retry`
before generating a verified checkpoint. Root cause in the source: the
`Git-Lines` helper mistakenly used `$Args` as a named parameter even
though `$args` is a PowerShell automatic variable. Git therefore received
an empty command; the earlier error did not identify the Git arguments.

The helper now uses `$GitArguments` and explicitly rejects missing command
arguments. Re-download the **fixed, exact commit** before the next execution.
The original failed attempt is **not** a verified source backup, and no
Windows execution or success is claimed for the fix. Do not repeat inventory
or patch generation.

## Cycle 5 — protect local source before reconciliation

The corrected inventory run from 13 Nov showed: 49 modified tracked source
paths, 49 untracked source paths, and **7 candidate-specific overlapping
paths** out of 24 changed by the rc.10 candidate. The user also generated a
private patch for seven relevant paths; that patch remains outside GitHub.

Before changing branches, merging or cleaning anything, preserve the untracked
files and the full uncommitted tracked-source state using
`scripts/windows/Checkpoint-Local-Source-rc10.ps1` from the exact reviewed
candidate commit. Download that script into a **temporary location outside
the dirty checkout**, then run it with:

```powershell
& "<downloaded-path>\Checkpoint-Local-Source-rc10.ps1" `
  -Repository "$HOME\Git\N3LX_Stem" `
  -InventoryFile "$HOME\Git\N3LX_Stem-Releases\rc10-local-review-20261113-041743-6eafa00d\inventory.json"
```

This tool reads the earlier inventory and checks that local HEAD and source
file lists remain consistent. It creates a unique private local folder under
`N3LX_Stem-Releases` containing copies of tracked-modified and untracked
source files, a binary tracked-file patch, per-file SHA-256 hashes, and
`manifest.json` / `STATUS.txt`. Only
`SOURCE_CHECKPOINT_VERIFIED` and `CHECKPOINT_VERIFIED` count as success.
If it refuses unsafe files, reports stale inventory, or leaves `INCOMPLETE`,
stop; do not reset the checkout or call the checkpoint complete.

It is **not a full backup of the repository, runtime, music library,
playlists, external models, environments or machine**. No source is
changed; no audio data is copied, and the checkpoint/manifest/patch must
remain private and never be committed or uploaded to GitHub.

Review the seven specific overlapping paths against the local patch and the
current PR #24 code. Preserve karaoke, frontend and other local features;
same-file changes are not proof of conflicting hunks. Only then run the bounded
Windows QA and release preflight.

## Cycle 6 — isolated reconciliation preview (no merge)

The checkpoint was completed on Windows and reported
`SOURCE_CHECKPOINT_VERIFIED`, 49 tracked source files,
49 untracked source files and 98 copies with zero tracked deletions.
Its private location is
`N3LX_Stem-Releases/rc10-source-checkpoint-20261113-043900-3dba8393`.
The private 7-file patch remains on disk; do not upload it to GitHub.

Seven rc.10-specific paths overlap local source. Five are tracked modifications:
`app/main.py`, `scripts/Start-N3LX_Stem.ps1`, `static/index.html`,
`static/js/i18n.js`, `static/js/lyrics.js`.
Two paths were **locally added as untracked files** because they did not exist
in local HEAD `a7c1515`: `app/api/karaoke.py` and
`app/pipeline/karaoke_timing.py`. Treat them as independent additions, never
overwrite them with candidate versions without review.

`scripts/windows/Preview-Local-Reconciliation-rc10.sh` generates a
**private, text-only, isolated, no-write-to-checkout** three-way preview for
these seven paths using files saved in the existing checkpoint:
- For the five tracked paths: candidate vs old local HEAD vs checkpointed
  working version, with CRLF normalized only in scratch copies
- For the two added paths: explicit add/add comparison and collision reporting,
  with **no automatic resolution**
- `summary.tsv` and `RESULT.md` report statuses and conflict marker counts;
  actual source files and merged previews stay local
- No Git reset, clean, checkout, stash, merge commit, changes to the library,
  Python/model install, music export, tests, EXE build or release publication

Download the preview script from the **pinned reviewed GitHub SHA** outside the
dirty checkout and run using Git Bash, passing repo, verified checkpoint and
candidate SHA. Do not treat `AUTO_MERGE_PREVIEW_ONLY` as proof that the
combined behavior works. No results can be claimed until the user's actual
Windows run is inspected. The final `rc.10` branch remains draft.

## Cycle 9 — restore existing automatic lyrics lookup

The private rc.10 reconciliation review found one concrete change in
`static/js/lyrics.js`: when no saved, karaoke sidecar, server-provided or
embedded lyrics existed, the older local application automatically requested
a lookup; the candidate required the user to press the search button.

The existing workflow is restored on the rc.10 draft branch, without
overwriting edits or bypassing karaoke/sidecar precedence:
- An eligible missing-lyrics track triggers `lookUp(info, { song })`
  after all local and server sources have been checked
- An empty search result leaves the **manual retry** button available
- Cached empty results do not initiate another automatic lookup
- Existing protections still prevent searching unknown song metadata

Added `tests/js/lyrics-auto-lookup-rc10.test.mjs` and included it in the
`scripts/verify-local-release.py` bounded JS suite. Eight mocked,
network-free cases were run in an isolated environment against the
candidate source: **baseline 5 passed / 3 failed**; corrected version
**8 passed / 0 failed**, with JS syntax validated. The patched source's
Git blob hash was cross-checked against the committed file.

These checks are not Windows app, LRCLIB network, Electron, AMD/Vulkan,
GPU or full-package QA. The change deliberately preserves prior product
behavior pending a separately validated decision to make lookups manual.
The source checkpoint remains private; 91 other local source files were
not fully reconciled by the seven-path review. Do not merge or publish the
draft release until remaining functional parity and release gates pass.

## Cycle 10 — audit the remaining checkpointed source files

The earlier seven-path private reconciliation resolved what needed a semantic
decision in the rc.10 candidate, including restoring automatic lyrics lookup.
It does **not** cover the other 91 saved source paths (49 tracked changes plus
49 untracked copies in the private checkpoint = 98 total).

The audit script at `scripts/windows/Audit-Local-Source-Parity-rc10.py`
uses ONLY the **previously verified private checkpoint** and Git object reads.
Download it to the `N3LX_Stem-Releases` directory from the **exact reviewed
candidate SHA**, then run it with existing Python 3.12+ and these arguments:

```text
python <downloaded-Audit-Local-Source-Parity-rc10.py>
  --repository <user-home>/Git/N3LX_Stem
  --checkpoint <user-home>/Git/N3LX_Stem-Releases/rc10-source-checkpoint-20261113-043900-3dba8393
  --reports-root <user-home>/Git/N3LX_Stem-Releases
  --candidate <exact-reviewed-rc10-SHA>
```

The audit verifies the checkpoint marker, all saved-file SHA-256 hashes and
tracked patch SHA-256 *before* fetching the candidate. It compares each
checkpoint copy against the original HEAD and exact rc.10 commit, allowing
CRLF-only equivalence without modifying originals. Its **private metadata-only**
`RESULT.md` and `summary.tsv` distinguish:
- Local-only files missing from candidate and local changes not incorporated
- Independent parallel additions (add/add)
- Both sides changed: requires semantic review
- Candidate-only changes and content-equivalent files

The seven previously reviewed paths are labeled separately; the report
classifies all 98 copies but totals the **other 91** for follow-up.
This is a triage, not a verified semantic merge or functional parity claim.
No private source contents, music, GPU models, exports or paths outside the
checkpoint are copied. No Git checkout, merge, reset, clean, stash or build.
Do not commit the private report or checkpoint to GitHub. Share only the
metadata summary after reviewing filenames. Actual Windows execution of
this new audit is pending, as is final parity review and full rc.10 QA.

A synthetic disposable-Git fixture passed end to end for the original audit
implementation, including independent addition, local-only changes, CRLF
equivalence and both-sides-changed classification. The test
`tests/test_rc10_source_parity_audit.py` is included in the bounded Python
release suite. Do not infer a successful Windows invocation or user-data
inspection from this fixture.

## Cycle 11 — private 20-file source parity review (13 Nov 2026)

The owner supplied `rc10-parity-20-private.tar.gz`, containing exactly the
**20 `PENDING_OTHER_FILES` copies** from the already verified 98-file source
checkpoint. They are not included in the repository and were **not** uploaded
to the public PR. Their contents were inspected in a private analysis
environment. Static syntax checks passed on **18 Python/JavaScript files**
(README and CSS excluded).

The review compared the source structure and selected behavior of the private
copies against candidate `911903017f02cd47e325d68eb385408e4f332182`.
The existing named module functions were retained in the candidate's
backend, catalog, mixer, player, transport, section, karaoke and
processing modules; there was no evidence requiring the wholesale replacement
of the candidate with the older local source. This **does not** prove full
internal semantic parity for the larger UI/CSS/backend files.

| Surface | Files | Findings or remaining QA |
| --- | --- | --- |
| Import, multitrack and export | `app/api/router.py`, `app/api/stems.py`, `app/pipeline/complete_multitrack.py` | Core 6-piece drum and reconstruction residual functions remain; candidate adds a dedicated three-residue ZIP endpoint and routes. Test against synthesized source and a representative real song later. |
| Playback and interaction | `static/js/main.js`, `player.js`, `mixer.js`, `transport.js`, `sections.js` | Named existing controls remain, with additional residue export, metronome preview and karaoke section snapshot. Test transport timing, solo/mute, edits and export paths in Windows. |
| Library and data | `static/js/catalog.js`, `job.js`, `sharedUiStore.js` | Existing public functions remain, including resplit target, playlist and settings. Confirm stored library contents, export destination and recovery without migrating the user's data. |
| Karaoke, header, processing | `static/js/headerReextract.js`, `karaoke.js`, `karaokeTiming.js`, `lyricsEditing.js`, `processingStudio.js` | Candidate improves localized reextract staging/disabled checks, fullscreen and section display, and protection against stale generated timestamps; processing errors use a generic message with diagnostics in Settings rather than displaying raw errors inline. Validate interactive states. |
| UI, documentation and tests | `static/css/daw.css`, `README.md`, `tests/js/karaoke-timing-ui.test.mjs`, `tests/test_karaoke_timing.py` | CSS requires rendered UI smoke checks; tests retained and extended. README is updated candidate documentation, not a reason to replace app code. |

**Functional hardening found during review:** in
`timingForMatchingEditedLyrics` the candidate previously accepted a manual
lyric that matched only a *prefix* of the generated Whisper words. The code
claimed exact, in-order alignment, but a missing final word would still
receive generated timing. Now all word counts must match before applying
machine timestamps to edited text. Added regression assertions for full
matches, missing words, and changed words in
`tests/js/karaoke-timing-ui.test.mjs`; original manual text is preserved.
Commits: `935ca6c` (fix) and `6727654` (test). These new test assertions
are committed but **full candidate tests were not executed on the owner's
Windows installation yet**.

No dirty checkout contents, music, models, playlists or private archive were
committed, moved or deleted. No automatic bulk merge is needed based on
the structural comparison alone. **Final status: structural parity reviewed;
functional parity and release gates remain open** until the bounded rc.10
test suite, Windows desktop smoke test, AMD/Vulkan karaoke, 6-drum/3-residue
exports and library data-preservation checks pass.

## Build and QA gate

1. Confirm the checkout has an existing compatible Python 3.12 .venv and
   .venv-directml, and desktop-app/node_modules/electron/dist version 44.3.0.
2. Review the pinned candidate commit and download the PowerShell preparation
   script from that exact commit. Pass -ExpectedSha equal to it.
3. The script fetches the release ref (no git pull/reset/clean), validates
   the expected SHA, creates a detached worktree in a new Releases directory,
   runs a single bounded QA pass with synthetic/isolated data, builds the
   Windows ZIP and N3LX_Stem.exe, validates ZIP+SHA256 and package metadata.
4. Review local-QA/RESULT.md, summary.json and release-preflight.json.
   A failed step stops; do not repeat tests in a loop.
5. Start the packaged EXE on Windows against the existing AMD runtime,
   after closing all other backends; confirm one-instance ownership,
   playback of representative existing music, 6 drum sub-stems, 3 residues,
   Library persistence, Portuguese large-v3 karaoke with actual GPU Vulkan
   log confirmation, and export WAV/ZIP to custom D: folder.
6. Confirm migration is blocked for nonempty stems library; do not call the
   old copy/move routine to relocate 46 GB.
7. Only after the approved code matches expected user-facing features and
   real Windows QA passes, decide whether to merge/tag/publish.

## Cleanup policy

Never delete tests from Git: they are not packaged into the EXE. After
rc.10 is validated and a rollback EXE is retained, remove ONLY identified
redundant temporary QA worktrees, old environment backups and generated
builds. Git worktrees must be detached and unregistered safely first;
the 46GB data directory, shared models/venvs and uncommitted edits are excluded.
