"""Signal-level QA for stereo transfer; these do not test SAM separation quality."""

import numpy as np
import pytest
from scipy.signal import resample_poly

from scripts.sam_audio_stereo import restore_stereo


def mixture(rate=44100):
    times = np.arange(rate * 2) / rate
    low = 0.25 * np.sin(2 * np.pi * 220 * times)
    high = 0.15 * np.sin(2 * np.pi * 1760 * times)
    original = np.stack([low + high, 0.5 * low + 1.3 * high], axis=1).astype(np.float32)
    return times, original, 0.75 * low, 1.15 * high


def test_transfer_selects_known_component_and_preserves_stereo_pan():
    times, original, low, high = mixture()
    selected, remainder, report = restore_stereo(original, 44100, low, high, estimate_rate=44100)
    interior = slice(4410, -4410)
    reference = np.sin(2 * np.pi * 220 * times[interior])
    rejected = np.sin(2 * np.pi * 1760 * times[interior])
    amplitudes = 2 * selected[interior].T @ reference / len(reference)
    leakage = 2 * selected[interior].T @ rejected / len(reference)
    assert amplitudes[1] / amplitudes[0] == pytest.approx(0.5, abs=0.002)
    assert np.max(np.abs(leakage)) < np.min(amplitudes) / 100
    np.testing.assert_allclose(selected + remainder, original, atol=6e-8)
    assert report["mask_min"] >= 0 and report["mask_max"] <= 1


def test_transfer_preserves_opposite_phase_channels():
    _, original, low, high = mixture()
    original[:, 1] = -original[:, 0]
    selected, remainder, _ = restore_stereo(original, 44100, low, high, estimate_rate=44100)
    np.testing.assert_array_equal(selected[:, 0], -selected[:, 1])
    np.testing.assert_array_equal(remainder[:, 0], -remainder[:, 1])


def test_zero_estimates_keep_all_original_audio_in_remainder():
    _, original, low, _ = mixture()
    selected, remainder, _ = restore_stereo(original, 44100, low * 0, low * 0, estimate_rate=44100)
    np.testing.assert_array_equal(selected, 0)
    np.testing.assert_array_equal(remainder, original)


def test_resampling_estimates_does_not_change_source_length_rate_or_silent_channel():
    _, original, low, high = mixture()
    original[:, 1] = 0
    selected, remainder, report = restore_stereo(
        original, 44100, resample_poly(low, 160, 147), resample_poly(high, 160, 147)
    )
    assert selected.shape == original.shape
    assert report["sample_rate"] == 44100
    np.testing.assert_array_equal(selected[:, 1], 0)
    np.testing.assert_allclose(selected + remainder, original, atol=6e-8)


@pytest.mark.parametrize("component", ["original", "target", "residual"])
def test_nonfinite_audio_is_rejected(component):
    _, original, low, high = mixture()
    data = {"original": original, "target": low, "residual": high}
    data[component].flat[0] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        restore_stereo(**data, sample_rate=44100, estimate_rate=44100)


def test_misaligned_estimate_is_rejected_instead_of_silently_padding():
    _, original, low, high = mixture()
    with pytest.raises(ValueError, match="same time interval"):
        restore_stereo(original, 44100, low[:-100], high, estimate_rate=44100)
