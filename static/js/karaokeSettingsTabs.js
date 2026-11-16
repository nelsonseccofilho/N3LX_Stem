import { getLanguage, onLanguageChange } from "./i18n.js";

/**
 * C27.6B — Organiza os fluxos existentes em abas.
 * Preserva IDs, listeners, geracao, busca e persistencia.
 */
export function initKaraokeSettingsTabs() {
  const dialog = document.getElementById("karaokeSettings");
  if (!dialog || dialog.dataset.tabsReady === "true") return;

  const content = dialog.querySelector(".karaoke-settings-content");
  const source = content?.querySelector(".karaoke-source-actions");
  const searchOpen = document.getElementById("lyricsOpenSearchBtn");
  const searchForm = document.getElementById("lyricsSearchForm");
  const language = content?.querySelector(".lyrics-generator-language");
  const model = content?.querySelector(".lyrics-generator-model");
  const unavailable = document.getElementById("karaokeModelUnavailable");
  const advanced = content?.querySelector(".lyrics-advanced-actions");
  const edit = document.getElementById("lyricsEditBtn");
  const tools = document.getElementById("karaokeToolsHost");

  const required = [
    content, source, searchOpen, searchForm,
    language, model, unavailable, advanced, edit, tools,
  ];

  if (required.some(node => !node)) {
    console.error("C27.6B: controles obrigatorios ausentes");
    return;
  }

  const names = ["generate", "search", "sync"];
  const nav = document.createElement("div");
  nav.className = "karaoke-tabs";
  nav.setAttribute("role", "tablist");

  const tabs = {};
  const panels = {};

  for (const name of names) {
    const tab = document.createElement("button");
    tab.type = "button";
    tab.id = `karaokeTab-${name}`;
    tab.className = "karaoke-tab";
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-controls", `karaokePanel-${name}`);

    const panel = document.createElement("section");
    panel.id = `karaokePanel-${name}`;
    panel.className = "karaoke-tab-panel";
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-labelledby", tab.id);

    nav.append(tab);
    tabs[name] = tab;
    panels[name] = panel;
  }

  function hint(name) {
    const p = document.createElement("p");
    p.className = "lyrics-note karaoke-tab-hint";
    p.dataset.hint = name;
    return p;
  }

  const generateHint = hint("generate");
  const searchHint = hint("search");
  const syncHint = hint("sync");

  // Reorganizar nós reais, sem clonar controles.
  // Os eventos e IDs originais permanecem válidos.
  searchOpen.remove();

  // O botão original continua servindo ao fluxo de abertura
  // e preenchimento da busca, mas não ocupa espaço na UI.
  searchOpen.hidden = true;

  panels.generate.append(
    generateHint,
    language,
    model,
    unavailable,
    source
  );

  panels.search.append(
    searchHint,
    searchOpen,
    searchForm
  );

  panels.sync.append(
    syncHint,
    advanced,
    tools
  );

  const footer = document.createElement("div");
  footer.className = "karaoke-tab-footer";
  footer.append(edit);

  content.replaceChildren(
    panels.generate,
    panels.search,
    panels.sync,
    footer
  );

  content.before(nav);

  let active = "generate";

  function labels() {
    const en = String(getLanguage()).toLowerCase().startsWith("en");

    const titles = en
      ? ["Generate lyrics", "Find lyrics", "Synchronization"]
      : ["Gerar letra", "Buscar letra", "Sincronização"];

    names.forEach((name, index) => {
      tabs[name].textContent = titles[index];
    });

    nav.setAttribute(
      "aria-label",
      en ? "Karaoke workflows" : "Etapas do karaokê"
    );

    generateHint.textContent = en
      ? "Generate lyrics and word timing using the vocals."
      : "Gere a letra e os tempos das palavras usando os vocais.";

    searchHint.textContent = en
      ? "Find lyrics in LRCLIB and compare recordings."
      : "Encontre letras no LRCLIB e compare as gravações.";

    syncHint.textContent = en
      ? "Synchronize with vocals or adjust phrase timing."
      : "Sincronize com os vocais ou ajuste os tempos das frases.";
  }

  function activate(name, focus = false) {
    if (!panels[name]) return;

    active = name;

    for (const key of names) {
      const selected = key === name;

      tabs[key].setAttribute("aria-selected", String(selected));
      tabs[key].tabIndex = selected ? 0 : -1;
      panels[key].hidden = !selected;
    }

    if (name === "search" && searchForm.hidden) {
      // Reutiliza o handler já registrado em lyrics.js.
      if (!searchOpen.disabled) searchOpen.click();
    }

    if (focus) {
      if (name === "search" && !searchForm.hidden) {
        const artist = document.getElementById("lyricsSearchArtist");
        const title = document.getElementById("lyricsSearchTitle");
        (artist?.value ? title : artist)?.focus();
      } else {
        tabs[name].focus();
      }
    }
  }

  for (const name of names) {
    tabs[name].addEventListener("click", () => {
      activate(name, true);
    });
  }

  nav.addEventListener("keydown", event => {
    const index = names.indexOf(active);
    let next;

    switch (event.key) {
      case "ArrowRight": next = (index + 1) % 3; break;
      case "ArrowLeft": next = (index + 2) % 3; break;
      case "Home": next = 0; break;
      case "End": next = 2; break;
      default: return;
    }

    event.preventDefault();
    activate(names[next], true);
  });

  dialog.addEventListener("close", () => {
    activate("generate");
  });

  onLanguageChange(labels);
  labels();
  activate("generate");

  dialog.dataset.tabsReady = "true";
}
