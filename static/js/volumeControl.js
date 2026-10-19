// Keyboard nudges use decibels so precision stays consistent along the fader.
export function nudgeVolumeGain(gain, direction, coarse = false, maxGain = 2) {
  if (gain <= 0) return direction > 0 ? 0.001 : 0;
  const db = Math.round(20 * Math.log10(gain) * 10) / 10;
  const next = Math.round((db + direction * (coarse ? 1 : 0.1)) * 10) / 10;
  return next < -60 ? 0 : Math.min(maxGain, 10 ** (next / 20));
}
