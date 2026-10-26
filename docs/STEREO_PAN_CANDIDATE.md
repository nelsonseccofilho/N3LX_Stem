# Universal stereo PAN — isolated candidate

## User-visible behavior

Every audible lane gains an **L / C / R** slider for stereo placement.
C (or double-click on the slider) recenters it. The range is -100 (L) to
+100 (R). Pan is a playback parameter, not a separation parameter:
existing stereo WAVs, drum reconstruction, stem names/counts, ZIP exports
and playlists are not regenerated.

The implementation uses Web Audio `StereoPannerNode` per **physical playback
source**, between its gain stage and analyser/pitch bus. For the `original`
complement (multiple actual source stems controlled by one logical lane),
a single pan parameter applies to all underlying sources without leaking to
other pitch buses or mixer lanes.

The existing volume, mute, solo and per-lane pitch controls remain intact.
`pan: 0` preserves existing stereo playback. A non-finite pan is reset
to center. Smooth `AudioParam.setTargetAtTime` transitions avoid abrupt
clicks; master limiter and output graph are unchanged.

## Persistence

The existing per-job mix includes `pan` in normalized range [-1, 1].
Setlist `copyMix` copies and clamps this value and old playlists default to
center. Setlist copies are independent. The existing playlist-scoped
persistence code is reused without changing format version or replacing
prior mixes.

## Engine compatibility

- `static/js/audioEngine.js`: full decoded audio, full PAN.
- `static/js/chunkedAudioEngine.js`: chunked WAV audio, full PAN.
- Legacy HTMLMediaElement/multitrack playback or contexts without
  `createStereoPanner`: PAN controls are disabled, existing playback
  continues. There is no false claim of L/R positioning on that path.
- No backend changes or new Python dependencies.

The UI is compact in the existing mixer columns. The saved center value is
silent as a functional change to the legacy mix. No separate guitar L and R
stems are created; splitting a stereo signal into L/R **does not** isolate
distinct instruments recorded together.

## QA gates

Run on a disposable checkout derived from this branch, not over the current
working tree `D:\git\stemdeck` (which contains F23R15 and prior local work):

```powershell
node tests/js/multitrack-playback.test.mjs
node tests/js/setlist.test.mjs
node tests/js/studio-lanes.test.mjs
node tests/js/pitch-shift.test.mjs
```

The two modified tests cover isolated lane PAN, a multi-source logical lane,
lack of StereoPanner support, preservation of stereo decoded PCM and saved
PAN in independent setlists. The full set of baseline JS/Python tests and
actual browser playback QA are still required before merge.

**This is Cycle A.** Cycle B — independent left/right *channel gains*, not two
physical tracks — will be considered on top of a proven Cycle A baseline. It
must preserve stereo center neutrality, handle mono WAV gracefully and avoid
overlap with the pitch/tempo DSP and pan value.

## Isolation / ownership

The karaoke synchronization candidate remains in PR #5; neither workstream
should import or merge the other's changes without separate review.
Remote `main` is older than the already integrated F23R15 Windows checkout.
**Do not merge this branch directly into the local worktree; first reconcile
the actual file hashes and uncommitted diffs, create a backup and run full
regression.** No audio files or personal library data belong in this PR.
