import { storeGet, storeSet } from "./utils.js";
const choices = new Set(["dark", "light", "system"]);
const normalize = value => choices.has(value) ? value : "system";
const media = window.matchMedia("(prefers-color-scheme: dark)");
let preference = normalize(document.documentElement.dataset.themePreference), revision = 0;
export const getTheme = () => preference;
function apply() {
 const theme = preference === "system" ? (media.matches ? "dark" : "light") : preference;
 const root = document.documentElement;
 root.dataset.themePreference = preference;
 root.dataset.theme = theme;
 root.style.colorScheme = theme;
 window.n3lxAppearance?.setTheme(preference);
 document.dispatchEvent(new CustomEvent("themechange", { detail: { preference, theme } }));
 window.dispatchEvent(new Event("resize"));
}
export async function initTheme() {
 const token = revision;
 const saved = await storeGet("stemdeck.theme", "system");
 if (token === revision) { preference = normalize(saved); apply(); }
}
export async function setTheme(value) {
 preference = normalize(value); ++revision; apply();
 await storeSet("stemdeck.theme", preference);
}
media.addEventListener("change", () => { if (preference === "system") apply(); });
