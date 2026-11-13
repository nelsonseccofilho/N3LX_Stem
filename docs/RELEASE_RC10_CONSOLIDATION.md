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
checking out, resetting, stashing, cleaning or moving files. From PowerShell,
use the script committed at the **reviewed, exact rc.10 SHA**:

```powershell
& "$HOME\Git\N3LX_Stem\scripts\windows\Inspect-Local-Checkout-rc10.ps1" `
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
A zero-overlap list does not prove functional equivalence; review all local
commits and uncommitted changes against rc.10 before signing off completeness.

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
