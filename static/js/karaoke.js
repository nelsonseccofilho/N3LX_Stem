import { getCurrentTrackInfo, setCatalogView } from "./catalog.js";
import { setLyricsPresentation } from "./lyrics.js";
import { transport, setPlayheadTime } from "./transport.js";
import { t, getLanguage, onLanguageChange } from "./i18n.js";
import { getSectionsSnapshot, sectionDisplayName } from "./sections.js";
import { refreshAnalysisKey } from './analysisKey.js';

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
  const settings = document.getElementById("karaokeSettings"), settingsOpen = document.getElementById("lyricsSettingsOpen");
  const cinemaOpen = document.getElementById("karaokeCinemaOpen"), cinemaExit = document.getElementById("karaokeCinemaExit");
  let cinemaReturnFocus = null;
  const cinemaTools = document.createElement('div');
  cinemaTools.className = 'cinema-tools';
  cinemaTools.hidden = true;
  const cinemaKey = document.createElement('output');
  cinemaKey.id = 'cinemaKey';
  cinemaKey.setAttribute('aria-live', 'polite');
  cinemaKey.textContent = 'Tom não identificado';
  cinemaTools.append(cinemaKey);
  stage.prepend(cinemaTools);
  const pitchGroup = document.querySelector('.footer-group-key');
  const pitchHome = document.createComment('Cinema pitch controls home');
  pitchGroup?.before(pitchHome);
  settingsOpen?.addEventListener("click", () => {
    if (!getCurrentTrackInfo()) return;
    if (!settings.open) settings.showModal();
  });
  document.getElementById("lyricsSettingsClose")?.addEventListener("click", () => settings.close());
  settings?.addEventListener("close", () => { if (settingsOpen?.isConnected) settingsOpen.focus(); });
  new MutationObserver(() => { if (panel.classList.contains("is-karaoke-processing") && settings.open) settings.close(); })
    .observe(panel, { attributes:true, attributeFilter:["class"] });
  cinemaOpen?.addEventListener("click", async () => {
    cinemaReturnFocus = cinemaOpen;
    try { await stage.requestFullscreen(); }
    catch { document.getElementById("lyricsGeneratorStatus").textContent = t("karaoke.cinemaUnavailable"); }
  });
  cinemaExit?.addEventListener("click", () => { if (document.fullscreenElement === stage) void document.exitFullscreen(); });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && document.fullscreenElement === stage) {
      event.preventDefault(); event.stopPropagation();
      void document.exitFullscreen();
    }
  }, true);
  document.addEventListener("fullscreenchange", () => {
    const on = document.fullscreenElement === stage;
    stage.classList.toggle("cinema-mode", on);
    cinemaExit.hidden = !on;
    cinemaTools.hidden = !on;
    refreshAnalysisKey();
    if (pitchGroup) {
      if (on) cinemaTools.append(pitchGroup);
      else pitchHome.after(pitchGroup);
    }
    if (on) cinemaExit.focus();
    else if (cinemaReturnFocus?.isConnected) { cinemaReturnFocus.focus(); cinemaReturnFocus = null; }
    window.dispatchEvent(new Event("resize"));
  });
  let active = false, trackId = null, duration = 0, peaks = [], frame = 0, request = 0;
  let controller = null, waveState = "", sidebarView = "library", lastSecond = -1;
  const sectionHost = document.getElementById("karaokeSections");
  let visibleSections = [], activeSection = -1;

  // C27.6B.3 — Empty state, without changing library selection.
  const empty = document.createElement("section");
  empty.id = "karaokeEmptyState";
  empty.className = "karaoke-empty-state";
  empty.setAttribute("role", "status");

  const emptyIcon = document.createElement("div");
  emptyIcon.className = "karaoke-empty-symbol";
  emptyIcon.textContent = "♫";
  emptyIcon.setAttribute("aria-hidden", "true");

  const emptyTitle = document.createElement("h2");
  const emptyDescription = document.createElement("p");

  const emptyAction = document.createElement("button");
  emptyAction.type = "button";
  emptyAction.className = "lyrics-align-btn lyrics-generate-btn";

  emptyAction.addEventListener("click", () => {
    setCatalogView("library");
    waveTab.click();
  });

  empty.append(
    emptyIcon,
    emptyTitle,
    emptyDescription,
    emptyAction
  );

  stage.prepend(empty);

  function translateEmptyState() {
    const english = String(getLanguage())
      .toLowerCase()
      .startsWith("en");

    emptyTitle.textContent = english
      ? "No song selected"
      : "Nenhuma música selecionada";

    emptyDescription.textContent = english
      ? "Choose a song from your library or import a track to get started."
      : "Para começar, importe uma faixa ou selecione uma faixa em sua coleção de música.";

    emptyAction.textContent = english
      ? "Open library"
      : "Abrir biblioteca";
  }

  function updateEmptyState(info = getCurrentTrackInfo()) {
    const isEmpty = !info?.id;

    empty.hidden = !isEmpty;

    stage.classList.toggle(
      "karaoke-no-track",
      isEmpty
    );

    if (settingsOpen) settingsOpen.disabled = isEmpty;
    if (cinemaOpen) cinemaOpen.disabled = isEmpty;

    if (isEmpty && settings?.open) {
      settings.close();
    }
  }

  translateEmptyState();
  updateEmptyState();

  const fmt = (s) => `${Math.floor(Math.max(0, s) / 60)}:${String(Math.floor(Math.max(0, s) % 60)).padStart(2, "0")}`;
  const message = () => { document.getElementById("karaokeWaveStatus").textContent = waveState ? t(waveState) : ""; };
  function renderSections() {
    if (!sectionHost) return;
    const snapshot = getSectionsSnapshot();
    sectionHost.replaceChildren();
    visibleSections = []; activeSection = -1;
    if (!trackId || snapshot.trackId !== trackId || !(duration > 0)) {
      sectionHost.hidden = true;
      return;
    }
    const all = snapshot.sections;
    for (const section of all) {
      const start = Math.max(0, Number(section.start));
      const end = Math.min(duration, Number(section.end));
      if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) continue;
      const label = sectionDisplayName(section, all);
      const item = document.createElement("span");
      item.className = "karaoke-section";
      item.setAttribute("role", "listitem");
      item.setAttribute("aria-label", label + ", " + fmt(start) + "–" + fmt(end));
      item.title = label + " · " + fmt(start) + "–" + fmt(end);
      item.textContent = label;
      item.style.left = (start / duration * 100) + "%";
      item.style.width = ((end - start) / duration * 100) + "%";
      if (/^#[0-9a-f]{6}$/i.test(String(section.color || ""))) item.style.setProperty("--section-color", section.color);
      sectionHost.append(item);
      visibleSections.push({ start, end, element: item });
    }
    sectionHost.hidden = visibleSections.length === 0;
  }
  function markSection(time) {
    const index = visibleSections.findIndex(s => time >= s.start && time < s.end);
    if (index === activeSection) return;
    if (visibleSections[activeSection]) visibleSections[activeSection].element.classList.remove("is-active");
    activeSection = index;
    if (visibleSections[index]) visibleSections[index].element.classList.add("is-active");
  }
  document.addEventListener("sectionschange", () => { if (active) renderSections(); });
  const draw = (time) => {
    const box = canvas.getBoundingClientRect(), scale = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.round(box.width * scale)), height = Math.max(1, Math.round(box.height * scale));
    if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, width, height);
    const accent = getComputedStyle(stage).getPropertyValue("--accent").trim() || "#f4b740";
    const progress = duration ? Math.min(1, time / duration) : 0;
    const max = Math.max(.01, ...peaks);
    const bars = Math.min(peaks.length, Math.floor(width / (3 * scale)));
    for (let i = 0; i < bars; i++) {
      const h = Math.max(2 * scale, peaks[Math.floor(i * peaks.length / bars)] / max * height * .85);
      ctx.fillStyle = i / bars <= progress ? accent : (getComputedStyle(stage).getPropertyValue("--wave-unplayed").trim() || "#5f798b");
      ctx.fillRect(i * width / bars, (height - h) / 2, Math.max(scale, width / bars - scale), h);
    }
    ctx.fillStyle = accent;
    ctx.fillRect(progress * (width - 2 * scale), 0, 2 * scale, height);
  };
  async function load(info) {
    const token = ++request;
    controller?.abort(); controller = new AbortController();
    trackId = info?.id ?? null; duration = info?.duration || 0; peaks = []; lastSecond = -1;
    updateEmptyState(info);
    renderSections();
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
    markSection(time);
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
    if (!on && document.fullscreenElement === stage) void document.exitFullscreen();
    if (!on && settings?.open) settings.close();
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
  onLanguageChange(() => {
    message();
    translateEmptyState();
    if (active) renderSections();
  });
}
