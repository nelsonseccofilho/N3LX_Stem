"""Current Windows workspace karaoke integration; no GPU or personal audio needed."""
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api import karaoke as api
from app.pipeline import karaoke_timing as timing


def test_current_workspace_transcriber_discovery(tmp_path, monkeypatch):
    shared = tmp_path / "_workspace"
    python = shared / "venvs" / "whispergpu" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"test")
    worker = tmp_path / "NELX-Whisper-GPU" / "src" / "transcrever_gpu.py"
    worker.parent.mkdir(parents=True)
    worker.write_text("# test worker", encoding="utf-8")
    monkeypatch.setenv("N3LX_SHARED_WORKSPACE", str(shared))
    monkeypatch.setenv("N3LX_WHISPER_GPU_HOME", str(worker.parent.parent))
    monkeypatch.setenv("N3LX_WHISPER_GPU_PYTHON", str(python))
    assert timing.aligned_worker_resources() == (python, worker)


def test_large_v3_only_and_language_readiness(tmp_path, monkeypatch):
    cli = tmp_path / "whisper-cli.exe"
    model = tmp_path / "ggml-large-v3.bin"
    cli.write_bytes(b"binary")
    model.write_bytes(b"model")
    monkeypatch.setenv("N3LX_WHISPER_CLI", str(cli))
    monkeypatch.setenv("N3LX_WHISPER_LARGE_MODEL", str(model))
    monkeypatch.setattr(api.shutil, "which", lambda _: str(cli))
    monkeypatch.setattr(api, "ffmpeg_executable", lambda: "ffmpeg")
    monkeypatch.setattr(api, "aligned_worker_resources", lambda: (cli, model))
    assert api._configuration("large-v3", "pt")[1] == model
    assert api._configuration("large-v3", "en")[1] == model
    with pytest.raises(HTTPException) as exc:
        api._configuration("medium", "pt")
    assert exc.value.status_code == 422
    monkeypatch.setattr(api, "_job", lambda _: (None, tmp_path))
    status = api.karaoke_status("abcdef123456")
    assert status["models"] == ["large-v3"]
    assert status["language_models"] == {"pt": ["large-v3"], "en": ["large-v3"]}


@pytest.mark.parametrize("exit_code,gpu_verified,success", [
    (0, True, True),
    (2, True, False),  # Current transcriber returns 2 for partial alignment.
    (0, False, False),
])
def test_current_worker_cli_contract_and_quality_gate(
    tmp_path, monkeypatch, exit_code, gpu_verified, success
):
    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"synthetic")
    model = tmp_path / "ggml-large-v3.bin"
    model.write_bytes(b"synthetic")
    worker = tmp_path / "NELX-Whisper-GPU" / "src" / "transcrever_gpu.py"
    worker.parent.mkdir(parents=True)
    worker.write_text("# fake", encoding="utf-8")
    commands = []

    class Process:
        returncode = exit_code

        def poll(self):
            return self.returncode

    def fake_popen(command, **kwargs):
        commands.append(command)
        output = Path(command[command.index("--output-dir") + 1])
        (output / "test.integrado.json").write_text(
            json.dumps({"language": "pt", "segments": [{"words": [
                {"word": "Eu", "start": 0.1, "end": 0.3},
                {"word": "vou", "start": 0.35, "end": 0.6},
                {"word": "cantar", "start": 0.7, "end": 1.2},
            ]}]}), encoding="utf-8",
        )
        (output / "test.qualidade.json").write_text(json.dumps({
            "etapas": {"alinhamento": "ok"},
            "backend_alinhamento": "cpu",
            "gpu_reconhecimento": (
                "vulkan_confirmado_pelo_log" if gpu_verified else "vulkan_nao_confirmado_pelo_log"
            ),
            "total_alertas": 0,
        }), encoding="utf-8")
        return Process()

    monkeypatch.setattr(timing, "aligned_worker_resources", lambda: (Path("python"), worker))
    monkeypatch.setattr(timing, "_checked_executable", lambda executable, *_: str(executable))
    monkeypatch.setattr(timing.subprocess, "Popen", fake_popen)
    if success:
        result = timing.generate_timing(audio, whisper_cli="whisper-cli", model=model)
        assert result["alignment_backend"] == "cpu"
        assert result["gpu_verified"] is True
        assert len(result["words"]) == 3
    else:
        with pytest.raises(timing.KaraokeTimingError):
            timing.generate_timing(audio, whisper_cli="whisper-cli", model=model)
    assert len(commands) == 1
    command = commands[0]
    assert "--no-diarize" in command
    assert "--output-format" in command
    assert "--no-preload-align" not in command
    assert "--output-profile" not in command
    assert "large-v3" in command


def test_frontend_has_no_medium_model_picker():
    html = Path("static/index.html").read_text(encoding="utf-8")
    assert '<input id="lyricsKaraokeModel" type="hidden" value="large-v3">' in html
    assert '<option value="medium"' not in html
