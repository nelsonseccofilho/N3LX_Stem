
"""Selective drum-residual recovery with bounded-memory FFT windows."""

from pathlib import Path
import os

import numpy as np
import soundfile as sf


def recover(
    source,
    recovery_target,
    remaining_target,
    *,
    block_seconds=4.0,
    context_seconds=0.5,
    check_cancel=None,
):
    source = Path(source)
    recovery_target = Path(recovery_target)
    remaining_target = Path(remaining_target)

    locations = [
        source.resolve(),
        recovery_target.resolve(),
        remaining_target.resolve(),
    ]

    if len(set(locations)) != 3:
        raise ValueError("Source and outputs must be distinct")

    if recovery_target.exists() or remaining_target.exists():
        raise FileExistsError("Recovery output already exists")

    info = sf.info(str(source))
    rate = info.samplerate
    frames = info.frames
    channels = info.channels

    if rate <= 0 or frames <= 0 or channels <= 0:
        raise ValueError("Invalid audio stream")

    block = max(1, round(block_seconds * rate))
    padding = max(1, round(context_seconds * rate))

    recovery_tmp = recovery_target.with_name(
        recovery_target.stem + ".partial.wav"
    )
    remaining_tmp = remaining_target.with_name(
        remaining_target.stem + ".partial.wav"
    )

    if recovery_tmp.exists() or remaining_tmp.exists():
        raise FileExistsError("Temporary output already exists")

    try:
        with (
            sf.SoundFile(str(source)) as reader,
            sf.SoundFile(str(source)) as window_reader,
            sf.SoundFile(
                str(recovery_tmp),
                "w",
                samplerate=rate,
                channels=channels,
                format="WAV",
                subtype="FLOAT",
            ) as recovery_writer,
            sf.SoundFile(
                str(remaining_tmp),
                "w",
                samplerate=rate,
                channels=channels,
                format="WAV",
                subtype="FLOAT",
            ) as remaining_writer,
        ):
            for start in range(0, frames, block):
                if check_cancel is not None:
                    check_cancel()

                end = min(frames, start + block)
                count = end - start

                left = max(0, start - padding)
                right = min(frames, end + padding)

                window_reader.seek(left)
                window = window_reader.read(
                    right - left,
                    dtype="float64",
                    always_2d=True,
                )

                missing_left = padding - (start - left)
                missing_right = padding - (right - end)

                if missing_left or missing_right:
                    window = np.pad(
                        window,
                        ((missing_left, missing_right), (0, 0)),
                        mode="reflect",
                    )

                if len(window) != count + 2 * padding:
                    raise RuntimeError("Invalid FFT window alignment")

                if not np.isfinite(window).all():
                    raise ValueError("Non-finite audio input")

                frequencies = np.fft.rfftfreq(
                    len(window), d=1.0 / rate
                )

                position = np.clip(
                    (frequencies - 3000.0) / 2000.0,
                    0.0,
                    1.0,
                )

                mask = 0.5 - 0.5 * np.cos(
                    np.pi * position
                )

                filtered = np.fft.irfft(
                    np.fft.rfft(window, axis=0) * mask[:, None],
                    n=len(window),
                    axis=0,
                )

                selected = filtered[
                    padding:padding + count
                ]

                reader.seek(start)
                original = reader.read(
                    count,
                    dtype="float64",
                    always_2d=True,
                )

                remaining = original - selected

                if (
                    not np.isfinite(selected).all()
                    or not np.isfinite(remaining).all()
                ):
                    raise ValueError("Non-finite recovery result")

                recovery_writer.write(selected)
                remaining_writer.write(remaining)

        os.replace(recovery_tmp, recovery_target)
        os.replace(remaining_tmp, remaining_target)

    finally:
        recovery_tmp.unlink(missing_ok=True)
        remaining_tmp.unlink(missing_ok=True)

    return {
        "sample_rate": rate,
        "channels": channels,
        "frames": frames,
        "block_seconds": block_seconds,
        "context_seconds": context_seconds,
        "filter_lower_hz": 3000,
        "filter_upper_hz": 5000,
    }
