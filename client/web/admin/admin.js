import { Api } from "../common/api.js";
import { WS_BASE } from "../common/config.js";
import {
  ROLE_LABEL, applyErrors, confirmDialog, emptyRow, field, fmtDateTime, h, icon, modal,
  roleBadge, select, showPasswordDialog, toast, toastError,
} from "../common/ui.js";

const api = new Api("his.admin.refresh");
const root = document.getElementById("root");
const ROLES = Object.entries(ROLE_LABEL).filter(([k]) => k !== "admin");

api.onLogout = (msg) => { toast(msg, "error"); showLogin(); };


function authShell(title, subtitle, ...content) {
  root.replaceChildren(h("div", { class: "auth-page" },
    h("div", { class: "card auth-card" }, h("div", { class: "card-body" },
      h("div", { class: "auth-title" }, h("div", { class: "brand-mark" }, "+"),
        h("div", {}, h("h1", {}, title), h("div", { class: "muted" }, subtitle))),
      ...content))));
}

async function boot() {
  if (await api.restore()) return showApp();
  try {
    const { configured } = await api.public("GET", "/api/auth/admin/status");
    configured ? showLogin() : showSetupPassword();
  } catch (e) {
    authShell("MedSoft HIS", "Администратор",
      h("div", { class: "callout" }, e.message),
      h("button", { class: "btn", onclick: boot }, "Повторить"));
  }
}

function showLogin() {
  const pwd = h("input", { class: "input", type: "password", autocomplete: "current-password" });
  const code = h("input", { class: "input code-input", inputmode: "numeric", maxlength: "6", autocomplete: "one-time-code", placeholder: "000000" });
  const err = h("div", { class: "callout hidden" });
  const btn = h("button", { class: "btn primary", type: "submit" }, "Войти");
  const form = h("form", { class: "stack", onsubmit: async (e) => {
    e.preventDefault();
    btn.disabled = true; err.classList.add("hidden");
    try {
      api.setPair(await api.public("POST", "/api/auth/admin/login", { password: pwd.value, code: code.value }));
      showApp();
    } catch (ex) {
      if (ex.status === 409) return showSetupPassword();
      err.textContent = ex.message; err.classList.remove("hidden"); code.value = "";
    } finally { btn.disabled = false; }
  } },
  field("Пароль администратора", pwd),
  field("Код из приложения-аутентификатора", code),
  err, btn);
  authShell("Вход администратора", "Пароль и одноразовый код TOTP", form);
  pwd.focus();
}

function showSetupPassword() {
  const pwd = h("input", { class: "input", type: "password", autocomplete: "new-password" });
  const pwd2 = h("input", { class: "input", type: "password", autocomplete: "new-password" });
  const fPwd = field("Новый пароль", pwd, { hint: "Не короче 12 символов, заглавные и строчные буквы, цифры" });
  const fPwd2 = field("Повторите пароль", pwd2);
  const btn = h("button", { class: "btn primary", type: "submit" }, "Далее");
  const form = h("form", { class: "stack", onsubmit: async (e) => {
    e.preventDefault();
    fPwd.setError(""); fPwd2.setError("");
    if (pwd.value !== pwd2.value) return fPwd2.setError("Пароли не совпадают");
    btn.disabled = true;
    try {
      const setup = await api.public("POST", "/api/auth/admin/setup/begin",
        { password: pwd.value, password_confirm: pwd2.value });
      showSetupTotp(setup);
    } catch (ex) {
      if (ex.status === 409) return showLogin();
      fPwd.setError(ex.message);
    } finally { btn.disabled = false; }
  } },
  h("div", { class: "steps" }, h("span", { class: "on" }), h("span")),
  h("div", { class: "callout info" }, "Первый запуск: задайте пароль администратора и подключите двухфакторную аутентификацию."),
  fPwd, fPwd2, btn);
  authShell("Настройка администратора", "Шаг 1 из 2 · пароль", form);
  pwd.focus();
}

function showSetupTotp(setup) {
  const code = h("input", { class: "input code-input", inputmode: "numeric", maxlength: "6", placeholder: "000000", autocomplete: "one-time-code" });
  const fCode = field("Код из приложения", code);
  const btn = h("button", { class: "btn primary", type: "submit" }, "Подтвердить и войти");
  const form = h("form", { class: "stack", onsubmit: async (e) => {
    e.preventDefault();
    btn.disabled = true; fCode.setError("");
    try {
      api.setPair(await api.public("POST", "/api/auth/admin/setup/complete",
        { setup_id: setup.setup_id, code: code.value }));
      toast("Двухфакторная аутентификация включена", "ok");
      showApp();
    } catch (ex) { fCode.setError(ex.message); code.value = ""; code.focus(); }
    finally { btn.disabled = false; }
  } },
  h("div", { class: "steps" }, h("span", { class: "on" }), h("span", { class: "on" })),
  h("div", { class: "muted" }, "Отсканируйте QR-код в Google Authenticator, Яндекс Ключе или аналоге (RFC 6238) и введите код."),
  h("img", { class: "qr", src: setup.qr_data_url, alt: "QR-код TOTP" }),
  h("div", { class: "field" }, h("span", {}, "Или введите секрет вручную"),
    h("div", { class: "secret-box", style: { fontSize: "14px" } }, setup.secret.replace(/(.{4})/g, "$1 ").trim())),
  fCode, btn);
  authShell("Настройка администратора", "Шаг 2 из 2 · TOTP", form);
  code.focus();
}


const VIEWS = {
  staff: { title: "Медработники", icon: "users", render: renderStaff },
  accounts: { title: "Аккаунты", icon: "key", render: renderAccounts },
  diagnoses: { title: "Справочник диагнозов", icon: "book", render: renderDiagnoses },
  audit: { title: "Аудит", icon: "activity", render: renderAudit },
};
let currentView = null;
let viewCleanup = null;

function showApp() {
  const nav = h("nav", { class: "stack", style: { gap: "2px" } });
  const title = h("h1", { class: "grow" });
  const content = h("div", { class: "content" });
  const topRight = h("div", { class: "row" }, roleBadge("admin"));

  root.replaceChildren(h("div", { class: "app" },
    h("aside", { class: "sidebar" },
      h("div", { class: "brand" }, h("div", { class: "brand-mark" }, "+"),
        h("div", {}, h("b", {}, "MedSoft HIS"), h("small", {}, "Администратор"))),
      nav,
      h("div", { class: "sidebar-foot" },
        h("button", { class: "nav-item", onclick: async () => { await api.logout(); viewCleanup?.(); showLogin(); } },
          icon("logout"), "Выйти"))),
    h("main", { class: "main" }, h("header", { class: "topbar" }, title, topRight), content)));

  const go = (key) => {
    viewCleanup?.(); viewCleanup = null;
    currentView = key;
    try { localStorage.setItem("his.admin.view", key); } catch {}
    nav.replaceChildren(...Object.entries(VIEWS).map(([k, v]) =>
      h("button", { class: `nav-item${k === key ? " active" : ""}`, onclick: () => go(k) }, icon(v.icon), v.title)));
    title.textContent = VIEWS[key].title;
    content.replaceChildren();
    viewCleanup = VIEWS[key].render(content) || null;
  };
  let saved = null;
  try { saved = localStorage.getItem("his.admin.view"); } catch {}
  go(VIEWS[saved] ? saved : "staff");
}


function renderStaff(content) {
  const search = h("input", { class: "input", placeholder: "Поиск по ФИО или должности" });
  const showDeleted = h("input", { type: "checkbox" });
  const tbody = h("tbody");
  let items = [];

  const draw = () => {
    const q = search.value.trim().toLowerCase();
    const rows = items.filter((s) => !q || `${s.last_name} ${s.first_name} ${s.position}`.toLowerCase().includes(q));
    tbody.replaceChildren(...(rows.length ? rows.map((s) =>
      h("tr", { class: `clickable${s.is_deleted ? " deleted" : ""}`, onclick: () => openStaff(s.id, load) },
        h("td", {}, h("b", {}, `${s.last_name} ${s.first_name}`)),
        h("td", {}, s.position),
        h("td", {}, roleBadge(s.role)),
        h("td", {}, s.account
          ? h("span", { class: `badge ${s.account.is_active ? "ok" : ""}` }, s.account.username, s.account.is_active ? "" : " · откл.")
          : h("span", { class: "muted" }, "нет")),
        h("td", {}, s.is_deleted ? h("span", { class: "badge danger" }, "удалён") : h("span", { class: "badge ok" }, "работает")),
      )) : [emptyRow(5, "Медработников нет")]));
  };
  const load = async () => {
    try { items = await api.get(`/api/admin/staff?include_deleted=${showDeleted.checked}`); draw(); }
    catch (e) { toastError(e); }
  };
  search.addEventListener("input", draw);
  showDeleted.addEventListener("change", load);

  content.append(
    h("div", { class: "toolbar" }, search,
      h("label", { class: "check" }, showDeleted, "Показывать удалённых"),
      h("div", { class: "grow" }),
      h("button", { class: "btn primary", onclick: () => openStaff(null, load) }, icon("plus"), "Добавить")),
    h("div", { class: "card table-wrap" }, h("table", { class: "grid" },
      h("thead", {}, h("tr", {}, ["ФИО", "Должность", "Роль", "Аккаунт", "Статус"].map((t) => h("th", {}, t)))),
      tbody)));
  load();
}

async function openStaff(id, onChange) {
  let staff = null;
  if (id) {
    try { staff = await api.get(`/api/admin/staff/${id}`); } catch (e) { return toastError(e); }
  }
  const overlay = h("div", { class: "drawer-overlay" });
  const close = () => { overlay.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape" && !document.querySelector(".overlay")) close(); };
  document.addEventListener("keydown", onKey);
  overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });

  const readonly = staff?.is_deleted;
  const inp = {
    last_name: h("input", { class: "input", value: staff?.last_name ?? "", disabled: readonly }),
    first_name: h("input", { class: "input", value: staff?.first_name ?? "", disabled: readonly }),
    position: h("input", { class: "input", value: staff?.position ?? "", disabled: readonly }),
    role: select(ROLES, staff?.role ?? "other"),
  };
  inp.role.disabled = !!readonly;
  const f = {
    last_name: field("Фамилия", inp.last_name), first_name: field("Имя", inp.first_name),
    position: field("Должность", inp.position, { full: true }), role: field("Роль", inp.role, { full: true }),
  };
  const saveBtn = h("button", { class: "btn primary", disabled: readonly, onclick: async () => {
    const body = Object.fromEntries(Object.entries(inp).map(([k, el]) => [k, el.value]));
    if (staff && staff.account && body.role !== staff.role &&
        !(await confirmDialog("Смена роли", "Все сессии этого медработника будут завершены (refresh-токены отозваны). Продолжить?"))) return;
    saveBtn.disabled = true;
    try {
      staff = staff ? await api.put(`/api/admin/staff/${staff.id}`, body) : await api.post("/api/admin/staff", body);
      toast("Сохранено", "ok"); onChange(); close(); openStaff(staff.id, onChange);
    } catch (e) { applyErrors(f, e); } finally { saveBtn.disabled = false; }
  } }, "Сохранить");

  const sections = [
    h("div", {}, h("div", { class: "section-title" }, "Данные медработника"),
      h("div", { class: "form-grid" }, f.last_name, f.first_name, f.position, f.role)),
  ];
  if (staff) sections.push(accountSection(staff, () => { onChange(); close(); openStaff(staff.id, onChange); }));
  if (staff) sections.push(h("div", { class: "muted", style: { fontSize: "12px" } },
    `Создан ${fmtDateTime(staff.created_at)} · изменён ${fmtDateTime(staff.updated_at)}`,
    staff.deleted_at ? ` · удалён ${fmtDateTime(staff.deleted_at)}` : ""));

  const deleteBtn = staff && !staff.is_deleted ? h("button", { class: "btn danger", onclick: async () => {
    const ok = await confirmDialog("Удалить медработника?",
      `${staff.last_name} ${staff.first_name} будет помечен удалённым. Запись останется в базе, связанный аккаунт будет деактивирован.`,
      { okText: "Удалить", danger: true });
    if (!ok) return;
    try { await api.del(`/api/admin/staff/${staff.id}`); toast("Медработник удалён", "ok"); onChange(); close(); }
    catch (e) { toastError(e); }
  } }, "Удалить") : null;

  overlay.append(h("aside", { class: "drawer" },
    h("div", { class: "drawer-head" },
      h("div", { class: "grow" }, h("h2", {}, staff ? `${staff.last_name} ${staff.first_name}` : "Новый медработник"),
        staff?.is_deleted ? h("span", { class: "badge danger" }, "удалён") : null),
      h("button", { class: "btn ghost icon", onclick: close }, icon("x"))),
    h("div", { class: "drawer-body" }, sections),
    h("div", { class: "modal-actions" }, deleteBtn, h("div", { class: "grow" }),
      h("button", { class: "btn", onclick: close }, "Закрыть"), saveBtn)));
  document.body.append(overlay);
  inp.last_name.focus();
}

function accountSection(staff, refresh) {
  const box = h("div", {}, h("div", { class: "section-title" }, "Учётная запись"));
  const acc = staff.account;
  if (!acc) {
    if (staff.is_deleted) { box.append(h("div", { class: "muted" }, "Нет аккаунта")); return box; }
    const username = h("input", { class: "input", placeholder: "например, ivanov", maxlength: "16" });
    const fUser = field("Логин (3–16 символов: латиница, цифры, . _ -)", username);
    const btn = h("button", { class: "btn primary", onclick: async () => {
      btn.disabled = true;
      try {
        const res = await api.post(`/api/admin/staff/${staff.id}/account`, { username: username.value });
        showPasswordDialog("Аккаунт создан", res.account.username, res.password);
        refresh();
      } catch (e) { applyErrors({ username: fUser }, e); } finally { btn.disabled = false; }
    } }, icon("key"), "Создать аккаунт");
    box.append(h("div", { class: "stack" }, fUser, h("div", {}, btn)));
    return box;
  }
  box.append(h("div", { class: "card", style: { boxShadow: "none" } }, h("div", { class: "card-body stack" },
    h("div", { class: "row" }, h("b", { class: "mono grow" }, acc.username),
      h("span", { class: `badge ${acc.is_active ? "ok" : "danger"}` }, acc.is_active ? "активен" : "деактивирован")),
    h("div", { class: "row" },
      h("button", { class: "btn small", disabled: staff.is_deleted, onclick: () => resetPassword(acc, refresh) }, "Новый пароль"),
      h("button", { class: "btn small", disabled: staff.is_deleted && !acc.is_active,
        onclick: () => toggleAccount(acc, refresh) }, acc.is_active ? "Деактивировать" : "Активировать")))));
  return box;
}

async function resetPassword(acc, done) {
  if (!(await confirmDialog("Сгенерировать новый пароль?",
    `Старый пароль ${acc.username} перестанет действовать, все сессии будут завершены.`))) return;
  try {
    const res = await api.post(`/api/admin/accounts/${acc.id}/reset-password`);
    showPasswordDialog("Новый пароль", res.account.username, res.password);
    if (res.revoked_tokens) toast(`Завершено сессий: ${res.revoked_tokens}`);
    done?.();
  } catch (e) { toastError(e); }
}

async function toggleAccount(acc, done) {
  if (acc.is_active && !(await confirmDialog("Деактивировать аккаунт?",
    `${acc.username} не сможет войти, его сессии будут завершены.`, { okText: "Деактивировать", danger: true }))) return;
  try {
    await api.patch(`/api/admin/accounts/${acc.id}`, { is_active: !acc.is_active });
    toast(acc.is_active ? "Аккаунт деактивирован" : "Аккаунт активирован", "ok");
    done?.();
  } catch (e) { toastError(e); }
}


function renderAccounts(content) {
  const tbody = h("tbody");
  const load = async () => {
    let items;
    try { items = await api.get("/api/admin/accounts"); } catch (e) { return toastError(e); }
    tbody.replaceChildren(...(items.length ? items.map((a) => h("tr", {},
      h("td", {}, h("b", { class: "mono" }, a.username)),
      h("td", {}, a.staff_name ? [a.staff_name, a.staff_deleted ? h("span", { class: "badge danger", style: { marginLeft: "6px" } }, "удалён") : null] : h("span", { class: "muted" }, "не связан")),
      h("td", {}, a.staff_role ? roleBadge(a.staff_role) : "—"),
      h("td", {}, h("span", { class: `badge ${a.is_active ? "ok" : "danger"}` }, a.is_active ? "да" : "нет")),
      h("td", {}, String(a.active_sessions)),
      h("td", { class: "muted" }, fmtDateTime(a.created_at)),
      h("td", { class: "muted" }, fmtDateTime(a.updated_at)),
      h("td", {}, h("div", { class: "row" },
        h("button", { class: "btn small", disabled: a.staff_deleted, onclick: () => resetPassword(a, load) }, "Новый пароль"),
        h("button", { class: "btn small", disabled: a.staff_deleted && !a.is_active, onclick: () => toggleAccount(a, load) },
          a.is_active ? "Деактивировать" : "Активировать"))),
    )) : [emptyRow(8, "Аккаунтов пока нет. Их создают в карточке медработника.")]));
  };
  content.append(
    h("div", { class: "toolbar" }, h("div", { class: "muted grow" },
      "Аккаунт создаётся в карточке медработника. Здесь — сброс пароля и активация."),
      h("button", { class: "btn", onclick: load }, "Обновить")),
    h("div", { class: "card table-wrap" }, h("table", { class: "grid" },
      h("thead", {}, h("tr", {}, ["Логин", "Медработник", "Роль", "Активен", "Сессий", "Создан", "Изменён", ""].map((t) => h("th", {}, t)))),
      tbody)));
  load();
}


function renderDiagnoses(content) {
  const tbody = h("tbody");
  const load = async () => {
    let items;
    try { items = await api.get("/api/diagnoses"); } catch (e) { return toastError(e); }
    tbody.replaceChildren(...(items.length ? items.map((d) => h("tr", {},
      h("td", {}, h("span", { class: "code-chip" }, d.code)),
      h("td", {}, d.name),
      h("td", { class: "muted" }, fmtDateTime(d.updated_at)),
      h("td", {}, h("div", { class: "row" },
        h("button", { class: "btn small ghost", title: "Изменить", onclick: () => editDiagnosis(d, load) }, icon("edit")),
        h("button", { class: "btn small ghost danger", title: "Удалить", onclick: async () => {
          if (!(await confirmDialog("Удалить диагноз?", `${d.code} «${d.name}»`, { okText: "Удалить", danger: true }))) return;
          try { await api.del(`/api/admin/diagnoses/${d.id}`); toast("Удалено", "ok"); load(); } catch (e) { toastError(e); }
        } }, icon("x")))),
    )) : [emptyRow(4, "Справочник пуст. Нажмите «Загрузить реестр».")]));
  };
  const loadBtn = h("button", { class: "btn", onclick: async () => {
    loadBtn.disabled = true;
    try {
      const r = await api.post("/api/admin/diagnoses/load");
      toast(`Реестр загружен: добавлено ${r.created}, обновлено ${r.updated}, пропущено ${r.skipped.length}`, "ok");
      r.skipped.forEach((s) => toast(s, "error"));
      load();
    } catch (e) { toastError(e); } finally { loadBtn.disabled = false; }
  } }, icon("book"), "Загрузить реестр");

  content.append(
    h("div", { class: "toolbar" }, h("div", { class: "grow" }), loadBtn,
      h("button", { class: "btn primary", onclick: () => editDiagnosis(null, load) }, icon("plus"), "Добавить")),
    h("div", { class: "card table-wrap" }, h("table", { class: "grid" },
      h("thead", {}, h("tr", {}, ["Код", "Наименование", "Изменён", ""].map((t) => h("th", {}, t)))), tbody)));
  load();
}

function editDiagnosis(d, done) {
  const inp = {
    code: h("input", { class: "input mono", value: d?.code ?? "", maxlength: "6", placeholder: "A00.00" }),
    name: h("input", { class: "input", value: d?.name ?? "", maxlength: "24" }),
  };
  const f = { code: field("Код (ровно 6 символов)", inp.code), name: field("Наименование (3–24 символа)", inp.name) };
  const save = h("button", { class: "btn primary", onclick: async () => {
    save.disabled = true;
    const body = { code: inp.code.value, name: inp.name.value };
    try {
      if (d) await api.put(`/api/admin/diagnoses/${d.id}`, body); else await api.post("/api/admin/diagnoses", body);
      m.close(); toast("Сохранено", "ok"); done();
    } catch (e) { applyErrors(f, e); } finally { save.disabled = false; }
  } }, "Сохранить");
  const m = modal({ title: d ? "Изменить диагноз" : "Новый диагноз", body: [f.code, f.name],
    actions: [h("button", { class: "btn", onclick: () => m.close() }, "Отмена"), save] });
}


const ACTION_KIND = {
  login_failed: "danger", access_denied: "danger", token_reuse_detected: "danger", admin_setup_failed: "danger",
  login: "ok", admin_login: "ok", logout: "",
};

function renderAudit(content) {
  const tbody = h("tbody");
  const filter = h("input", { class: "input", placeholder: "Фильтр: действие, субъект, текст" });
  const status = h("span", { class: "row muted" }, h("span", { class: "dot" }), "подключение…");
  const wrap = h("div", { class: "card table-wrap", style: { maxHeight: "calc(100vh - 150px)" } });
  let lastSeq = 0;
  let ws = null;
  let stopped = false;
  let retry = null;

  const setStatus = (live, text) => {
    status.replaceChildren(h("span", { class: `dot ${live ? "live" : "off"}` }), text);
  };
  const matches = (e) => {
    const q = filter.value.trim().toLowerCase();
    return !q || `${e.action} ${e.actor} ${e.actor_name ?? ""} ${e.message} ${e.source_ip ?? ""}`.toLowerCase().includes(q);
  };
  const row = (e, flash) => h("tr", { class: flash ? "flash" : "", "data-text": "" },
    h("td", { class: "muted", style: { whiteSpace: "nowrap" } }, fmtDateTime(e.event_time)),
    h("td", {}, h("span", { class: `badge ${ACTION_KIND[e.action] ?? "info"}` }, e.action)),
    h("td", {}, h("div", {}, e.actor_name ?? "—"), h("div", { class: "mono muted", style: { fontSize: "11px" } }, e.actor)),
    h("td", { class: "mono muted" }, e.source_ip ?? "—"),
    h("td", {}, e.message));
  const all = [];
  const append = (events, flash) => {
    const nearBottom = wrap.scrollHeight - wrap.scrollTop - wrap.clientHeight < 80;
    for (const e of events) {
      all.push(e);
      lastSeq = Math.max(lastSeq, e.seq);
      if (matches(e)) tbody.append(row(e, flash));
    }
    if (nearBottom || !flash) wrap.scrollTop = wrap.scrollHeight;
  };
  filter.addEventListener("input", () => {
    tbody.replaceChildren(...all.filter(matches).map((e) => row(e, false)));
  });

  const prevOnTokens = api.onTokens;
  api.onTokens = (token) => {
    prevOnTokens(token);
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "auth", token }));
  };

  const connect = async () => {
    if (stopped) return;
    if (!api.access || api.accessExp - Date.now() < 10_000) {
      try { await api.refresh(); } catch { return; }
    }
    ws = new WebSocket(`${WS_BASE}/api/ws/audit`);
    ws.onopen = () => ws.send(JSON.stringify({ token: api.access, after_seq: lastSeq }));
    ws.onmessage = (m) => {
      const msg = JSON.parse(m.data);
      if (msg.type === "ready") setStatus(true, "в реальном времени");
      if (msg.type === "events") append(msg.items, true);
    };
    ws.onclose = (ev) => {
      if (stopped) return;
      setStatus(false, ev.code === 4403 ? "нет доступа" : "переподключение…");
      if (ev.code === 4403) return;
      retry = setTimeout(connect, ev.code === 4401 ? 200 : 2000);
    };
  };

  content.append(
    h("div", { class: "toolbar" }, filter, h("div", { class: "grow" }), status),
    wrap);
  wrap.append(h("table", { class: "grid" },
    h("thead", {}, h("tr", {}, ["Время", "Действие", "Субъект", "IP", "Описание"].map((t) => h("th", {}, t)))),
    tbody));

  api.get("/api/admin/audit?limit=500").then((items) => { append(items, false); connect(); }).catch(toastError);

  return () => {
    stopped = true;
    clearTimeout(retry);
    api.onTokens = prevOnTokens;
    ws?.close();
  };
}

boot();
