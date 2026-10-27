// Stereo placement is playback-only: never rewrite or duplicate source WAVs.
// StereoPannerNode preserves the original stereo channels at pan=0.
export function clampStereoPan(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.max(-1, Math.min(1, value))
    : 0;
}

export function panLabel(value) {
  const v = Math.round(clampStereoPan(value) * 100);
  return v === 0 ? "C" : v < 0 ? "L" + Math.abs(v) : "R" + v;
}
