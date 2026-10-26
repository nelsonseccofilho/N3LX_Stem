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
    destination.symlink_to(target)
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

