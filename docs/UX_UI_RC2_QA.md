# 0.21.0-rc.2 - appearance, trash and karaoke

## Behavior
- Settings > General > Theme: System default (initial default), Dark or Light.
  System follows live OS changes; explicit choices stay fixed. Preference uses
  the shared UI store and is cached for the first paint. Electron title-bar
  appearance uses a restricted, validated preload bridge. Existing playlists
  and per-song mixes are preserved.
- Trash: an explicit Restore button per row, reachable by keyboard. The old
  hold/drag shortcuts remain compatible, but button presses never trigger holds.
- Empty trash: a modal names a single item or the total item count. Cancel is
  focused initially; Escape cancels. Only the IDs shown in the confirmation are
  removed; later additions to trash are excluded from that operation.
- Mixer: track name above PAN, followed by the meter. No audio graph changes.
- Karaoke: a visible model selector, Generate again and Delete generated karaoke.
  Large v3 is the default; Medium is an explicit alternative. No silent model
  downgrade. Regeneration preserves a backup. Deleting the generated sidecar
  preserves manual lyrics, stems and mixes, and archives that sidecar privately.
  A per-job processing claim rejects deletion while lyrics work is active.

## Bounded evidence
- 22 Python tests passed, one skipped because Windows cannot create symlinks.
  Tests cover sidecar-only deletion, busy-job rejection, path protection,
  explicit model paths, no silent downgrade and preservation of shared mixes.
- Five JS test files passed: theme, shared store, karaoke timing, karaoke UI
  and processing/library navigation. Theme tests include live system changes,
  fixed overrides and a late-startup preference race.
- 23 browser checks passed with synthetic audio and lyrics, including Light,
  Dark, live System changes, persistence, name/PAN order, restoring a song,
  named/count deletion confirmation, cancellation, and karaoke deletion without
  removing manual lyrics. The generated-model request was intercepted so this
  browser test never launched an audio model.
- One separate public-audio probe used the already-installed ggml-large-v3.bin
  with whisper-cli Vulkan, device 0, and a 6000 ms duration option. Logs name
  RX 6600M, use_gpu=1 and Vulkan0 backend. The result normalized successfully.
  Worker output/timings were collected; process exit status was not retained by
  the launcher. This does not assess sung-lyrics quality or all CPU/GPU stages.
- No private track was re-extracted or transcribed. Original checkout and data
  are outside the QA directories. No model/runtime installation was performed.

## Distribution
The Windows update still requires the existing AMD Python environments, FFmpeg
and local weights. The Large v3 file must be installed alongside the configured
Whisper model or supplied through N3LX_WHISPER_LARGE_MODEL. Missing weights fail
explicitly; they never cause a silent switch to Medium or CPU.

The build recipe includes the appearance preload and frontend/backend source.
The package launch and remote checksum results accompany the release assets.
Main merge remains pending while GitHub Actions is blocked by account billing;
local QA and a prerelease do not claim a successful hosted CI run.

Vulkan and model reference: https://github.com/ggml-org/whisper.cpp#vulkan-gpu-support
