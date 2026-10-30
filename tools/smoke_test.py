import asyncio
import json
import ssl
import sys
import time
from pathlib import Path

import httpx
import pyotp
import websockets

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from server.settings import settings  # noqa: E402

API = f"https://localhost:{settings.api_port}"
CA = str(settings.ca_cert)
ADMIN_PASSWORD = "AdminPassw0rd!"

c = httpx.Client(base_url=API, verify=CA)
ok_count = 0


def check(cond, what):
    global ok_count
    if not cond:
        raise AssertionError(what)
    ok_count += 1
    print("  ok:", what)


def h(token):
    return {"Authorization": f"Bearer {token}"}


def wait_next_totp_window(secret, last_code):
    while pyotp.TOTP(secret).now() == last_code:
        time.sleep(1)
    return pyotp.TOTP(secret).now()


print("TLS")
try:
    httpx.get(API + "/api/health", verify=ssl.create_default_context()).raise_for_status()
    print("  (системное хранилище уже доверяет CA)")
except httpx.ConnectError:
    check(True, "без учебного CA соединение отклоняется")
ctx12 = ssl.create_default_context(cafile=CA)
ctx12.maximum_version = ssl.TLSVersion.TLSv1_2
try:
    httpx.get(API + "/api/health", verify=ctx12)
    check(False, "TLS 1.2 должен отклоняться")
except httpx.ConnectError:
    check(True, "TLS 1.2 отклоняется, принимается только 1.3")

print("Первичная настройка админа")
check(c.get("/api/auth/admin/status").json() == {"configured": False}, "админ не настроен")
r = c.post("/api/auth/admin/setup/begin", json={"password": "short", "password_confirm": "short"})
check(r.status_code == 422, "слабый пароль отклонён")
r = c.post("/api/auth/admin/setup/begin",
           json={"password": ADMIN_PASSWORD, "password_confirm": ADMIN_PASSWORD})
check(r.status_code == 200 and r.json()["qr_data_url"].startswith("data:image/svg"), "выдан QR")
setup = r.json()
r = c.post("/api/auth/admin/setup/complete", json={"setup_id": setup["setup_id"], "code": "000000"})
check(r.status_code == 401, "неверный код не завершает настройку")
code = pyotp.TOTP(setup["secret"]).now()
r = c.post("/api/auth/admin/setup/complete", json={"setup_id": setup["setup_id"], "code": code})
check(r.status_code == 200, "настройка завершена верным кодом")
admin = r.json()["access_token"]
check(c.post("/api/auth/admin/setup/begin", json={"password": ADMIN_PASSWORD,
              "password_confirm": ADMIN_PASSWORD}).status_code == 409, "повторная настройка запрещена")

r = c.post("/api/auth/admin/login", json={"password": ADMIN_PASSWORD, "code": code})
check(r.status_code == 401, "тот же TOTP-код повторно не принимается")
code = wait_next_totp_window(setup["secret"], code)
r = c.post("/api/auth/admin/login", json={"password": "wrong", "code": code})
check(r.status_code == 401, "неверный пароль админа")
r = c.post("/api/auth/admin/login", json={"password": ADMIN_PASSWORD, "code": code})
check(r.status_code == 200, "вход админа пароль + TOTP")
admin_pair = r.json()
admin = admin_pair["access_token"]

print("Справочник диагнозов")
r = c.post("/api/admin/diagnoses/load", headers=h(admin))
check(r.status_code == 200 and r.json()["created"] == 5, "загружено 5 диагнозов")
r = c.post("/api/admin/diagnoses", headers=h(admin), json={"code": "AB", "name": "X"})
check(r.status_code == 422, "валидация длины кода/наименования")
r = c.post("/api/admin/diagnoses", headers=h(admin), json={"code": "I10.00", "name": "Дубль"})
check(r.status_code == 409, "уникальность кода")
diags = c.get("/api/diagnoses", headers=h(admin)).json()

print("Медработники и аккаунты")
r = c.post("/api/admin/staff", headers=h(admin),
           json={"last_name": "Иванов", "first_name": "И", "position": "Терапевт"})
check(r.status_code == 201 and r.json()["role"] == "other", "медработник создан, роль other")
doc = r.json()
r = c.put(f"/api/admin/staff/{doc['id']}", headers=h(admin),
          json={"last_name": "Иванов", "first_name": "И", "position": "Терапевт", "role": "doctor"})
check(r.json()["role"] == "doctor", "роль изменена на doctor")
nurse = c.post("/api/admin/staff", headers=h(admin), json={
    "last_name": "Петрова", "first_name": "Анна", "position": "Медсестра", "role": "nurse"}).json()
lab = c.post("/api/admin/staff", headers=h(admin), json={
    "last_name": "Сидоров", "first_name": "Пётр", "position": "Лаборант",
    "role": "laboratory-technician"}).json()

r = c.post(f"/api/admin/staff/{doc['id']}/account", headers=h(admin), json={"username": "ivanov"})
check(r.status_code == 201 and len(r.json()["password"]) == 12, "аккаунт создан, пароль 12 симв.")
doc_acc, doc_pwd = r.json()["account"], r.json()["password"]
check(c.post(f"/api/admin/staff/{doc['id']}/account", headers=h(admin),
             json={"username": "ivanov2"}).status_code == 409, "второй аккаунт медработнику нельзя")
nurse_pwd = c.post(f"/api/admin/staff/{nurse['id']}/account", headers=h(admin),
                   json={"username": "petrova"}).json()["password"]
lab_pwd = c.post(f"/api/admin/staff/{lab['id']}/account", headers=h(admin),
                 json={"username": "sidorov"}).json()["password"]

print("Вход медработников и права")
check(c.post("/api/auth/login", json={"username": "ivanov", "password": "bad"}).status_code == 401,
      "неверный пароль")
doc_pair = c.post("/api/auth/login", json={"username": "ivanov", "password": doc_pwd}).json()
doc_t = doc_pair["access_token"]
check(doc_pair["me"]["role"] == "doctor", "роль в токене")
nurse_t = c.post("/api/auth/login", json={"username": "petrova", "password": nurse_pwd}).json()["access_token"]
lab_t = c.post("/api/auth/login", json={"username": "sidorov", "password": lab_pwd}).json()["access_token"]

check(c.get("/api/admin/staff", headers=h(doc_t)).status_code == 403, "врач не видит админку")
check(c.get("/api/patients", headers=h(admin)).status_code == 403, "админ не видит пациентов")
check(c.get("/api/patients").status_code == 401, "без токена 401")

pat_body = {"last_name": "Смирнов", "first_name": "Олег", "birth_date": "1980-05-01", "sex": "M"}
check(c.post("/api/patients", headers=h(lab_t), json=pat_body).status_code == 403,
      "лаборант не создаёт пациента")
r = c.post("/api/patients", headers=h(nurse_t), json=pat_body)
check(r.status_code == 201, "медсестра создаёт пациента")
pat = r.json()
check(c.post("/api/patients", headers=h(nurse_t), json={**pat_body, "birth_date": "2999-01-01"})
      .status_code == 422, "дата рождения в будущем отклонена")
r = c.post("/api/patients", headers=h(doc_t), json={**pat_body, "last_name": "Временный"})
check(c.delete(f"/api/patients/{r.json()['id']}", headers=h(doc_t)).status_code == 204,
      "пациент без ЭМК удаляется")

print("ЭМК")
r = c.post(f"/api/patients/{pat['id']}/emr", headers=h(nurse_t))
check(r.status_code == 201, "медсестра создаёт ЭМК")
emr = r.json()
check(c.post(f"/api/patients/{pat['id']}/emr", headers=h(doc_t)).status_code == 409, "вторая ЭМК нельзя")
check(c.delete(f"/api/patients/{pat['id']}", headers=h(doc_t)).status_code == 409,
      "пациента с ЭМК удалить нельзя")
check(c.get(f"/api/emrs/{emr['id']}", headers=h(lab_t)).status_code == 200, "лаборант читает ЭМК")
ops = {"base_version": emr["version"], "operations": [
    {"op": "add_diagnosis", "diagnosis_id": diags[0]["id"]},
    {"op": "add_prescription", "text": "Лизиноприл 10 мг утром"}]}
check(c.post(f"/api/emrs/{emr['id']}/changes", headers=h(nurse_t), json=ops).status_code == 403,
      "медсестра не редактирует ЭМК")
r = c.post(f"/api/emrs/{emr['id']}/changes", headers=h(doc_t), json=ops)
check(r.status_code == 200 and len(r.json()["diagnoses"]) == 1, "врач добавил диагноз и назначение")
s1 = r.json()
t_after_first = s1["prescriptions"][0]["added_at"]
check(c.post(f"/api/emrs/{emr['id']}/changes", headers=h(doc_t), json=ops).status_code == 409,
      "устаревшая версия отклонена (оптимистическая блокировка)")
time.sleep(0.05)
r = c.post(f"/api/emrs/{emr['id']}/changes", headers=h(doc_t), json={
    "base_version": s1["version"], "operations": [
        {"op": "edit_prescription", "entry_id": s1["prescriptions"][0]["id"],
         "text": "Лизиноприл 20 мг утром"},
        {"op": "remove_diagnosis", "entry_id": s1["diagnoses"][0]["id"]},
        {"op": "add_diagnosis", "diagnosis_id": diags[1]["id"]}]})
s2 = r.json()
check(s2["prescriptions"][0]["text"] == "Лизиноприл 20 мг утром"
      and s2["prescriptions"][0]["replaces_id"] == s1["prescriptions"][0]["id"], "назначение изменено")
past = c.get(f"/api/emrs/{emr['id']}", headers=h(doc_t), params={"at": t_after_first}).json()
check(past["prescriptions"][0]["text"] == "Лизиноприл 10 мг утром"
      and past["diagnoses"][0]["code"] == diags[0]["code"], "восстановлено состояние на момент времени")
hist = c.get(f"/api/emrs/{emr['id']}/history", headers=h(doc_t)).json()
check([x["action"] for x in hist] == ["emr_created", "diagnosis_added", "prescription_added",
                                       "prescription_edited", "diagnosis_removed", "diagnosis_added"],
      "история ЭМК полная")

print("Токены")
r = c.post("/api/auth/refresh", json={"refresh_token": doc_pair["refresh_token"]})
check(r.status_code == 200, "refresh выдаёт новую пару")
new_pair = r.json()
r = c.post("/api/auth/refresh", json={"refresh_token": doc_pair["refresh_token"]})
check(r.status_code == 401, "повторный refresh отклонён (обнаружено повторное использование)")
r = c.post("/api/auth/refresh", json={"refresh_token": new_pair["refresh_token"]})
check(r.status_code == 401, "после повторного использования отозвана вся цепочка")

lab_pair = c.post("/api/auth/login", json={"username": "sidorov", "password": lab_pwd}).json()
r = c.put(f"/api/admin/staff/{lab['id']}", headers=h(admin), json={
    "last_name": "Сидоров", "first_name": "Пётр", "position": "Лаборант", "role": "nurse"})
check(c.post("/api/auth/refresh", json={"refresh_token": lab_pair["refresh_token"]}).status_code == 401,
      "смена роли отзывает refresh-токены")
nurse_pair = c.post("/api/auth/login", json={"username": "petrova", "password": nurse_pwd}).json()
accs = {a["username"]: a for a in c.get("/api/admin/accounts", headers=h(admin)).json()}
r = c.patch(f"/api/admin/accounts/{accs['petrova']['id']}", headers=h(admin), json={"is_active": False})
check(r.json()["is_active"] is False, "аккаунт деактивирован")
check(c.post("/api/auth/login", json={"username": "petrova", "password": nurse_pwd}).status_code == 401,
      "деактивированный аккаунт не входит")
check(c.post("/api/auth/refresh", json={"refresh_token": nurse_pair["refresh_token"]}).status_code == 401,
      "деактивация отозвала refresh-токены")
r = c.post(f"/api/admin/accounts/{accs['ivanov']['id']}/reset-password", headers=h(admin))
check(r.status_code == 200 and r.json()["password"] != doc_pwd, "новый пароль сгенерирован")
check(c.post("/api/auth/login", json={"username": "ivanov", "password": doc_pwd}).status_code == 401,
      "старый пароль больше не работает")
c.delete(f"/api/admin/staff/{lab['id']}", headers=h(admin))
accs = {a["username"]: a for a in c.get("/api/admin/accounts", headers=h(admin)).json()}
check(accs["sidorov"]["is_active"] is False, "удаление медработника деактивирует аккаунт")

print("Аудит")
events = c.get("/api/admin/audit", headers=h(admin)).json()
actions = {e["action"] for e in events}
for a in ["admin_login", "login", "login_failed", "staff_created", "staff_updated", "staff_deleted",
          "patient_created", "patient_deleted", "emr_created", "emr_updated", "account_updated",
          "account_password_reset", "token_reuse_detected"]:
    check(a in actions, f"в аудите есть {a}")
revoke_msgs = [e["message"] for e in events if "отозвано" in e["message"]]
check(any("refresh-токенов: 2" in m and "деактивирован" in m for m in revoke_msgs),
      "в аудите указано число отозванных токенов (2 сессии медсестры)")
check(c.delete("/api/admin/audit/1", headers=h(admin)).status_code in (404, 405), "удалить аудит нельзя")


async def ws_check():
    ws_ctx = ssl.create_default_context(cafile=CA)
    url = f"wss://localhost:{settings.api_port}/api/ws/audit"
    async with websockets.connect(url, ssl=ws_ctx) as ws:
        await ws.send(json.dumps({"token": doc_t}))
        try:
            await asyncio.wait_for(ws.recv(), 3)
            check(False, "WS должен отклонить не-админа")
        except websockets.ConnectionClosed as e:
            check(e.rcvd.code == 4403, "WS аудита: не-админ получает 4403")
    async with websockets.connect(url, ssl=ws_ctx) as ws:
        await ws.send(json.dumps({"token": admin, "after_seq": events[-1]["seq"]}))
        check(json.loads(await ws.recv())["type"] == "ready", "WS аудита: админ подключён")
        t0 = time.monotonic()
        httpx.post(API + "/api/auth/login", json={"username": "nobody", "password": "x"}, verify=CA)
        msg = json.loads(await asyncio.wait_for(ws.recv(), 3))
        dt = time.monotonic() - t0
        check(msg["type"] == "events" and msg["items"][0]["action"] == "login_failed"
              and dt <= 2, f"новое событие пришло за {dt:.2f} с")

asyncio.run(ws_check())
print(f"\nВсе проверки пройдены: {ok_count}")
