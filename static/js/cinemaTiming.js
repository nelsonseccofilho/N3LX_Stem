export const CINEMA_LONG_GAP = 6;
export const CINEMA_PREVIEW = 2;

// Pure clock-derived presentation. Never change the source timings.
export function cinemaTiming(lines, time) {
  let previousLine = null, activeLine = null, nextLine = null;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.text?.trim()) continue;
    const end = Number.isFinite(line.end) ? line.end : (lines[i + 1]?.time ?? Infinity);
    if (line.time > time) { nextLine = i; break; }
    if (time < end) activeLine = i;
    else previousLine = i;
  }
  let state, displayLine = activeLine;
  if (activeLine !== null) state = 'singing';
  else if (nextLine === null) state = 'ended';
  else if (lines[nextLine].time - time <= CINEMA_PREVIEW) {
    state = 'preview'; displayLine = nextLine;
  } else {
    const end = previousLine === null ? 0 : (lines[previousLine].end ?? lines[previousLine + 1]?.time ?? time);
    if (previousLine !== null && lines[nextLine].time - end < CINEMA_LONG_GAP) {
      state = 'short-gap'; displayLine = previousLine;
    } else state = 'instrumental';
  }
  return {previousLine, activeLine, nextLine, displayLine, state};
}
