"""Sample-aligned overlap/add, independent of the application's ML runtime."""

from __future__ import annotations

import numpy as np


def windows(samples: int, rate: int, seconds=12.0, overlap=2.0):
    if samples <= 0 or rate <= 0 or not 0 <= overlap < seconds:
        raise ValueError("Invalid sample grid or overlap")
    size, step = round(seconds * rate), round((seconds - overlap) * rate)
    if size < 1 or step < 1:
        raise ValueError("Window and step must contain samples")
    result, start = [], 0
    while True:
        end = min(samples, start + size)
        result.append((start, end))
        if end == samples:
            return result
        start += step


def window_weight(length, fade, *, first=False, last=False):
    weight = np.ones(length, dtype=np.float32)
    fade = min(fade, length)
    if fade and not first:
        weight[:fade] *= np.linspace(0, 1, fade, endpoint=False, dtype=np.float32)
    if fade and not last:
        weight[-fade:] *= np.linspace(1, 0, fade, endpoint=False, dtype=np.float32)
    return weight


def add_window(accumulator, weights, value, start, fade, *, first, last):
    if value.ndim != 2 or value.shape[1] != accumulator.shape[1] or not np.isfinite(value).all():
        raise ValueError("Invalid separated audio window")
    end = start + len(value)
    if not 0 <= start < end <= len(accumulator):
        raise ValueError("Separated window is outside the source")
    weight = window_weight(len(value), fade, first=first, last=last)
    accumulator[start:end] += value * weight[:, None]
    weights[start:end] += weight


def finish_windows(accumulator, weights):
    if np.any(weights <= 0) or not np.isfinite(weights).all():
        raise ValueError("Separation left uncovered audio samples")
    return accumulator / weights[:, None]
