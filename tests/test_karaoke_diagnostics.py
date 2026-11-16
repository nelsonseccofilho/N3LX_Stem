"""C27.4D: simulated failure-only tests; never run ML models or user audio."""
import json
from pathlib import Path

import pytest

from app.pipeline.karaoke_diagnostics import classify_worker_failure, record_worker_failure


def test_structured_chain_keeps_origin_but_rejects_private_fields():
    from app.pipeline.karaoke_diagnostics import analyze_worker_failure
    payload = {"operation": "load_model", "private": "LYRIC SECRET", "versions": {
        "torch": "2.8.0+cpu", "transformers": "secret", "private": "2.0"},
        "chain": [{"exception_type": "ValueError", "reason": "model_load",
                   "origin": {"module": "whisperx.alignment", "line": 103},
                   "message": "LYRIC SECRET", "message_fingerprint": "a" * 16},
                  {"exception_type": "PRIVATE", "reason": "PRIVATE",
                   "origin": {"module": "C:/private/person", "line": 5}}]}
    result = analyze_worker_failure("N3LX_ALIGNMENT_DIAGNOSTIC=" + json.dumps(payload))
    evidence = result["alignment_evidence"]
    assert evidence["operation"] == "load_model"
    assert evidence["chain"][0]["origin"] == {"module": "whisperx.alignment", "line": 103}
    assert evidence["chain"][1]["origin"] is None
    assert evidence["versions"] == {"torch": "2.8.0+cpu"}
    assert "PRIVATE" not in json.dumps(result)
    assert "SECRET" not in json.dumps(result)


@pytest.mark.parametrize("payload", ["[]", "null", "garbled", '{"chain":null,"versions":[]}',
    '{"operation":[],"chain":[{"reason":[],"origin":{"module":[]}}]}'])
def test_malformed_structured_evidence_never_masks_failure(payload):
    from app.pipeline.karaoke_diagnostics import analyze_worker_failure
    assert isinstance(analyze_worker_failure("N3LX_ALIGNMENT_DIAGNOSTIC=" + payload), dict)


def test_classification_is_allowlisted_and_cannot_echo_transcript():
    sample = (
        "Recognized lyric: private chorus that must never reach logs\n"
        "Traceback (most recent call last):\n"
        "ModuleNotFoundError: No module named 'whisperx'\n"
    )
    category, exception_type = classify_worker_failure(sample)
    assert (category, exception_type) == (
        "missing_python_dependency", "ModuleNotFoundError"
    )


def test_failure_report_survives_temp_log_cleanup_and_contains_no_lyrics(
    monkeypatch, tmp_path: Path,
):
    logs = tmp_path / "logs"
    monkeypatch.setenv("STEMDECK_LOGS_DIR", str(logs))
    temp = tmp_path / "temporary"
    temp.mkdir()
    log = temp / "worker.log"
    marker = "PRIVATE_AUDIO_LYRIC_DO_NOT_PERSIST"
    log.write_text(
        f"[2/4] recognition\n{marker}\n"
        "Traceback (most recent call last):\n"
        "RuntimeError: test worker failure at hidden local path\n",
        encoding="utf-8",
    )
    audio = tmp_path / "jobs" / "2e2c72eee977" / "stems" / "vocals.wav"
    report_id = record_worker_failure(
        logfile=log, audio=audio, language="pt", phase="transcribe",
        exit_code=2, alignment_backend="cpu",
    )
    assert report_id is not None
    path = logs / "karaoke-diagnostics" / f"karaoke-failure-{report_id}.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["job_id"] == "2e2c72eee977"
    assert data["exit_code"] == 2
    assert data["exception_type"] == "RuntimeError"
    assert data["category_hint"] == "worker_failure_unclassified"
    assert data["requested_recognition_backend"] == "vulkan:0"
    assert data["requested_alignment_backend"] == "cpu"
    assert data["gpu_execution_verified"] is False
    log.unlink()
    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert marker not in content
    assert "hidden local path" not in content
    assert "whisperx" not in content


def test_report_retention_is_bounded(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("STEMDECK_LOGS_DIR", str(tmp_path / "logs"))
    log = tmp_path / "worker.log"
    log.write_text("PermissionError: [WinError 32]\n", encoding="utf-8")
    for _index in range(34):
        result = record_worker_failure(
            logfile=log, audio=tmp_path / "vocals.wav", language="en",
            phase="align", exit_code=2, alignment_backend="cpu",
        )
        assert result
    reports = list((tmp_path / "logs/karaoke-diagnostics").glob(
        "karaoke-failure-*.json"
    ))
    assert len(reports) == 32
    one = json.loads(reports[0].read_text(encoding="utf-8"))
    assert one["category_hint"] == "file_locked_or_permission_denied"


def test_worker_failure_preserves_original_error_even_when_report_cannot_write(
    monkeypatch, tmp_path: Path,
):
    from app.pipeline import karaoke_diagnostics as d
    monkeypatch.setattr(d, "_log_directory", lambda: tmp_path / "missing")
    monkeypatch.setattr(
        d.Path, "mkdir", lambda *_args, **_kwargs: (_ for _ in ()).throw(
            PermissionError("mock denied")
        ),
    )
    assert record_worker_failure(
        logfile=tmp_path / "worker.log", audio=tmp_path / "vocals.wav",
        language="pt", phase="prepare", exit_code=2, alignment_backend="cpu",
    ) is None


def test_generate_timing_nonzero_exit_emits_diagnostic_without_gpu(
    monkeypatch, tmp_path: Path,
):
    from app.pipeline import karaoke_timing as k
    monkeypatch.setenv("STEMDECK_LOGS_DIR", str(tmp_path / "logs"))
    audio = tmp_path / "vocals.wav"
    model = tmp_path / "ggml-large-v3.bin"
    audio.write_bytes(b"stub audio")
    model.write_bytes(b"stub model")

    class Finished:
        returncode = 2

        def poll(self):
            return self.returncode

    def fake_worker(_argv, **kwargs):
        kwargs["stdout"].write(
            "Traceback (most recent call last):\n"
            "ModuleNotFoundError: No module named 'missing package'\n"
            "PRIVATE_LYRIC_FROM_WORKER\n"
        )
        kwargs["stdout"].flush()
        return Finished()

    monkeypatch.setattr(k, "_checked_executable", lambda value, _label: value)
    monkeypatch.setattr(k, "aligned_worker_resources", lambda: (
        tmp_path / "python.exe", tmp_path / "src/transcrever_gpu.py",
    ))
    monkeypatch.setattr(k.subprocess, "Popen", fake_worker)
    monkeypatch.setattr(k, "portuguese_alignment_cache", lambda: tmp_path / "hf-cache")

    with pytest.raises(k.KaraokeTimingError, match="worker exited with code 2") as failure:
        k.generate_timing(
            audio, whisper_cli="whisper-cli", model=model, language="pt"
        )
    assert "diagnostic:" in str(failure.value)
    reports = list((tmp_path / "logs/karaoke-diagnostics").glob(
        "karaoke-failure-*.json"
    ))
    assert len(reports) == 1
    stored = reports[0].read_text(encoding="utf-8")
    assert "PRIVATE_LYRIC_FROM_WORKER" not in stored
    assert '"category_hint": "missing_python_dependency"' in stored
    assert audio.read_bytes() == b"stub audio"


def test_separate_vulkan_mention_does_not_falsely_blame_gpu():
    from app.pipeline.karaoke_diagnostics import analyze_worker_failure

    result = analyze_worker_failure(
        "[1/4] preparing audio\n"
        "whisper-cli using Vulkan0 backend\n"
        "[2/4] recognition\n"
        "[3/4] alignment\n"
        "RuntimeError: generic failure without backend evidence\n"
    )
    assert result["category_hint"] == "worker_failure_unclassified"
    assert result["exception_type"] == "RuntimeError"
    assert result["last_worker_stage_marker"] == "3/4"
    assert result["classification_basis"] == "insufficient_evidence"


def test_only_explicit_terminal_vulkan_error_is_flagged():
    from app.pipeline.karaoke_diagnostics import analyze_worker_failure

    result = analyze_worker_failure(
        "[2/4] recognition\n"
        "ERROR: Vulkan initialization failed\n"
    )
    assert result["category_hint"] == "vulkan_error"
    assert result["classification_basis"] == "explicit_log_line"


def test_worker_argument_error_is_identified_without_saving_raw_arguments():
    from app.pipeline.karaoke_diagnostics import analyze_worker_failure

    result = analyze_worker_failure(
        "usage: transcrever_gpu.py\n"
        "error: unrecognized arguments: --private-value user-secret\n"
    )
    assert result["category_hint"] == "worker_argument_error"
    assert "user-secret" not in str(result)


def test_allowlisted_missing_module_is_recorded_without_arbitrary_names(
    monkeypatch, tmp_path: Path,
):
    monkeypatch.setenv("STEMDECK_LOGS_DIR", str(tmp_path / "logs"))
    log = tmp_path / "worker.log"
    log.write_text(
        "[3/4] alignment\n"
        "Traceback (most recent call last):\n"
        "ModuleNotFoundError: No module named 'torchaudio'\n"
        "PRIVATE_TRANSCRIBED_TEXT\n",
        encoding="utf-8",
    )
    report_id = record_worker_failure(
        logfile=log, audio=tmp_path / "vocals.wav",
        language="pt", phase="align", exit_code=2, alignment_backend="cpu",
    )
    assert report_id is not None
    report = tmp_path / "logs/karaoke-diagnostics" / (
        f"karaoke-failure-{report_id}.json"
    )
    document = json.loads(report.read_text(encoding="utf-8"))
    assert document["missing_dependency"] == "torchaudio"
    assert document["last_worker_stage_marker"] == "3/4"
    assert document["classification_basis"] == "python_exception"
    assert "PRIVATE_TRANSCRIBED_TEXT" not in report.read_text(encoding="utf-8")

