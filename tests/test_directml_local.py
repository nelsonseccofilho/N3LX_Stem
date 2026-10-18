"""Local AMD integration: isolated environment and existing fallback policy."""

import sys
from pathlib import Path

import pytest

from app.core import amd_directml as dml
from app.core import config, settings
from app.pipeline import separate as separation


def test_directml_is_opt_in(monkeypatch):
    monkeypatch.delenv("STEMDECK_DIRECTML_PYTHON", raising=False)
    assert not dml.directml_available()


def test_probe_receives_the_configured_interpreter_and_adapter(monkeypatch):
    monkeypatch.setenv("STEMDECK_DIRECTML_PYTHON", sys.executable)
    monkeypatch.setenv("STEMDECK_DIRECTML_ADAPTER", "RX 6600M")
    seen = []
    monkeypatch.setattr(dml, "_probe", lambda *args: seen.append(args) or True)
    assert dml.directml_available()
    assert seen == [(sys.executable, "RX 6600M")]


def test_unavailable_directml_cannot_be_forced(monkeypatch):
    monkeypatch.setattr(settings, "available_torch_devices", lambda: ["cpu"])
    with pytest.raises(ValueError, match="not available"):
        settings.set_demucs_device("directml")


def test_worker_interpreters_are_isolated(monkeypatch):
    monkeypatch.setenv("STEMDECK_DIRECTML_PYTHON", "amd-python.exe")
    assert separation._spawn_worker_cmd("directml") == [
        "amd-python.exe",
        str(Path(dml.__file__).resolve()),
        "--worker",
    ]
    assert separation._spawn_worker_cmd("cpu")[0] == sys.executable


def test_device_probe_prioritizes_directml_over_cpu(monkeypatch):
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)
    monkeypatch.setattr(config, "directml_available", lambda: True)
    assert config.available_torch_devices() == ["directml", "cpu"]
