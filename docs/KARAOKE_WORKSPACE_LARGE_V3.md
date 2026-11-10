# N3LX_Stem karaoke: shared Windows workspace / Large v3 only

Scope: Windows 10, new local Git root, existing AMD RX 6600M, installed NELX-Whisper-GPU.
This revision corrects resource discovery and the **opt-in karaoke** worker interface.
It does not modify any saved audio, existing jobs, playlists, manual lyrics or models.

## Resource paths

By default `scripts/Start-N3LX_Stem.ps1` discovers these paths from `RuntimeRoot`:

- `../_workspace/tools/whisper.cpp/build-vulkan-nmake/bin/whisper-cli.exe`
- `../_workspace/models/ggml-large-v3.bin`
- `../NELX-Whisper-GPU/src/transcrever_gpu.py`
- `../_workspace/venvs/whispergpu/Scripts/python.exe`

Use `N3LX_WHISPER_CLI`, `N3LX_WHISPER_LARGE_MODEL`,
`N3LX_WHISPER_GPU_HOME`, and `N3LX_WHISPER_GPU_PYTHON` to override.
The model **Large v3** is mandatory in the user interface and API; `medium`
is rejected rather than substituted.

The modern worker is invoked with the installed CLI contract:
`--model large-v3 --device vulkan --gpu 0 --language pt --threads 6 --no-diarize --output-format json --output-dir ...`,
plus explicit `--whisper-model` and `--whisper-cli`. It does **not**
receive the legacy `--no-preload-align` or `--output-profile` flags.

For Portuguese, the *current* `src/transcrever_gpu.py` performs ASR on
whisper.cpp/Vulkan and alignment on **WhisperX/CPU**. The ONNX Portuguese
alignment model under `_workspace/models/alignment/onnx-pt.staging` is not used
or claimed ready. A legacy DirectML worker remains recognized only when all
of its original prerequisites are present.

For English, the existing whisper.cpp/Vulkan word timestamp path remains
in use and does not require the Portuguese aligner.

## Validation gates

The worker is **not** accepted when it exits with code 2 (partial alignment),
code 1 (error), when no integrated JSON/quality report exists, or when its
report fails to verify Vulkan or the selected alignment backend. Failed jobs
must not replace existing saved lyrics, stems, or timing JSON.

Test commands from an isolated checked-out copy:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_karaoke_workspace_large_v3.py tests/test_karaoke_timing.py tests/test_karaoke_service.py
node --check static/js/lyrics.js
```

Do not assume test success from the existence of this document. Run the tests,
then validate the button and one opted-in karaoke job against real Windows
resources. The package `0.21.0-rc.9` is **not** automatically rebuilt by this
change. A Windows update requires separate package/build/release QA.
