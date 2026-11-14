"""Pure karaoke timing contract tests: no GPU or personal audio needed."""
import json
from pathlib import Path

import pytest

from app.pipeline.karaoke_timing import (
    KaraokeTimingError, enhanced_lrc, normalize_timing, store_timing,
)


def cpp(words):
    return {"language": "pt", "transcription": [
        {"offsets": {"from": int(a * 1000), "to": int(b * 1000)}, "text": t}
        for t, a, b in words
    ]}


def test_whisper_cpp_words_and_lrc():
    result = normalize_timing(cpp([
        (" Eu", 0.0, 0.2), (" volto", 0.25, 0.7), (" pra", 0.8, 1.0),
        (" casa", 1.1, 1.6), ("!", 1.6, 1.7),
    ]))
    assert result["engine"] == "whisper.cpp"
    assert [w["text"] for w in result["words"]] == ["Eu", "volto", "pra", "casa!"]
    assert result["timing_status"] == "machine_unverified"
    assert "[00:00.00]<00:00.00>Eu" in enhanced_lrc(result["words"])
    assert "<00:01.70>" in enhanced_lrc(result["words"])


def test_whisperx_word_level_import_contract():
    payload = {"segments": [{"words": [
        {"word": "Olá", "start": 2, "end": 2.2},
        {"word": "minha", "start": 2.3, "end": 2.7},
        {"word": "casa", "start": 2.7, "end": 3.3},
    ]}]}
    assert len(normalize_timing(payload)["words"]) == 3


@pytest.mark.parametrize("payload", [
    cpp([("fala sem tempos", 0, 1), ("x", 1, 2), ("y", 2, 3)]),
    cpp([("um", 3, 4), ("dois", 1, 2), ("tres", 4, 5)]),
    cpp([("um", 0, 1), ("dois", 1, 2)]),
    {"segments": [{"words": [{"word": "olá"}]}]},
    cpp([("<00:10.00>", 0, 1), ("abc", 1, 2), ("def", 2, 3)]),
])
def test_invalid_or_unreliable_timings_rejected(payload):
    with pytest.raises(KaraokeTimingError):
        normalize_timing(payload)


def test_persist_regenerate_preserves_original(tmp_path: Path):
    destination = tmp_path / "lyrics_timing.json"
    original = {"v": 1, "words": ["original"]}
    destination.write_text(json.dumps(original), encoding="utf-8")
    with pytest.raises(KaraokeTimingError):
        store_timing(destination, {"v": 1, "words": ["new"]})
    old = store_timing(destination, {"v": 1, "words": ["new"]}, replace=True)
    assert old and json.loads(old.read_text(encoding="utf-8")) == original
    assert json.loads(destination.read_text(encoding="utf-8"))["words"] == ["new"]
    assert len(list(tmp_path.glob("*.backup-*.json"))) == 1


def test_symlink_target_is_rejected(tmp_path: Path):
    destination = tmp_path / "destination.json"
    target = tmp_path / "other.json"
    target.write_text("original", encoding="utf-8")
    try:
        destination.symlink_to(target)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows account cannot create symbolic links")
        raise
    with pytest.raises(KaraokeTimingError):
        store_timing(destination, {"v": 1}, replace=True)
    assert target.read_text(encoding="utf-8") == "original"

def test_cancelled_worker_is_terminated(monkeypatch):
    from app.pipeline import karaoke_timing as k

    class Process:
        returncode = None
        stopped = False

        def poll(self):
            return self.returncode

        def terminate(self):
            self.stopped = True
            self.returncode = -15

        def wait(self, timeout=None):
            return self.returncode

    proc = Process()
    monkeypatch.setattr(k.subprocess, "Popen", lambda *args, **kwargs: proc)
    with pytest.raises(KaraokeTimingError, match="cancelled"):
        k._run_command(["dummy"], timeout=30, cancelled=lambda: True)
    assert proc.stopped

def test_real_whisper_cpp_full_json_tokens_use_word_offsets():
    """-ojf carries token times inside segments, not just segment times."""
    payload = {
        "result": {"language": "pt"},
        "transcription": [{
            "offsets": {"from": 0, "to": 1500},
            "text": " Eu vou encontrar.",
            "tokens": [
                {"text": "[_BEG]"},
                {"text": " Eu", "offsets": {"from": 100, "to": 300}},
                {"text": " vou", "offsets": {"from": 350, "to": 550}},
                {"text": " en", "offsets": {"from": 600, "to": 700}},
                {"text": "con", "offsets": {"from": 700, "to": 900}},
                {"text": "trar", "offsets": {"from": 900, "to": 1200}},
                {"text": ".", "offsets": {"from": 1200, "to": 1300}},
            ],
        }],
    }
    result = normalize_timing(payload)
    assert result["language"] == "pt"
    assert [word["text"] for word in result["words"]] == ["Eu", "vou", "encontrar."]
    assert [word["start"] for word in result["words"]] == [.1, .35, .6]
    assert [word["end"] for word in result["words"]] == [.3, .55, 1.3]


def test_full_json_without_word_offsets_is_rejected():
    payload = {"transcription": [{
        "text": "Eu vou cantar",
        "offsets": {"from": 0, "to": 2000},
        "tokens": [
            {"text": " Eu", "offsets": {"from": 0, "to": 300}},
            {"text": " vou"},
            {"text": " cantar", "offsets": {"from": 800, "to": 2000}},
        ],
    }]}
    with pytest.raises(KaraokeTimingError, match="lacks timestamps"):
        normalize_timing(payload)


@pytest.mark.parametrize("language", ["pt", "en"])
def test_both_languages_use_the_same_vulkan_whisperx_worker(
    monkeypatch, tmp_path: Path, language: str,
):
    """No GPU, network, model download or user recording required."""
    from app.pipeline import karaoke_timing as k

    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"test audio stub")
    model = tmp_path / "ggml-large-v3.bin"
    model.write_bytes(b"model stub")
    captured = []

    class Finished:
        returncode = 0

        def poll(self):
            return 0

    def worker_run(argv, **kwargs):
        captured.append(argv)
        assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
        assert kwargs["env"]["TRANSFORMERS_OFFLINE"] == "1"
        output = Path(argv[argv.index("--output-dir") + 1])
        output.joinpath("fixture.integrado.json").write_text(json.dumps({
            "language": language,
            "segments": [{"words": [
                {"word": "Hello", "start": 22.0, "end": 22.2},
                {"word": "from", "start": 22.3, "end": 22.5},
                {"word": "vocals", "start": 22.6, "end": 23.0},
            ]}],
        }), encoding="utf-8")
        output.joinpath("fixture.qualidade.json").write_text(json.dumps({
            "etapas": {"alinhamento": "ok"},
            "backend_alinhamento": "cpu",
            "gpu_reconhecimento": "vulkan_confirmado_pelo_log",
        }), encoding="utf-8")
        return Finished()

    monkeypatch.setattr(k, "_checked_executable", lambda value, label: value)
    monkeypatch.setattr(k, "aligned_worker_resources", lambda: (
        tmp_path / "python.exe", tmp_path / "src" / "transcrever_gpu.py"))
    monkeypatch.setattr(k, "english_alignment_ready", lambda: True)
    monkeypatch.setattr(k.subprocess, "Popen", worker_run)
    phases = []
    timing = k.generate_timing(
        audio, whisper_cli="whisper-cli", model=model,
        language=language, phase_changed=phases.append)
    assert captured
    args = captured[0]
    assert args[args.index("--language") + 1] == language
    assert args[args.index("--device") + 1] == "vulkan"
    assert "--no-diarize" in args
    assert "-ojf" not in args  # do not silently fall back to Whisper timestamps
    assert timing["language"] == language
    assert timing["engine"] == "whisperx"
    assert timing["alignment_backend"] == "cpu"
    assert timing["gpu_verified"] is True
    assert timing["words"][0]["start"] == 22.0
    assert "finalize" in phases


def test_english_requires_offline_acoustic_checkpoint(monkeypatch, tmp_path: Path):
    from app.pipeline import karaoke_timing as k

    monkeypatch.setenv("TORCH_HOME", str(tmp_path / "torch"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "other"))
    assert k.english_alignment_checkpoint() == (
        tmp_path / "torch/hub/checkpoints" / k.ENGLISH_ALIGN_CHECKPOINT)
    assert k.english_alignment_ready() is False
    location = k.english_alignment_checkpoint()
    location.parent.mkdir(parents=True)
    with location.open("wb") as output:
        output.truncate(20 * 1024 * 1024)  # sparse fixture, no model download
    assert k.english_alignment_ready() is True


def test_english_fails_before_worker_when_model_missing(monkeypatch, tmp_path: Path):
    from app.pipeline import karaoke_timing as k

    audio = tmp_path / "vocals.wav"
    audio.write_bytes(b"stub")
    model = tmp_path / "ggml-large-v3.bin"
    model.write_bytes(b"stub")
    monkeypatch.setattr(k, "_checked_executable", lambda v, _label: v)
    monkeypatch.setattr(k, "aligned_worker_resources", lambda: (
        tmp_path / "python.exe", tmp_path / "src/transcrever_gpu.py"))
    monkeypatch.setattr(k, "english_alignment_ready", lambda: False)
    with pytest.raises(k.KaraokeTimingError, match="checkpoint not available"):
        k.generate_timing(audio, whisper_cli="whisper-cli", model=model, language="en")
