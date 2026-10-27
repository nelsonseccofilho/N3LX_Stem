import { t } from "./i18n.js";
export function confirmAction({ title, message, confirmLabel }) {
 return new Promise(resolve => {
  const opener = document.activeElement;
  const dialog = document.createElement("dialog"); dialog.className = "action-confirm";
  const heading = document.createElement("h2"); heading.id = "actionConfirmTitle"; heading.textContent = title;
  const description = document.createElement("p"); description.id = "actionConfirmDescription"; description.textContent = message;
  dialog.setAttribute("aria-labelledby", heading.id); dialog.setAttribute("aria-describedby", description.id);
  const actions = document.createElement("div"); actions.className = "action-confirm-actions";
  const cancel = document.createElement("button"); cancel.type = "button"; cancel.textContent = t("confirm.cancel");
  const accept = document.createElement("button"); accept.type = "button"; accept.className = "confirm-danger"; accept.textContent = confirmLabel;
  let settled = false;
  const finish = result => { if (settled) return; settled = true; dialog.close(); dialog.remove(); if(opener?.isConnected) opener.focus(); resolve(result); };
  cancel.addEventListener("click", () => finish(false)); accept.addEventListener("click", () => finish(true));
  dialog.addEventListener("cancel", event => { event.preventDefault(); finish(false); });
  dialog.addEventListener("close", () => finish(false));
  actions.append(cancel, accept); dialog.append(heading, description, actions); document.body.append(dialog); dialog.showModal(); cancel.focus();
 });
}
