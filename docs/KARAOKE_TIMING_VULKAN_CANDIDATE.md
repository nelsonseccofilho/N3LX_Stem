# Karaoke word timing — candidate, not integrated into production

## Scope and safety

This workstream is intentionally **isolated from the six-stage F23R15 local integration**.
The production checkout at `D:\git\stemdeck` has uncommitted work that is
newer than GitHub main. **Do not merge or copy the entire branch over local
files** before reconciling the local diff.

First implemented capability: a standalone word-timecode sidecar generator
that can operate on an existing `vocals.wav` or any separate MP3/WAV.
It does not edit, delete or re-separate stems, `lyrics.json`, playlists or mixes.

## Output

`lyrics_timing.json` is a sidecar distinct from the existing canonical
`lyrics.json`. Its word entries are `{"text", "start", "end"}` seconds
relative to the input audio; it also stores an enhanced-LRC **preview**.
`timing_status: machine_unverified` is intentional: generated text and timing
may be wrong for music. `gpu_verified: false` means the CLI invocation
requested device 0 but real Vulkan dispatch has not yet been attested.

The existing application karaoke UI **does not read this sidecar yet**.
Later phases will connect it to `lyrics_retime.py` and the existing lyrics
presentation, without replacing a user-authored `user_synced` result.

Regeneration is explicit: `--replace` first stores the previous sidecar
under a uniquely named timestamped backup, then atomically replaces it.
Without `--replace`, an existing sidecar is never overwritten.

## Usage after the code is locally reviewed / reconciled

Supply paths to the exact Vulkan-built `whisper-cli.exe` and a local ggml
model file already installed. Do not install models or drivers as part of
this test. Run from the repository root with the existing .venv:

```powershell
& .\.venv\Scripts\python.exe -B -m app.pipeline.karaoke_timing `
  --audio 'D:\path\to\your\vocals.wav' `
  --output 'D:\path\to\lyrics_timing.json' `
  --whisper-cli 'D:\path\to\whisper-cli.exe' `
  --model 'D:\path\to\ggml-medium.bin'
```

For an existing sidecar, add `--replace` only after checking its provenance.
The command uses ffmpeg to create a temporary mono 16-kHz WAV and runs
`whisper-cli -dev 0 -ml 1 -sow -ojf`, without `--vad`.
Known whisper.cpp versions have a segment/token timestamp axis mismatch when
the VAD removes silence; see ggml-org/whisper.cpp issue #4046.

## On-demand endpoint candidate

The new `app/api/karaoke.py` router is explicitly opt-in. The backend
process requires these two environment variables to point at pre-existing
local files (no downloads/installs):

- `N3LX_WHISPER_CLI`: path to a Vulkan-built whisper-cli executable
- `N3LX_WHISPER_MODEL`: path to a local GGML model

The route is not usable without these settings. After controlled local
reconciliation and service restart:

- `POST /api/jobs/{id}/karaoke/generate` with body `{}` to create the
  sidecar for an existing `vocals.wav`; or `{"replace":true}` to regenerate
  while preserving the previous sidecar as a separate backup;
- `GET /api/jobs/{id}/karaoke/status` to check the result;
- `GET /api/jobs/{id}/karaoke/timing` for the normalized JSON;
- `GET /api/jobs/{id}/karaoke/lrc` for a preliminary enhanced-LRC preview;
- `POST /api/jobs/{id}/karaoke/cancel` to cancel the active sidecar task.

The service uses the existing global pipeline lock and lyrics retime run
registry for GPU serialization and cancellation. It **does not** overwrite
`lyrics.json`, automatically replace a manual `user_synced` timeline, or
yet connect this sidecar to the actual karaoke UI.

Two additional on-demand service tests were exercised with isolated
stubs (no real repository installation), alongside 10 pure timing tests.
Full integrated API regression is still pending.

## Next implementation gates

1. Validate actual Vulkan GPU dispatch and timecodes against a real song
   using existing `whisper.cpp` and the RX 6600M. A CLI exit code is not
   evidence of correct GPU execution or musical alignment.
2. Run the GPU-serialized on-demand job API end-to-end on the locally
   reconciled project, including cancellation, state and download.
3. Add isolated upload-only karaoke workflow for files with no stems.
4. Integrate `lyrics_timing.json` with `lyrics_retime.py` and the karaoke
   UI. Prefer a verified existing lyric text over transcription guesses.
5. Add opt-in post-extraction automatic sync; ensure failed ASR does not
   invalidate the completed stems, and preserve legacy 7/8-step histories.
6. Pass full regression and destructive-data safety audit before enabling
   defaults or merging.

## Contract tests

```powershell
& .\.venv\Scripts\python.exe -B -m pytest tests/test_karaoke_timing.py -q
```

The isolated prototype passed 10 pure contract tests and 2 service-stub tests; no real RX 6600M model was
executed and no end-to-end API/UI verification has been claimed.
