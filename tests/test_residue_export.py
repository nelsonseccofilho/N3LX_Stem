"""No signal duplication in the three-residue export."""

from zipfile import ZipFile

import numpy as np
import pytest
import soundfile as sf

from app.pipeline.residue_export import residue_groups, write_residue_archive


def test_refined_drums_replace_legacy_residue_without_double_counting():
    names = {
        "residual_vocals",
        "residual_mix",
        "residual_guitar",
        "residual_drums",
        "drum_recovery",
        "residual_drums_refined",
    }
    groups = residue_groups(names)
    assert groups == {
        "residuos_vozes": ("residual_vocals",),
        "residuos_musica": ("residual_mix", "residual_guitar"),
        "residuos_bateria": ("drum_recovery", "residual_drums_refined"),
    }
    assert "residual_drums" not in groups["residuos_bateria"]


def test_incomplete_refinement_uses_original_drum_residue():
    groups = residue_groups({"residual_drums", "drum_recovery", "residual_mix"})
    assert groups["residuos_bateria"] == ("residual_drums",)
    assert groups["residuos_vozes"] == ()


def test_archive_has_exactly_three_aligned_float_wavs(tmp_path):
    stems = tmp_path / "stems"
    stems.mkdir()
    sample_rate = 44100
    reference = np.zeros((5, 2), dtype=np.float32)
    sample_a = np.asarray([[0.5, 0.5]] * 5, dtype=np.float32)
    sample_b = np.asarray([[0.75, 0.75]] * 5, dtype=np.float32)
    drum_a = np.asarray([[0.1, 0.1]] * 5, dtype=np.float32)
    drum_b = np.asarray([[0.2, 0.2]] * 5, dtype=np.float32)
    sf.write(stems / "drums.wav", reference, sample_rate, subtype="FLOAT")
    for name, samples in {
        "residual_mix": sample_a,
        "residual_guitar": sample_b,
        "residual_drums": np.asarray([[0.9, 0.9]] * 5, dtype=np.float32),
        "drum_recovery": drum_a,
        "residual_drums_refined": drum_b,
    }.items():
        sf.write(stems / f"{name}.wav", samples, sample_rate, subtype="FLOAT")

    archive = tmp_path / "export.zip"
    originals = {p.name: p.read_bytes() for p in stems.iterdir()}
    write_residue_archive(stems, archive, set(originals) | {
        "residual_mix", "residual_guitar", "residual_drums",
        "drum_recovery", "residual_drums_refined",
    }, "faixa")

    with ZipFile(archive) as zf:
        assert zf.namelist() == [
            "faixa_residuos_vozes.wav",
            "faixa_residuos_musica.wav",
            "faixa_residuos_bateria.wav",
        ]
        import io

        expected = [np.zeros_like(reference), sample_a + sample_b, drum_a + drum_b]
        for filename, values in zip(zf.namelist(), expected, strict=True):
            with sf.SoundFile(io.BytesIO(zf.read(filename))) as stream:
                assert stream.subtype == "FLOAT"
                assert stream.samplerate == sample_rate
                assert stream.channels == 2
                assert stream.frames == len(reference)
                np.testing.assert_allclose(stream.read(always_2d=True), values, atol=1e-6)
        assert np.max(expected[1]) > 1.0  # do not clip musical residue

    assert {p.name: p.read_bytes() for p in stems.iterdir()} == originals


def test_export_rejects_mismatched_sample_grids(tmp_path):
    stems = tmp_path / "stems"
    stems.mkdir()
    sf.write(stems / "drums.wav", np.zeros((8, 1)), 44100)
    sf.write(stems / "residual_mix.wav", np.zeros((7, 1)), 44100)
    with pytest.raises(ValueError, match="incompatible audio grids"):
        write_residue_archive(
            stems, tmp_path / "bad.zip", {"residual_mix"}, "song"
        )
