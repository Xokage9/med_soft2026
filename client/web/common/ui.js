export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style") Object.assign(el.style, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "value") el.value = v;
    else if (k === "checked" || k === "disabled" || k === "selected") el[k] = !!v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const SVG_NS = "http://www.w3.org/2000/svg";
const ICONS = {
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75",
  key: "M21 2l-2 2m-7.6 7.6a5.5 5.5 0 1 1-7.78 7.78 5.5 5.5 0 0 1 7.78-7.78zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4",
  book: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20V2H6.5A2.5 2.5 0 0 0 4 4.5v15zM4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5",
  activity: "M22 12h-4l-3 9L9 3l-3 9H2",
  lock: "M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4",
  unlock: "M5 11h14v10H5zM8 11V7a4 4 0 0 1 7.9-1",
  logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  plus: "M12 5v14M5 12h14",
  x: "M18 6L6 18M6 6l12 12",
  edit: "M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z",
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h8",
  undo: "M3 7v6h6M3 13a9 9 0 1 0 3-7.7L3 7",
  user: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  clock: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 6v6l4 2",
};
export function icon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("width", "16");
  svg.setAttribute("height", "16");
  const p = document.createElementNS(SVG_NS, "path");
  p.setAttribute("d", ICONS[name] || "");
  svg.append(p);
  return svg;
}

let toastBox;
export function toast(text, kind = "") {
  if (!toastBox) { toastBox = h("div", { class: "toasts" }); document.body.append(toastBox); }
  const t = h("div", { class: `toast ${kind}` }, text);
  toastBox.append(t);
  setTimeout(() => t.remove(), kind === "error" ? 6000 : 3500);
}
export const toastError = (e) => toast(e?.message || String(e), "error");

export function modal({ title, body, actions = [], onClose }) {
  const overlay = h("div", { class: "overlay" });
  const close = () => { overlay.remove(); document.removeEventListener("keydown", onKey); onClose?.(); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  const card = h("div", { class: "card modal", role: "dialog", "aria-modal": "true" },
    h("div", { class: "card-head" }, h("h2", { class: "grow" }, title),
      h("button", { class: "btn ghost icon", title: "Закрыть", onclick: close }, icon("x"))),
    h("div", { class: "card-body" }, body),
    actions.length ? h("div", { class: "modal-actions" }, actions) : null);
  overlay.append(card);
  overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
  document.body.append(overlay);
  setTimeout(() => card.querySelector("input, select, textarea")?.focus(), 30);
  return { close, el: card };
}

export function confirmDialog(title, text, { okText = "Подтвердить", danger = false } = {}) {
  return new Promise((resolve) => {
    let done = false;
    const m = modal({
      title, body: h("p", {}, text),
      onClose: () => { if (!done) resolve(false); },
      actions: [
        h("button", { class: "btn", onclick: () => m.close() }, "Отмена"),
        h("button", {
          class: `btn ${danger ? "danger" : "primary"}`,
          onclick: () => { done = true; m.close(); resolve(true); },
        }, okText),
      ],
    });
  });
}

export function showPasswordDialog(title, username, password) {
  const copyBtn = h("button", {
    class: "btn small", onclick: async () => {
      try { await navigator.clipboard.writeText(password); toast("Пароль скопирован", "ok"); }
      catch { toast("Не удалось скопировать — выделите вручную", "error"); }
    },
  }, "Скопировать");
  const m = modal({
    title,
    body: [
      h("div", { class: "row" }, h("span", { class: "muted" }, "Логин:"), h("b", { class: "mono" }, username)),
      h("div", { class: "secret-box" }, password),
      h("div", { class: "callout" }, "Пароль показывается один раз: в базе хранится только его хэш (Argon2id). Передайте его медработнику."),
    ],
    actions: [copyBtn, h("button", { class: "btn primary", onclick: () => m.close() }, "Готово")],
  });
}

export function field(label, input, { full = false, hint } = {}) {
  const err = h("div", { class: "err" });
  const wrap = h("label", { class: `field${full ? " full" : ""}` }, h("span", {}, label), input,
    hint ? h("div", { class: "muted", style: { fontSize: "12px" } }, hint) : null, err);
  wrap.setError = (msg) => { err.textContent = msg || ""; input.classList.toggle("invalid", !!msg); };
  return wrap;
}

export function applyErrors(fields, e) {
  Object.values(fields).forEach((f) => f.setError(""));
  let shown = false;
  for (const { field: name, message } of e?.errors || []) {
    if (fields[name]) { fields[name].setError(message); shown = true; }
  }
  if (!shown) toastError(e);
}

export function busy(button, promiseFn) {
  return async (...args) => {
    button.disabled = true;
    try { return await promiseFn(...args); } finally { button.disabled = false; }
  };
}

const dtf = new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", timeStyle: "medium" });
const df = new Intl.DateTimeFormat("ru-RU", { dateStyle: "short" });
export const fmtDateTime = (s) => (s ? dtf.format(new Date(s)) : "—");
export const fmtDate = (s) => (s ? df.format(new Date(s + (s.length === 10 ? "T00:00:00" : ""))) : "—");

export const ROLE_LABEL = {
  doctor: "Врач", nurse: "Медсестра/медбрат", "laboratory-technician": "Лаборант", other: "Другое",
  admin: "Администратор",
};
export const SEX_LABEL = { M: "Мужской", F: "Женский", U: "Не установлен" };

export function roleBadge(role) {
  const kind = { doctor: "accent", nurse: "info", "laboratory-technician": "warn", admin: "danger" }[role] || "";
  return h("span", { class: `badge ${kind}` }, ROLE_LABEL[role] || role);
}

export function select(options, value) {
  return h("select", { class: "input" },
    options.map(([v, label]) => h("option", { value: v, selected: v === value }, label)));
}

export function emptyRow(cols, text) {
  return h("tr", {}, h("td", { colspan: cols, class: "empty" }, text));
}
