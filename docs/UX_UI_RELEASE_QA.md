# UX/UI and i18n release candidate - 0.21.0-rc.1

## Reconciliation and scope

Release base: main a7c151565b7bd7609f91eef10e00d5daa5221985.
The local checkout was copied without Git metadata, environments, data, audio,
weights or logs into an independent clone. A source snapshot and binary diff
were retained privately before editing. All 569 eligible source files were
compared afterwards: no source file in the original checkout changed.
The original branch and uncommitted Git status were preserved.

The library contains 51 catalog tracks. settings.json retained its initial hash.
The existing application and servers remained active; ui-store.json changed
during the session. Do not claim a frozen or byte-identical live library.
No release operation writes to the original data directory. QA uses a separate
seeded data/jobs directory and the package smoke test uses another isolated one.
Private catalog contents and audio are excluded from Git and release artifacts.

Reviewed draft branches:
- PR #7 / feature/compact-header-v2-residual-pitch-20261026: header V2/V3 and
  re-extract modules match installed copies. Installer assets are retained for
  historical compatibility, not rerun. The local constants retain additional
  guitar/drum lanes and the tonal residual pitch behavior.
- feature/mixer-universal-pan-20261026: audioEngine, chunkedAudioEngine and
  stereoPan match. Local mixer/player/setlist additions preserve per-playlist
  mixes, inherited guitar controls, processing state and navigation fixes.
- feature/karaoke-vulkan-timing-20261026: API/tests match. The local parser's
  millisecond conversion and single-word segments are retained; timings are
  still explicitly machine-unverified.

## User-visible corrections

Settings sections no longer shrink into each other; its dialog, scroll area,
select controls and footer remain readable in compact windows. Categories have
selected state, linked tab panels and arrow/Home/End navigation. Tab is contained
in the dialog, Escape closes it and focus returns to the opener. Language changes
keep the active category and language control focus.

Dynamic header controls wait for the saved language on startup. PT uses Formas
de onda, pistas, Mesa de mistura and localized extraction dates. Analysis names
wrap instead of disappearing into ellipses. PT/EN re-extraction explanations are
consistent. Timing downloads and main failure states use readable copy; diagnostics
remain in their explicit settings views.

Re-extract delegates to the existing resplit endpoint, creates a separate job
and preserves the original song/mix. It reflects an in-flight request, recovers
on a rejected request and blocks while a different import is staged. Waveform
and Karaoke panels expose the same selected/hidden state to assistive technology;
arrow navigation wraps and never moves focus to a disabled processing tab.

## Focused QA (bounded, no real model loop)

- Browser: 25 checks passed using installed Microsoft Edge. PT/EN initial render,
  Settings 1280/1080/800/640 px, tab semantics, focus wrap/restore, Karaoke panel
  navigation and failed/staged re-extraction. No page execution errors.
- Python: primary run 114 passed; one test could not create a Windows symbolic
  link (WinError 1314). Only that test was made platform-aware and rerun: skipped.
  The link rejection assertion remains enforced on systems supporting symlinks.
  Includes real API resplit behavior with the pipeline stubbed, original audio
  retention, independent new identity, UI store, progress and karaoke contracts.
- JS: 12 of 13 files passed initially, including 21 DSP and 55 audio-routing
  assertions. The remaining assertion expected tonal residuals to ignore pitch,
  contradicting PR #7. It was corrected; only studio-lanes was rerun and passed,
  including explicit preservation of drum residual pitch protection.
- Follow-up visual checks cover final date/analysis-label corrections separately.

## Windows package contract

This is an update ZIP containing N3LX_Stem.exe, Electron and application sources.
It requires the existing AMD installation (.venv and .venv-directml), FFmpeg,
workers and model weights. It is not a standalone ML installer. Extract the whole
ZIP and choose the existing installation on first launch. Close its old server
before opening the same library with the new version. The release uses its own
UI profile, the existing shared library and a server with verified instance/version
identity. It neither installs packages nor downloads weights during packaging.
SAM source resolution and the user's existing Whisper Vulkan installation are
preserved; GPU fallback policy and model execution are not changed by this review.

The build recipe refuses an existing destination or uncommitted tracked changes,
checks the installed Electron version against its pin, packages tracked source
only, excludes private runtime/media, and verifies the ZIP plus SHA-256 manifest.
Actual package launch evidence is recorded with the release assets after build.
A UI smoke test does not prove real AMD separation or Vulkan inference quality.

## Final release state

The Windows executable was launched: packaged app and backend version 0.21.0-rc.1,
verified instance identity, DirectML selected, Settings and Karaoke visible using
a synthetic library. No real separation was run. The final package includes
the additional narrow-window library drawer so waveforms retain usable width.

GitHub Actions did not start any runner: the account is locked due to a billing
issue (run 40434685551). No rerun was requested. Main merge remains pending;
the verified Windows artifact is a prerelease candidate on the release branch.
