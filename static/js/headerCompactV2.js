// N3LX_Stem: compact header v2 (local-v1 compatible).
// Move the EXISTING lane badges to the spare view toolbar, preserving
// IDs, event handlers, and the transport/now-playing controls.
export function initHeaderCompactV2() {
  const app = document.querySelector(".app.daw");
  const composer = document.querySelector("#job-form.header-compact");
  const lanes = document.getElementById("availableLanes");
  const tools = document.querySelector(".studio-view-tools");
  if (!app || !composer || !lanes || !tools) return;
  if (app.classList.contains("header-v2")) return;

  const hint = tools.querySelector(".view-shortcuts");
  if (hint) tools.insertBefore(lanes, hint);
  else tools.appendChild(lanes);
  lanes.classList.add("available-lanes-in-toolbar");
  app.classList.add("header-v2");
}
