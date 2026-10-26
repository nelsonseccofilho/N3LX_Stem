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

## Next implementation gates

1. Validate actual Vulkan GPU dispatch and timecodes against a real song
   using existing `whisper.cpp` and the RX 6600M. A CLI exit code is not
   evidence of correct GPU execution or musical alignment.
2. Add one GPU-serialized on-demand job API for **generate/regenerate** on
   existing stems, including cancellation, state and download.
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

The isolated prototype passed 9 contract tests; no real RX 6600M model was
executed and no end-to-end API/UI verification has been claimed.
