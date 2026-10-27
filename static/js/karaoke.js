import { getCurrentTrackInfo, setCatalogView } from "./catalog.js";
import { setLyricsPresentation } from "./lyrics.js";
import { transport, setPlayheadTime } from "./transport.js";
import { t, onLanguageChange } from "./i18n.js";

// A single visual envelope across the entire recording, derived from every
// stem's peaks. This is an overview, not a second audio player or mix render.
export function overviewPeaks(peaks, count = 800) {
  const sources = Object.values(peaks || {}).filter((p) => Array.isArray(p) && p.length);
  if (!sources.length) return [];
  return Array.from({ length: count }, (_, i) => {
    let energy = 0;
    for (const source of sources) {
      let peak = 0;
      const start = Math.floor(i * source.length / count);
      const end = Math.max(start + 1, Math.ceil((i + 1) * source.length / count));
      for (let j = start; j < end; j++) {
        const pair = source[j];
        if (Array.isArray(pair)) peak = Math.max(peak, ...pair.map((v) => Math.abs(Number(v) || 0)));
      }
      energy += peak * peak;
    }
    return Math.sqrt(energy / sources.length);
  });
}

export function initKaraoke() {
  const app = document.querySelector(".app"), stage = document.getElementById("karaokeStage");
  const panel = document.getElementById("lyricsPanel"), host = document.getElementById("karaokeLyricsHost");
  const waveTab = document.getElementById("studioWaveformsTab"), singTab = document.getElementById("studioKaraokeTab");
  const canvas = document.getElementById("karaokeWave"), clock = document.getElementById("karaokeClock");
  if (!app || !stage || !panel || !host || !canvas) return;
  const home = panel.parentElement;
  let active = false, trackId = null, duration = 0, peaks = [], frame = 0, request = 0;
  let controller = null, waveState = "", sidebarView = "library", lastSecond = -1;
  const fmt = (s) => `${Math.floor(Math.max(0, s) / 60)}:${String(Math.floor(Math.max(0, s) % 60)).padStart(2, "0")}`;
  const message = () => { document.getElementById("karaokeWaveStatus").textContent = waveState ? t(waveState) : ""; };
  const draw = (time) => {
    const box = canvas.getBoundingClientRect(), scale = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.round(box.width * scale)), height = Math.max(1, Math.round(box.height * scale));
    if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, width, height);
    const accent = getComputedStyle(app).getPropertyValue("--accent").trim() || "#f4b740";
    const progress = duration ? Math.min(1, time / duration) : 0;
    const max = Math.max(.01, ...peaks);
    const bars = Math.min(peaks.length, Math.floor(width / (3 * scale)));
    for (let i = 0; i < bars; i++) {
      const h = Math.max(2 * scale, peaks[Math.floor(i * peaks.length / bars)] / max * height * .85);
      ctx.fillStyle = i / bars <= progress ? accent : (getComputedStyle(app).getPropertyValue("--wave-unplayed").trim() || "#5f798b");
      ctx.fillRect(i * width / bars, (height - h) / 2, Math.max(scale, width / bars - scale), h);
    }
    ctx.fillStyle = accent;
    ctx.fillRect(progress * (width - 2 * scale), 0, 2 * scale, height);
  };
  async function load(info) {
    const token = ++request;
    controller?.abort(); controller = new AbortController();
    trackId = info?.id ?? null; duration = info?.duration || 0; peaks = []; lastSecond = -1;
    canvas.setAttribute("aria-valuemax", String(duration));
    canvas.setAttribute("aria-disabled", String(!duration));
    waveState = info ? "karaoke.loadingWave" : "lyrics.noTrack"; message();
    if (!info) return;
    try {
      const res = await fetch(`/api/jobs/${encodeURIComponent(info.id)}/peaks`, { signal: controller.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (token !== request) return;
      peaks = overviewPeaks(data);
      waveState = peaks.length ? "" : "karaoke.noWave"; message();
    } catch (err) {
      if (token !== request || err.name === "AbortError") return;
      waveState = "karaoke.noWave"; message();
    }
  }
  function tick() {
    frame = 0;
    if (!active) return;
    const info = getCurrentTrackInfo();
    if ((info?.id ?? null) !== trackId) load(info);
    const time = transport()?.getCurrentTime?.() || 0;
    draw(time);
    if (Math.floor(time) !== lastSecond) {
      lastSecond = Math.floor(time);
      clock.textContent = `${fmt(time)} / ${fmt(duration)}`;
      canvas.setAttribute("aria-valuenow", String(Math.min(duration, time)));
      canvas.setAttribute("aria-valuetext", `${fmt(time)} / ${fmt(duration)}`);
    }
    frame = requestAnimationFrame(tick);
  }
  function select(on) {
    if (on && app.classList.contains("is-processing-track")) return;
    active = on;
    stage.hidden = !on;
    document.getElementById("lanes").hidden = on;
    app.classList.toggle("karaoke-mode", on);
    waveTab.setAttribute("aria-selected", String(!on)); singTab.setAttribute("aria-selected", String(on));
    waveTab.tabIndex = on ? -1 : 0; singTab.tabIndex = on ? 0 : -1;
    (on ? host : home).append(panel);
    setLyricsPresentation(on);
    if (on) { load(getCurrentTrackInfo()); if (!frame) frame = requestAnimationFrame(tick); }
    else {
      controller?.abort(); ++request; cancelAnimationFrame(frame); frame = 0; trackId = null;
      if (sidebarView === "lyrics") setCatalogView("library");
    }
    window.dispatchEvent(new Event("resize"));
  }
  waveTab.addEventListener("click", () => select(false)); singTab.addEventListener("click", () => select(true));
  for (const tab of [waveTab, singTab]) tab.addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    e.preventDefault(); const on = e.key === "End" || (e.key !== "Home" && !active);
    select(on); (active ? singTab : waveTab).focus();
  });
  canvas.addEventListener("click", (e) => {
    if (!duration) return;
    const rect = canvas.getBoundingClientRect();
    setPlayheadTime(Math.max(0, Math.min(duration, (e.clientX - rect.left) / rect.width * duration)));
  });
  canvas.addEventListener("keydown", (e) => {
    if (!duration || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    e.preventDefault(); e.stopPropagation();
    const time = transport()?.getCurrentTime?.() || 0;
    setPlayheadTime(e.key === "Home" ? 0 : e.key === "End" ? duration : Math.max(0, Math.min(duration, time + (e.key === "ArrowRight" ? 1 : -1) * (e.shiftKey ? 10 : 1))));
  });
  document.addEventListener("catalogviewchange", (e) => {
    sidebarView = e.detail?.view;
    if (sidebarView === "lyrics") select(true);
  });
  document.addEventListener("trackwillopen", (e) => {
    if (e.detail?.source === "processing") select(false);
  });
  const availability = () => {
    singTab.disabled = app.classList.contains("is-processing-track");
    if (singTab.disabled && active) select(false);
  };
  new MutationObserver(availability).observe(app, { attributes: true, attributeFilter: ["class"] });
  availability();
  new ResizeObserver(() => { if (active) draw(transport()?.getCurrentTime?.() || 0); }).observe(canvas);
  onLanguageChange(message);
}
