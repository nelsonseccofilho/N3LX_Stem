"""Regression checks for float drum-detail publication.

A drum separator can emit finite peaks above unity. Rejecting these peaks
prevented an otherwise successful full-mode extraction from publishing any
individual drum stems. Float WAV must preserve the data without normalization.
"""

import numpy as np
import pytest
import soundfile as sf

from app.pipeline import complete_multitrack as multitrack


def test_drum_detail_preserves_finite_peaks_above_unity(tmp_path, monkeypatch):
    monkeypatch.setattr(multitrack, "check_cancel", lambda _job: None)
    samples = np.asarray([[0.2], [1.25], [-1.5], [0.0]], dtype=np.float32)
    source = tmp_path / "drum_kick.wav"
    reference = tmp_path / "drums.wav"
    destination = tmp_path / "drum_kick.aligned.wav"

    sf.write(source, samples, 44100, subtype="FLOAT")
    sf.write(reference, np.zeros_like(samples), 44100, subtype="FLOAT")
    multitrack._aligned_copy(object(), source, destination, sf.info(reference))

    assert sf.info(destination).subtype == "FLOAT"
    actual, rate = sf.read(destination, dtype="float64", always_2d=True)
    assert rate == 44100
    np.testing.assert_allclose(actual, samples, atol=1e-6)
    assert np.max(np.abs(actual)) > 1


def test_drum_detail_still_rejects_nonfinite_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(multitrack, "check_cancel", lambda _job: None)
    source = tmp_path / "drum_snare.wav"
    reference = tmp_path / "drums.wav"

    sf.write(
        source, np.asarray([[0.1], [np.nan]], dtype=np.float32), 48000, subtype="FLOAT"
    )
    sf.write(reference, np.zeros((2, 1), dtype=np.float32), 48000, subtype="FLOAT")

    with pytest.raises(ValueError, match="non-finite"):
        multitrack._aligned_copy(
            object(), source, tmp_path / "drum_snare.aligned.wav", sf.info(reference)
        )
