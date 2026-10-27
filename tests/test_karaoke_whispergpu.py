"""Test the WhisperGPU JSON boundary without a model or private audio."""
import json
import sys
from pathlib import Path

import pytest
from app.pipeline import karaoke_timing as k


@pytest.fixture
def worker(tmp_path, monkeypatch):
    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"synthetic audio")
    model = tmp_path / "ggml-large-v3.bin"
    model.write_bytes(b"synthetic model")
    script = tmp_path / "fake_worker.py"
    script.write_text('''import json, pathlib, sys, time
root = pathlib.Path(sys.argv[sys.argv.index("--output-dir") + 1])
assert "--no-diarize" in sys.argv and "--language" in sys.argv
print("[2/4]", flush=True)
time.sleep(.4)
print("[3/4]", flush=True)
time.sleep(.4)
words = [{"word": "Eu", "start": 0.0, "end": .2},
         {"word": "vou", "start": .3, "end": .5},
         {"word": "cantar", "start": .6, "end": .9}]
(root / "fake.integrado.json").write_text(json.dumps({"language": "pt", "segments": [{"words": words}]}), encoding="utf-8")
(root / "fake.qualidade.json").write_text(json.dumps({"etapas": {"alinhamento": "ok"}, "backend_alinhamento": "onnx_directml_confirmado", "gpu_reconhecimento": "vulkan_confirmado_pelo_log", "total_alertas": 1}), encoding="utf-8")
''', encoding="utf-8")
    monkeypatch.setattr(k, "aligned_worker_resources", lambda: (Path(sys.executable), script))
    return audio, model, script


def test_external_json_is_normalized_and_gpu_evidence_preserved(worker):
    audio, model, _ = worker
    phases = []
    value = k.generate_timing(audio, whisper_cli=sys.executable, model=model,
                              ffmpeg=sys.executable, phase_changed=phases.append)
    assert [w["text"] for w in value["words"]] == ["Eu", "vou", "cantar"]
    assert value["words"][1]["start"] == .3
    assert value["language"] == "pt" and value["alignment_alerts"] == 1
    assert value["gpu_verified"] is True and value["alignment_backend"] == "onnx_directml_confirmado"
    assert "transcribe" in phases and "align" in phases and phases[-1] == "finalize"
    assert audio.read_bytes() == b"synthetic audio"


def test_alignment_without_gpu_evidence_is_rejected(worker):
    audio, model, script = worker
    text = script.read_text(encoding="utf-8").replace("vulkan_confirmado_pelo_log", "unverified")
    script.write_text(text, encoding="utf-8")
    with pytest.raises(k.KaraokeTimingError, match="not verified"):
        k.generate_timing(audio, whisper_cli=sys.executable, model=model, ffmpeg=sys.executable)


def test_cancellation_stops_worker_without_output(worker):
    audio, model, _ = worker
    with pytest.raises(k.KaraokeTimingError, match="cancelled"):
        k.generate_timing(audio, whisper_cli=sys.executable, model=model,
                          ffmpeg=sys.executable, cancelled=lambda: True)
    assert audio.read_bytes() == b"synthetic audio"


def test_missing_worker_resources_fail_without_download(tmp_path, monkeypatch):
    monkeypatch.setenv("N3LX_WHISPER_GPU_HOME", str(tmp_path))
    with pytest.raises(k.KaraokeTimingError, match="not configured"):
        k.aligned_worker_resources()
