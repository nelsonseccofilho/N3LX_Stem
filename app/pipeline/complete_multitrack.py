"""Automatic detailed stems, preserving base groups on an optional-pass failure."""

from __future__ import annotations

import json
import logging
import shutil
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

import numpy as np
import soundfile as sf

from app.core.config import STEM_NAMES, TIMEOUT_FFMPEG, ffmpeg_executable
from app.core.models import Job, JobCancelled, _set
from app.core.processing_progress import begin_step, clear_fraction, warn_step
from app.core.studio import DETAIL_LABELS, DRUM_STEMS
from app.core.worker_progress import run_progress_worker
from app.pipeline.cancel import check_cancel, run_registered
from app.pipeline.vocal_split import split_vocals

logger = logging.getLogger("stemdeck.pipeline")
VOICE_STEMS = ("lead_vocals", "backing_vocals")
RESIDUES = ("residual_mix", "residual_drums", "residual_vocals")
BLOCK = 262144


def _warn(job: Job, text: str, error: Exception) -> None:
    warn_step(job)
    logger.warning("[%s] %s: %s", job.id, text, error, exc_info=True)
    _set(job, separation_warnings=[*job.separation_warnings, text])


def _aligned_copy(job: Job, source: Path, target: Path, info: sf._SoundFileInfo) -> None:
    with (
        sf.SoundFile(source) as reader,
        sf.SoundFile(
            target,
            "w",
            samplerate=info.samplerate,
            channels=info.channels,
            format="WAV",
            subtype="PCM_24",
        ) as writer,
    ):
        if (reader.samplerate, reader.channels) != (info.samplerate, info.channels):
            raise ValueError("Detailed stem has incompatible sample rate/channels")
        for start in range(0, info.frames, BLOCK):
            check_cancel(job)
            data = reader.read(
                min(BLOCK, info.frames - start), dtype="float64", always_2d=True, fill_value=0
            )
            if not np.isfinite(data).all():
                raise ValueError("Detailed stem contains non-finite samples")
            if np.max(np.abs(data), initial=0) >= 1:
                raise ValueError("Detailed stem would clip in PCM24")
            writer.write(data)


def _residual(job: Job, reference: Path, components: list[Path], target: Path, frames: int) -> None:
    temp = target.with_suffix(".part.wav")
    with ExitStack() as stack:
        original = stack.enter_context(sf.SoundFile(reference))
        readers = [stack.enter_context(sf.SoundFile(p)) for p in components]
        if any(
            (r.samplerate, r.channels) != (original.samplerate, original.channels) for r in readers
        ):
            raise ValueError("Residual inputs have incompatible sample rate/channels")
        # Float preserves large residues without silently clipping their peaks.
        writer = stack.enter_context(
            sf.SoundFile(
                temp,
                "w",
                samplerate=original.samplerate,
                channels=original.channels,
                format="WAV",
                subtype="FLOAT",
            )
        )
        for start in range(0, frames, BLOCK):
            check_cancel(job)
            n = min(BLOCK, frames - start)
            data = original.read(n, dtype="float64", always_2d=True, fill_value=0)
            for reader in readers:
                data -= reader.read(n, dtype="float64", always_2d=True, fill_value=0)
            if not np.isfinite(data).all():
                raise ValueError("Residual contains non-finite samples")
            writer.write(data)
    temp.replace(target)


def _publish_group(
    job: Job, scratch: Path, names: tuple[str, ...], parent: str, residual: str, stems: Path
) -> None:
    info = sf.info(stems / (parent + ".wav"))
    for name in names:
        _aligned_copy(job, scratch / (name + ".wav"), scratch / (name + ".aligned.wav"), info)
    _residual(
        job,
        stems / (parent + ".wav"),
        [scratch / (n + ".aligned.wav") for n in names],
        scratch / (residual + ".wav"),
        info.frames,
    )
    for name in names:
        (scratch / (name + ".aligned.wav")).replace(stems / (name + ".wav"))
    (scratch / (residual + ".wav")).replace(stems / (residual + ".wav"))


def _split_drums(job: Job, stems: Path, scratch: Path) -> None:
    check_cancel(job)
    timeout = max(1800, int((job.duration_sec or 0) * 12) + 600)
    result = run_progress_worker(
        job,
        [
            sys.executable,
            "-m",
            "app.pipeline.drum_split_worker",
            str(stems / "drums.wav"),
            str(scratch),
        ],
        timeout,
    )
    check_cancel(job)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[-3000:])


def active_names(stems: Path) -> list[str]:
    def exists(n: str) -> bool:
        return (stems / (n + ".wav")).is_file()

    voice = (
        VOICE_STEMS if all(exists(n) for n in (*VOICE_STEMS, "residual_vocals")) else ("vocals",)
    )
    drums = DRUM_STEMS if all(exists(n) for n in (*DRUM_STEMS, "residual_drums")) else ("drums",)
    return [n for n in ("bass", "guitar", "piano", "other", *drums, *voice, *RESIDUES) if exists(n)]


def _manifest(job: Job, stems: Path) -> None:
    labels = {
        **DETAIL_LABELS,
        "bass": "Baixo",
        "guitar": "Guitarras agrupadas",
        "piano": "Piano estimado",
        "other": "Outros instrumentos",
        "lead_vocals": "Voz principal",
        "backing_vocals": "Backing vocals",
    }
    names = active_names(stems)
    notice = (
        f"Completo · {len(names)} pistas. Guitarras permanecem agrupadas."
    )
    if job.separation_warnings:
        notice += " Atenção: " + " ".join(job.separation_warnings)
    value = {
        "profile": "complete",
        "labels": labels,
        "active_names": names,
        "notice": notice,
        "percussion_names": list(DRUM_STEMS),
        "warnings": job.separation_warnings,
    }
    target = stems.parent / "studio.json"
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(target)


def complete_multitrack(job: Job, source: Path, stems: Path) -> None:
    check_cancel(job)
    _set(job, separation_warnings=[])
    with tempfile.TemporaryDirectory(prefix=".complete-", dir=stems.parent) as temporary:
        scratch = Path(temporary)
        voice_dir = scratch / "voice"
        voice_dir.mkdir()
        drum_dir = scratch / "drums"
        drum_dir.mkdir()
        started = time.monotonic()
        begin_step(job, "vocals")
        _set(job, stage="Separating lead and backing vocals...", vocal_split="running")
        try:
            shutil.copy2(stems / "vocals.wav", voice_dir / "vocals.wav")
            check_cancel(job)
            split_vocals(job, voice_dir)
            check_cancel(job)
            clear_fraction(job)
            _publish_group(job, voice_dir, VOICE_STEMS, "vocals", "residual_vocals", stems)
            _set(job, vocal_split="done")
        except JobCancelled:
            raise
        except Exception as error:
            check_cancel(job)
            _set(job, vocal_split="error")
            _warn(job, "Divisão vocal indisponível; voz agrupada preservada.", error)
        job.stage_timings = {
            **(job.stage_timings or {}),
            "vocal_split_auto": time.monotonic() - started,
        }
        started = time.monotonic()
        begin_step(job, "drums")
        _set(job, stage="Separating six drum pieces (CPU)...")
        try:
            _split_drums(job, stems, drum_dir)
            clear_fraction(job)
            _publish_group(job, drum_dir, DRUM_STEMS, "drums", "residual_drums", stems)
        except JobCancelled:
            raise
        except Exception as error:
            check_cancel(job)
            _warn(job, "Divisão da bateria indisponível; bateria agrupada preservada.", error)
        job.stage_timings = {
            **(job.stage_timings or {}),
            "drum_split_cpu": time.monotonic() - started,
        }
        begin_step(job, "reconstruct")
        _set(job, stage="Preserving reconstruction residues...")
        try:
            info = sf.info(stems / "drums.wav")
            if any(
                (
                    sf.info(stems / (n + ".wav")).samplerate,
                    sf.info(stems / (n + ".wav")).channels,
                    sf.info(stems / (n + ".wav")).frames,
                )
                != (info.samplerate, info.channels, info.frames)
                for n in STEM_NAMES
            ):
                raise ValueError("Base stems have incompatible sample grids")
            # Link sources can be webm/m4a/opus. Decode before source cleanup.
            decoded = scratch / "reference.wav"
            result = run_registered(
                job,
                [
                    ffmpeg_executable(),
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-ar",
                    str(info.samplerate),
                    "-ac",
                    str(info.channels),
                    "-c:a",
                    "pcm_f32le",
                    str(decoded),
                ],
                TIMEOUT_FFMPEG,
            )
            check_cancel(job)
            if result.returncode:
                raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[-2000:])
            _residual(
                job,
                decoded,
                [stems / (n + ".wav") for n in STEM_NAMES],
                stems / "residual_mix.wav",
                info.frames,
            )
        except JobCancelled:
            raise
        except Exception as error:
            check_cancel(job)
            _warn(
                job, "Referência de reconstrução indisponível; grupos musicais preservados.", error
            )
    _manifest(job, stems)
