"""Portable XDG must not hide an already installed offline acoustic model."""
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.pipeline import karaoke_timing as k


@pytest.fixture
def caches(monkeypatch):
    for key in ("TRANSFORMERS_CACHE", "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "HF_HOME"):
        monkeypatch.delenv(key, raising=False)
    # Keep synthetic HF snapshot paths below Windows 10's MAX_PATH limit.
    with TemporaryDirectory(prefix="kc-") as directory:
        root = Path(directory)
        monkeypatch.setattr(Path, "home", lambda: root / "p")
        monkeypatch.setenv("XDG_CACHE_HOME", str(root / "x"))
        yield root / "p/.cache/huggingface/hub", root / "x/huggingface/hub"


def seed(cache):
    repo = cache / "models--jonatasgrosman--wav2vec2-large-xlsr-53-portuguese"
    (repo / "refs").mkdir(parents=True)
    (repo / "refs/main").write_text("a" * 40)
    snapshot = repo / "snapshots" / ("a" * 40)
    snapshot.mkdir(parents=True)
    for name in ("config.json", "preprocessor_config.json", "vocab.json"):
        (snapshot / name).write_text("{}")
    with (snapshot / "pytorch_model.bin").open("wb") as handle:
        handle.truncate(20 * 1024 * 1024)
    return snapshot


def test_portable_cache_falls_back_to_complete_profile_model(caches):
    profile, _ = caches
    seed(profile)
    assert k.portuguese_alignment_cache() == profile


def test_complete_effective_cache_takes_precedence(caches):
    profile, portable = caches
    seed(profile)
    seed(portable)
    assert k.portuguese_alignment_cache() == portable


@pytest.mark.parametrize("key", ["TRANSFORMERS_CACHE", "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "HF_HOME"])
def test_explicit_missing_cache_never_uses_another_model(caches, monkeypatch, tmp_path, key):
    profile, _ = caches
    seed(profile)
    monkeypatch.setenv(key, str(tmp_path / "explicit"))
    assert k.portuguese_alignment_cache() is None


def test_missing_processor_is_not_advertised_as_available(caches):
    profile, _ = caches
    snapshot = seed(profile)
    (snapshot / "preprocessor_config.json").unlink()
    assert k.portuguese_alignment_cache() is None


def test_missing_pt_model_rejects_before_recognition(caches, tmp_path, monkeypatch):
    audio, model = tmp_path / "vocals.wav", tmp_path / "ggml-large-v3.bin"
    audio.write_bytes(b"audio must remain untouched")
    model.write_bytes(b"stub")
    monkeypatch.setattr(k, "_checked_executable", lambda value, _: value)
    monkeypatch.setattr(k, "aligned_worker_resources", lambda: (tmp_path / "python", tmp_path / "src/worker.py"))
    monkeypatch.setattr(k.subprocess, "Popen", lambda *a, **kw: pytest.fail("must not start recognition"))
    with pytest.raises(k.KaraokeTimingError, match="PT alignment model unavailable"):
        k.generate_timing(audio, whisper_cli="whisper", model=model)
    assert audio.read_bytes() == b"audio must remain untouched"
