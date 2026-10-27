// Apply the cached appearance before CSS paints; the shared store resolves later.
(() => {
 let preference = "system";
 try { const value = JSON.parse(localStorage.getItem("stemdeck.theme")); if (["dark", "light", "system"].includes(value)) preference = value; } catch {}
 const root = document.documentElement;
 root.dataset.themePreference = preference;
 root.dataset.theme = preference === "system" ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : preference;
})();
