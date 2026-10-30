import { Api } from "../common/api.js";
import {
  SEX_LABEL, applyErrors, confirmDialog, field, fmtDate, fmtDateTime, h, icon, modal,
  roleBadge, select, toast, toastError,
} from "../common/ui.js";

const api = new Api("his.staff.refresh");
const root = document.getElementById("root");
api.onLogout = (msg) => { toast(msg, "error"); showLogin(); };

const P = {
  PATIENT_WRITE: "patient:write", EMR_CREATE: "emr:create", EMR_WRITE: "emr:write",
};


function showLogin() {
  const user = h("input", { class: "input", autocomplete: "username" });
  const pwd = h("input", { class: "input", type: "password", autocomplete: "current-password" });
  const err = h("div", { class: "callout hidden" });
  const btn = h("button", { class: "btn primary", type: "submit" }, "Войти");
  root.replaceChildren(h("div", { class: "auth-page" }, h("div", { class: "card auth-card" }, h("div", { class: "card-body" },
    h("div", { class: "auth-title" }, h("div", { class: "brand-mark" }, "+"),
      h("div", {}, h("h1", {}, "MedSoft HIS"), h("div", { class: "muted" }, "Рабочее место медработника"))),
    h("form", { class: "stack", onsubmit: async (e) => {
      e.preventDefault();
      btn.disabled = true; err.classList.add("hidden");
      try {
        api.setPair(await api.public("POST", "/api/auth/login", { username: user.value, password: pwd.value }));
        showApp();
      } catch (ex) { err.textContent = ex.message; err.classList.remove("hidden"); pwd.value = ""; }
      finally { btn.disabled = false; }
    } }, field("Логин", user), field("Пароль", pwd), err, btn,
    h("div", { class: "muted", style: { fontSize: "12px" } }, "Логин и пароль выдаёт администратор."))))));
  user.focus();
}


const state = { patients: [], selectedId: null, diagnoses: [] };
let listEl, detailEl, searchEl;

function showApp() {
  const me = api.me;
  searchEl = h("input", { class: "input", placeholder: "Поиск пациента по ФИО" });
  searchEl.addEventListener("input", debounce(loadPatients, 250));
  listEl = h("div", { class: "ws-list-items" });
  detailEl = h("section", { class: "ws-detail" });

  root.replaceChildren(h("div", { class: "main" },
    h("header", { class: "topbar" },
      h("div", { class: "brand-mark" }, "+"),
      h("div", { class: "grow" }, h("b", {}, "MedSoft HIS"), h("span", { class: "muted" }, " · медработник")),
      h("div", { class: "row" }, icon("user"), h("span", {}, me.name), roleBadge(me.role)),
      h("button", { class: "btn ghost", onclick: async () => { await api.logout(); showLogin(); } }, icon("logout"), "Выйти")),
    h("div", { class: "ws" },
      h("aside", { class: "ws-list" },
        h("div", { class: "ws-list-head" },
          h("div", { class: "row" }, h("h2", { class: "grow" }, "Пациенты"),
            h("button", { class: "btn small primary", disabled: !api.can(P.PATIENT_WRITE),
              title: api.can(P.PATIENT_WRITE) ? "" : "Только врач или медсестра",
              onclick: () => editPatient(null) }, icon("plus"), "Новый")),
          searchEl),
        listEl),
      detailEl)));
  renderEmptyDetail();
  loadPatients();
  api.get("/api/diagnoses").then((d) => { state.diagnoses = d; }).catch(() => {});
}

function renderEmptyDetail() {
  detailEl.replaceChildren(h("div", { class: "empty-state" }, icon("users"),
    h("div", {}, "Выберите пациента слева")));
}

async function loadPatients() {
  try {
    const q = searchEl.value.trim();
    state.patients = await api.get(`/api/patients${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  } catch (e) { return toastError(e); }
  drawList();
}

function initials(p) { return `${p.last_name[0] ?? ""}${p.first_name[0] ?? ""}`.toUpperCase(); }
function fio(p) { return [p.last_name, p.first_name, p.middle_name].filter(Boolean).join(" "); }
function age(birth) {
  const b = new Date(birth + "T00:00:00"); const n = new Date();
  let a = n.getFullYear() - b.getFullYear();
  if (n.getMonth() < b.getMonth() || (n.getMonth() === b.getMonth() && n.getDate() < b.getDate())) a--;
  return a;
}

function drawList() {
  if (!state.patients.length) {
    listEl.replaceChildren(h("div", { class: "empty" }, "Пациентов не найдено"));
    return;
  }
  listEl.replaceChildren(...state.patients.map((p) => h("div", {
    class: `patient-item${p.id === state.selectedId ? " active" : ""}`,
    onclick: () => selectPatient(p.id),
  }, h("div", { class: "avatar" }, initials(p)),
  h("div", { class: "grow" }, h("div", {}, h("b", {}, fio(p))),
    h("div", { class: "muted", style: { fontSize: "12px" } }, `${fmtDate(p.birth_date)} · ${age(p.birth_date)} лет · ${SEX_LABEL[p.sex]}`)),
  p.emr_id ? h("span", { class: "badge accent", title: "Есть ЭМК" }, "ЭМК") : null)));
}


async function selectPatient(id) {
  if (emrEditor?.dirty() && !(await confirmDialog("Несохранённые изменения",
    "В ЭМК есть несохранённые изменения. Уйти без сохранения?", { okText: "Уйти", danger: true }))) return;
  emrEditor = null;
  state.selectedId = id;
  drawList();
  let p;
  try { p = await api.get(`/api/patients/${id}`); } catch (e) { return toastError(e); }
  const canWrite = api.can(P.PATIENT_WRITE);

  const emrBox = h("div", {});
  detailEl.replaceChildren(
    h("div", { class: "card" },
      h("div", { class: "card-head" }, h("div", { class: "avatar" }, initials(p)),
        h("div", { class: "grow" }, h("h1", {}, fio(p))),
        h("button", { class: "btn small", disabled: !canWrite, onclick: () => editPatient(p) }, icon("edit"), "Изменить"),
        h("button", {
          class: "btn small danger", disabled: !canWrite || !!p.emr_id,
          title: p.emr_id ? "Пациента с ЭМК удалить нельзя" : "",
          onclick: () => deletePatient(p),
        }, "Удалить")),
      h("div", { class: "card-body kv" },
        kv("Дата рождения", `${fmtDate(p.birth_date)} (${age(p.birth_date)} лет)`),
        kv("Пол", SEX_LABEL[p.sex]),
        kv("Комментарий", p.comment || "—"),
        kv("В системе с", fmtDateTime(p.created_at)))),
    emrBox);
  renderEmr(emrBox, p);
}

function kv(label, value) { return h("div", {}, h("span", {}, label), value); }

function editPatient(p) {
  const inp = {
    last_name: h("input", { class: "input", value: p?.last_name ?? "" }),
    first_name: h("input", { class: "input", value: p?.first_name ?? "" }),
    middle_name: h("input", { class: "input", value: p?.middle_name ?? "", placeholder: "при наличии" }),
    birth_date: h("input", { class: "input", type: "date", value: p?.birth_date ?? "", max: new Date().toISOString().slice(0, 10) }),
    sex: select(Object.entries(SEX_LABEL), p?.sex ?? "U"),
    comment: h("input", { class: "input", value: p?.comment ?? "", maxlength: "32" }),
  };
  const f = {
    last_name: field("Фамилия", inp.last_name), first_name: field("Имя", inp.first_name),
    middle_name: field("Отчество", inp.middle_name), birth_date: field("Дата рождения", inp.birth_date),
    sex: field("Административный пол", inp.sex), comment: field("Комментарий (до 32 символов)", inp.comment),
  };
  const save = h("button", { class: "btn primary", onclick: async () => {
    const body = Object.fromEntries(Object.entries(inp).map(([k, el]) => [k, el.value]));
    if (!body.birth_date) return f.birth_date.setError("Укажите дату рождения");
    save.disabled = true;
    try {
      const saved = p ? await api.put(`/api/patients/${p.id}`, body) : await api.post("/api/patients", body);
      m.close(); toast("Сохранено", "ok");
      await loadPatients(); selectPatient(saved.id);
    } catch (e) { applyErrors(f, e); } finally { save.disabled = false; }
  } }, "Сохранить");
  const m = modal({
    title: p ? "Данные пациента" : "Новый пациент",
    body: h("div", { class: "form-grid" }, f.last_name, f.first_name, f.middle_name, f.birth_date, f.sex, f.comment),
    actions: [h("button", { class: "btn", onclick: () => m.close() }, "Отмена"), save],
  });
}

async function deletePatient(p) {
  if (!(await confirmDialog("Удалить пациента?", `${fio(p)} будет удалён из базы безвозвратно.`,
    { okText: "Удалить", danger: true }))) return;
  try {
    await api.del(`/api/patients/${p.id}`);
    toast("Пациент удалён", "ok");
    state.selectedId = null; renderEmptyDetail(); loadPatients();
  } catch (e) { toastError(e); }
}


let emrEditor = null;

async function renderEmr(box, patient) {
  if (!patient.emr_id) {
    const can = api.can(P.EMR_CREATE);
    box.replaceChildren(h("div", { class: "card" }, h("div", { class: "empty-state" }, icon("file"),
      h("div", {}, "У пациента нет электронной медицинской карты"),
      h("button", { class: "btn primary", disabled: !can, title: can ? "" : "Только врач или медсестра",
        onclick: async () => {
          try {
            await api.post(`/api/patients/${patient.id}/emr`);
            toast("ЭМК создана", "ok"); await loadPatients(); selectPatient(patient.id);
          } catch (e) { toastError(e); }
        } }, icon("plus"), "Создать ЭМК"))));
    return;
  }

  const body = h("div", {});
  const tabs = [["current", "Текущее состояние"], ["history", "История изменений"]];
  const tabBar = h("div", { class: "tabs" });
  const show = async (key) => {
    if (key !== "current" && emrEditor?.dirty() && !(await confirmDialog("Несохранённые изменения",
      "Изменения ЭМК не сохранены. Отменить их?", { okText: "Отменить изменения", danger: true }))) return;
    tabBar.replaceChildren(...tabs.map(([k, t]) => h("button", { class: `tab${k === key ? " active" : ""}`, onclick: () => show(k) }, t)));
    body.replaceChildren();
    if (key === "current") { emrEditor = new EmrEditor(body, patient.emr_id); emrEditor.load(); }
    else { emrEditor = null; renderHistory(body, patient.emr_id); }
  };
  box.replaceChildren(h("div", { class: "card" },
    h("div", { class: "card-head" }, icon("file"), h("h2", { class: "grow" }, "Электронная медицинская карта")),
    tabBar, body));
  show("current");
}

class EmrEditor {
  constructor(box, emrId) {
    this.box = box; this.emrId = emrId; this.emr = null; this.unlocked = false;
    this.reset();
  }

  reset() {
    this.removedDiag = new Set();
    this.addedDiag = [];
    this.cancelledPresc = new Set();
    this.editedPresc = new Map();
    this.addedPresc = [];
  }

  dirty() {
    return this.unlocked && (this.removedDiag.size || this.addedDiag.length || this.cancelledPresc.size
      || this.editedPresc.size || this.addedPresc.length) > 0;
  }

  async load() {
    try { this.emr = await api.get(`/api/emrs/${this.emrId}`); } catch (e) { return toastError(e); }
    this.draw();
  }

  operations() {
    const ops = [];
    this.removedDiag.forEach((id) => ops.push({ op: "remove_diagnosis", entry_id: id }));
    this.addedDiag.forEach((d) => ops.push({ op: "add_diagnosis", diagnosis_id: d.id }));
    this.cancelledPresc.forEach((id) => ops.push({ op: "cancel_prescription", entry_id: id }));
    this.editedPresc.forEach((text, id) => ops.push({ op: "edit_prescription", entry_id: id, text }));
    this.addedPresc.forEach((text) => ops.push({ op: "add_prescription", text }));
    return ops;
  }

  async save(btn) {
    const ops = this.operations();
    if (!ops.length) { this.unlocked = false; return this.draw(); }
    btn.disabled = true;
    try {
      this.emr = await api.post(`/api/emrs/${this.emrId}/changes`, { base_version: this.emr.version, operations: ops });
      toast("ЭМК сохранена", "ok");
      this.unlocked = false; this.reset(); this.draw();
    } catch (e) {
      toastError(e);
      if (e.status === 409) { this.reset(); this.unlocked = false; this.load(); }
    } finally { btn.disabled = false; }
  }

  draw() {
    const emr = this.emr;
    const canWrite = api.can(P.EMR_WRITE);
    const me = api.me;

    const lockbar = this.unlocked
      ? h("div", { class: "lockbar unlocked" }, icon("unlock"),
        h("div", { class: "grow" }, h("b", {}, "Режим редактирования"),
          h("span", { class: "muted" }, ` · вносит изменения: ${me.name}`)),
        h("button", { class: "btn small", onclick: async () => {
          if (this.dirty() && !(await confirmDialog("Отменить изменения?", "Несохранённые изменения будут потеряны.",
            { okText: "Отменить изменения", danger: true }))) return;
          this.unlocked = false; this.reset(); this.draw();
        } }, "Отмена"),
        (() => { const b = h("button", { class: "btn small primary", onclick: () => this.save(b) }, "Сохранить"); return b; })())
      : h("div", { class: "lockbar" }, icon("lock"),
        h("div", { class: "grow" }, h("b", {}, "Карта заблокирована"),
          h("span", { class: "muted" }, ` · версия ${emr.version} · создана ${fmtDateTime(emr.created_at)} (${emr.created_by})`)),
        h("button", { class: "btn small", disabled: !canWrite, title: canWrite ? "" : "Разблокировать может только врач",
          onclick: () => { this.unlocked = true; this.draw(); } }, icon("unlock"), "Разблокировать"));

    this.box.replaceChildren(lockbar, this.diagSection(), this.prescSection());
  }

  diagSection() {
    const edit = this.unlocked;
    const items = this.emr.diagnoses.map((d) => {
      const removed = this.removedDiag.has(d.id);
      return h("div", { class: `entry${removed ? " removed" : ""}` },
        h("span", { class: "code-chip" }, d.code),
        h("div", { class: "entry-main" }, h("div", {}, d.name),
          h("div", { class: "meta" }, `${fmtDateTime(d.added_at)} · ${d.added_by}`)),
        edit ? h("button", { class: "btn small ghost", title: removed ? "Вернуть" : "Удалить диагноз",
          onclick: () => { removed ? this.removedDiag.delete(d.id) : this.removedDiag.add(d.id); this.draw(); } },
        icon(removed ? "undo" : "x")) : null);
    });
    this.addedDiag.forEach((d, i) => items.push(h("div", { class: "entry new" },
      h("span", { class: "code-chip" }, d.code), h("div", { class: "entry-main" }, d.name, h("div", { class: "meta" }, "будет добавлен")),
      h("button", { class: "btn small ghost", onclick: () => { this.addedDiag.splice(i, 1); this.draw(); } }, icon("x")))));

    let adder = null;
    if (edit) {
      const used = new Set([...this.emr.diagnoses.filter((d) => !this.removedDiag.has(d.id)).map((d) => d.diagnosis_id),
        ...this.addedDiag.map((d) => d.id)]);
      const options = state.diagnoses.filter((d) => !used.has(d.id));
      const sel = select([["", options.length ? "Выберите диагноз…" : "Все диагнозы справочника уже добавлены"],
        ...options.map((d) => [d.id, `${d.code} — ${d.name}`])], "");
      adder = h("div", { class: "row" }, sel, h("button", { class: "btn", onclick: () => {
        const d = state.diagnoses.find((x) => x.id === sel.value);
        if (d) { this.addedDiag.push(d); this.draw(); }
      } }, icon("plus"), "Добавить"));
    }
    return h("div", { class: "emr-section" }, h("div", { class: "section-title" }, "Диагнозы"),
      items.length ? items : h("div", { class: "muted" }, "Диагнозов нет"), adder);
  }

  prescSection() {
    const edit = this.unlocked;
    const items = this.emr.prescriptions.map((p) => {
      const cancelled = this.cancelledPresc.has(p.id);
      const edited = this.editedPresc.get(p.id);
      const cls = cancelled ? " removed" : edited !== undefined ? " edited" : "";
      return h("div", { class: `entry${cls}` },
        h("div", { class: "entry-main" }, h("div", {}, edited ?? p.text),
          h("div", { class: "meta" }, edited !== undefined ? `было: ${p.text}`
            : `${fmtDateTime(p.added_at)} · ${p.added_by}${p.replaces_id ? " · изменено" : ""}`)),
        edit && !cancelled ? h("button", { class: "btn small ghost", title: "Изменить",
          onclick: () => this.editPrescDialog(edited ?? p.text, (t) => {
            t === p.text ? this.editedPresc.delete(p.id) : this.editedPresc.set(p.id, t); this.draw();
          }) }, icon("edit")) : null,
        edit ? h("button", { class: "btn small ghost", title: cancelled ? "Вернуть" : "Отменить назначение",
          onclick: () => {
            if (cancelled) this.cancelledPresc.delete(p.id);
            else { this.cancelledPresc.add(p.id); this.editedPresc.delete(p.id); }
            this.draw();
          } }, icon(cancelled ? "undo" : "x")) : null);
    });
    this.addedPresc.forEach((t, i) => items.push(h("div", { class: "entry new" },
      h("div", { class: "entry-main" }, t, h("div", { class: "meta" }, "будет добавлено")),
      h("button", { class: "btn small ghost", onclick: () => this.editPrescDialog(t, (nt) => { this.addedPresc[i] = nt; this.draw(); }) }, icon("edit")),
      h("button", { class: "btn small ghost", onclick: () => { this.addedPresc.splice(i, 1); this.draw(); } }, icon("x")))));

    let adder = null;
    if (edit) {
      const ta = h("textarea", { class: "input", rows: "2", maxlength: "128", placeholder: "Новое назначение (3–128 символов)" });
      const counter = h("span", { class: "muted", style: { fontSize: "12px" } }, "0/128");
      ta.addEventListener("input", () => { counter.textContent = `${ta.value.length}/128`; });
      adder = h("div", { class: "stack", style: { gap: "6px" } }, ta, h("div", { class: "row" }, counter, h("div", { class: "grow" }),
        h("button", { class: "btn", onclick: () => {
          const t = ta.value.trim();
          if (t.length < 3 || t.length > 128) return toast("Назначение: от 3 до 128 символов", "error");
          this.addedPresc.push(t); this.draw();
        } }, icon("plus"), "Добавить назначение")));
    }
    return h("div", { class: "emr-section" }, h("div", { class: "section-title" }, "Назначения"),
      items.length ? items : h("div", { class: "muted" }, "Назначений нет"), adder);
  }

  editPrescDialog(text, onOk) {
    const ta = h("textarea", { class: "input", rows: "3", maxlength: "128", value: text });
    const f = field("Текст назначения (3–128 символов)", ta);
    const m = modal({ title: "Изменить назначение", body: [f,
      h("div", { class: "callout info" }, "При сохранении старое назначение будет отменено, а новое добавлено — оба шага попадут в историю.")],
    actions: [h("button", { class: "btn", onclick: () => m.close() }, "Отмена"),
      h("button", { class: "btn primary", onclick: () => {
        const t = ta.value.trim();
        if (t.length < 3 || t.length > 128) return f.setError("От 3 до 128 символов");
        m.close(); onOk(t);
      } }, "Применить")] });
  }
}


const HISTORY_LABEL = {
  emr_created: ["ЭМК создана", "accent"],
  diagnosis_added: ["Добавлен диагноз", "ok"],
  diagnosis_removed: ["Удалён диагноз", "danger"],
  prescription_added: ["Добавлено назначение", "ok"],
  prescription_cancelled: ["Отменено назначение", "danger"],
  prescription_edited: ["Изменено назначение", "warn"],
};

function historyDetails(e) {
  const p = e.payload;
  switch (e.action) {
    case "diagnosis_added": case "diagnosis_removed": return [h("span", { class: "code-chip" }, p.code), " ", p.name];
    case "prescription_added": case "prescription_cancelled": return p.text;
    case "prescription_edited": return [h("div", { class: "muted", style: { textDecoration: "line-through" } }, p.old_text), h("div", {}, p.text)];
    default: return "";
  }
}

async function renderHistory(box, emrId) {
  let items;
  try { items = await api.get(`/api/emrs/${emrId}/history`); } catch (e) { return toastError(e); }
  const snapshot = h("div", {});
  const atInput = h("input", { class: "input", type: "datetime-local", step: "1", style: { width: "240px" } });
  const list = h("div", { class: "timeline" });

  const showAt = async (iso, label) => {
    let s;
    try { s = await api.get(`/api/emrs/${emrId}?at=${encodeURIComponent(iso)}`); } catch (e) { return toastError(e); }
    snapshot.replaceChildren(h("div", { class: "emr-section", style: { background: "var(--surface-2)" } },
      h("div", { class: "row" }, icon("clock"), h("b", { class: "grow" }, `Состояние ЭМК ${label}`),
        h("button", { class: "btn small ghost", onclick: () => { snapshot.replaceChildren(); list.querySelectorAll(".selected").forEach((x) => x.classList.remove("selected")); } }, icon("x"))),
      h("div", { class: "section-title", style: { marginTop: "8px" } }, "Диагнозы"),
      s.diagnoses.length ? s.diagnoses.map((d) => h("div", { class: "entry" }, h("span", { class: "code-chip" }, d.code), h("div", { class: "entry-main" }, d.name))) : h("div", { class: "muted" }, "нет"),
      h("div", { class: "section-title", style: { marginTop: "8px" } }, "Назначения"),
      s.prescriptions.length ? s.prescriptions.map((p) => h("div", { class: "entry" }, h("div", { class: "entry-main" }, p.text))) : h("div", { class: "muted" }, "нет")));
  };

  list.replaceChildren(...items.slice().reverse().map((e) => {
    const [label, kind] = HISTORY_LABEL[e.action] || [e.action, ""];
    const row = h("div", { class: "tl-item" },
      h("div", {}, h("div", {}, fmtDateTime(e.at)), h("div", { class: "muted", style: { fontSize: "12px" } }, e.staff_name)),
      h("div", {}, h("span", { class: `badge ${kind}` }, label), h("div", { style: { marginTop: "4px" } }, historyDetails(e))),
      h("button", { class: "btn small", title: "Показать состояние ЭМК сразу после этого действия", onclick: () => {
        list.querySelectorAll(".selected").forEach((x) => x.classList.remove("selected"));
        row.classList.add("selected");
        showAt(e.at, `после действия ${fmtDateTime(e.at)}`);
      } }, "Состояние"));
    return row;
  }));

  box.replaceChildren(
    h("div", { class: "lockbar" }, icon("clock"), h("span", { class: "grow" }, "Восстановить состояние на момент:"), atInput,
      h("button", { class: "btn small", onclick: () => {
        if (!atInput.value) return toast("Укажите дату и время", "error");
        const d = new Date(atInput.value);
        showAt(d.toISOString(), `на ${fmtDateTime(d.toISOString())}`);
      } }, "Показать")),
    snapshot, list);
}

function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

window.addEventListener("beforeunload", (e) => { if (emrEditor?.dirty()) e.preventDefault(); });

(async () => { if (await api.restore()) showApp(); else showLogin(); })();
