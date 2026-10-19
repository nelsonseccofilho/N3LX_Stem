const validId = value => typeof value === "string" && /^[a-zA-Z0-9_-]{1,80}$/.test(value);
export function copyMix(mix) {
  return Object.fromEntries(Object.entries(mix || {}).filter(([name]) => validId(name)).map(([name, value]) => [name, {
    volume: Number.isFinite(value?.volume) ? Math.max(0, Math.min(2, value.volume)) : 1,
    muted: value?.muted === true, soloed: value?.soloed === true,
    pitch: Number.isFinite(value?.pitch) ? Math.max(-6, Math.min(6, Math.round(value.pitch))) : 0,
  }]));
}
export function newPlaylist(id, name, source = null) {
  return { id, name, entries: (Array.isArray(source?.entries) ? source.entries : []).filter(entry => validId(entry?.id)).map(entry => ({ id: entry.id, mix: copyMix(entry.mix) })),
    metro: { enabled: false, countInBars: 0, ...(structuredClone(source?.metro || {})) } };
}
export function normalizeSetlists(saved, makeId) {
  const seen = new Set();
  const playlists = (Array.isArray(saved?.playlists) ? saved.playlists : []).filter(p => validId(p?.id) && !seen.has(p.id) && seen.add(p.id)).map(p => {
    const ids = new Set();
    return { ...newPlaylist(p.id, String(p.name || "Playlist").slice(0, 80), p),
      entries: (Array.isArray(p.entries) ? p.entries : []).filter(e => validId(e?.id) && !ids.has(e.id) && ids.add(e.id)).map(e => ({ id: e.id, mix: copyMix(e.mix) })) };
  });
  if (!playlists.length) playlists.push(newPlaylist(makeId(), "Playlist 1"));
  return { version: 1, selectedId: playlists.some(p => p.id === saved?.selectedId) ? saved.selectedId : playlists[0].id, playlists };
}
export function applyMixToPlaylist(playlist, mix) {
  for (const entry of playlist.entries) entry.mix = copyMix(mix);
}
