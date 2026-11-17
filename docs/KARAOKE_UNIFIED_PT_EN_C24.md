# Ciclo 24 — Karaoke unified alignment (PT-BR and English)

Status: **Draft / not approved for release**. This specification applies to the PR based on the Cycle 23 automatic-sync UI branch; it is not part of a tagged Windows release.

## Product contract

1. Same steps in Portuguese and English: select song, generate karaoke from existing vocals, optionally correct text, auto-synchronize, listen, optionally fine-tune line starts.
2. ASR: Whisper Large v3 through whisper.cpp **Vulkan AMD GPU 0** for PT and EN.
3. Acoustic alignment: WhisperX **CPU** with a language-specific model. Never substitute raw whisper.cpp word estimates without explicit user-facing change/approval.
4. Source of truth for wording: the user's corrected lyrics. Automatic transcription is only time evidence, not permission to overwrite edited words.
5. Prefer existing validated WhisperX word timestamps in `lyrics_timing.json` when applying the `lyrics/retime` line-matching algorithm. Do **not** run Whisper Large v3 again just to synchronize text when the sidecar is usable.
6. Persist manually confirmed timings ahead of automatic aligned timings; never shift all lines to compensate for one erroneous vocal onset.
7. Failed/mismatched/low-confidence results keep existing text and timing. No stem extraction (Demucs/DrumSep) is part of this workflow.

## Backend behavior

`app/pipeline/karaoke_timing.py::generate_timing(language=pt|en)` launches the same modern `NELX-Whisper-GPU/src/transcrever_gpu.py` worker, supplying `--language pt|en`, `--device vulkan`, `--no-diarize`. It verifies the worker's Vulkan recognition, successful WhisperX alignment and the returned language before accepting a sidecar. Legacy DirectML alignment is only supported on the existing Portuguese path.

WhisperX alignment model defaults:
- Portuguese: `jonatasgrosman/wav2vec2-large-xlsr-53-portuguese`, Hugging Face cache, already proven on the QA host.
- English: `torchaudio.pipelines.WAV2VEC2_ASR_BASE_960H`, checkpoint `wav2vec2_fairseq_base_ls960_asr_ls960.pth` in `TORCH_HOME/hub/checkpoints` or the XDG/default torch cache. **A cached checkpoint is required** before the EN action becomes available; the karaoke endpoint does not silently download it.

`app/api/karaoke.py` persists `vocals: [size,mtime_ns]` in the sidecar after verifying the source stem stayed unchanged. `lyrics_retime.py::read_karaoke_transcript` only accepts a bounded, chronological, language-matched, GPU-verified WhisperX/CPU sidecar from the same vocals source; for pre-signature legacy sidecars it additionally requires a modification time not older than the source stem. If the sidecar is unusable, the previous cached-transcript and original retime paths remain available.

**Current limitation:** the corrected-text synchronization reuses verified WhisperX word timestamps and fuzzy line matching; it is not yet a second acoustic forced-alignment pass over every corrected word. A separate per-word forced-align refinement would require targeted CPU alignment and its own QA. Timestamps remain `machine_unverified` until checked by listening.

## Preflight without processing audio

On the QA Windows host, use the dedicated WhisperGPU environment to check installation:

```powershell
$py = Join-Path $env:USERPROFILE 'Git\_workspace\venvs\whispergpu\Scripts\python.exe'
& $py -c 'import whisperx, torch, torchaudio; print(torch.__version__); print(torchaudio.__version__)'
```

For English, verify the **effective TORCH_HOME/XDG_CACHE_HOME** of the QA server before starting generation. If the checkpoint is missing, install/cache it as a separate, explicitly authorized one-time setup; do not attempt EN generation repeatedly in offline mode.

## Tests and safeguards

Focused CPU-only tests:
- `tests/test_karaoke_timing.py`: PT/EN both use the same modern Vulkan+WhisperX worker, same quality report, no fallback to `-ojf`; reject missing EN cache.
- `tests/test_karaoke_sidecar_retime.py`: language identity, source-stem identity, bounds and chronological words, reject unverified/raw backend, reuse without invoking ASR.

Commands (in a disposable worktree, not the original production library):

```bash
python -m pytest -q tests/test_karaoke_timing.py tests/test_karaoke_sidecar_retime.py
python -m ruff check app/pipeline/karaoke_timing.py app/pipeline/lyrics_retime.py app/api/karaoke.py tests/test_karaoke_timing.py tests/test_karaoke_sidecar_retime.py
python -m ruff format --check app/pipeline/karaoke_timing.py app/pipeline/lyrics_retime.py app/api/karaoke.py tests/test_karaoke_timing.py tests/test_karaoke_sidecar_retime.py
```

**Acceptance gate:** a previously unseen PT song and a previously unseen EN song each show correct recognized lyrics, timing, edit+resync behavior, proper playback, reloading persistence and original-library isolation. PT “Princesa caiçara” first-phrase reference is 00:22; accuracy requires auditory validation, not just screenshot or matching word count. Do not mark the Draft PR or an rc package approved without those checks.

Do not overwrite `N3LX_Stem/data`, its registry, `ui-store.json` or the 52-job original library.
