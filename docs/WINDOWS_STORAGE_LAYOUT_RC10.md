# Windows storage — candidate for next release (not yet published)

Separate three independently managed areas:
- App update EXE + existing AMD Python runtime: not a standalone Program Files installer.
- Multitrack library: proposed D:\N3LX_Stem_Lib\Stems (jobs, registry, original audio, WAV tracks, lyric timing, projects).
- Exports: proposed D:\N3LX_Stem_Lib\Exports (WAV, ZIP, mixes, loops).
- Data/settings.json, caches, logs, shared models and Python envs remain separate.

## Implemented in this draft

1. New Storage dialog from Settings that reads the current multitrack path.
2. Independent export directory picker via secure Electron IPC, persisted in per-user profile outside EXE.
3. Save As defaults to configured folder for new downloads; user can still override each filename/destination.
4. Missing external export drive falls back to Downloads without forgetting the saved path.
5. Electron sets STEMDECK_DESKTOP=1 for its spawned backend (reuses PR #21 idea), and passes a settings mirror path.
6. Crucial safety: the dialog and backend forbid relocating a populated multitrack library.
   Only configuring a genuinely empty new library is supported in this cycle.

## Explicitly NOT implemented

- No move/copy/delete of any existing ~46 GB music library.
- No cleanup of old source directories.
- No new standalone installer or release EXE.
- No promise that ONNX/DirectML alignment is validated.

## Before migrating existing stems

The legacy move_library() operation moves files individually across drives and
can leave a partial relocation after failure. It must NOT be invoked on the
user’s populated library. A later gated migration needs: destination free-space
check, immutable checkpoint, copy-first plus hashes, quiesced writes, atomic
setting switch, restart, verification of representative music/stems/lyrics,
playlists and metadata, and rollback. Source deletion is a separate decision.

## QA and release

This branch is based on the draft PR #22; it must be reconciled with draft
PR #21 and the uncommitted local checkout before any new Windows package.
Run one isolated bounded test pass and inspect results:

    .venv\Scripts\python.exe -m pytest -q tests/test_stems_location.py tests/test_karaoke_workspace_large_v3.py
    node --test tests/js/desktop-storage-paths.test.mjs
    node --check desktop-app/main.cjs
    node --check desktop-app/preload.cjs
    node --check static/js/storageSettings.js

Then Windows QA: choose exports folder, save WAV/ZIP, restart persistence,
missing external D: drive fallback, and legacy music remaining intact.
Neither those tests nor a real Windows build has been executed in this draft.
