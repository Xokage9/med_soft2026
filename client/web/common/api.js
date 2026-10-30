import { API_BASE } from "./config.js";

export class ApiError extends Error {
  constructor(status, detail, errors = []) {
    super(detail);
    this.status = status;
    this.errors = errors;
  }
}

export class Api {
  constructor(storageKey) {
    this.storageKey = storageKey;
    this.access = null;
    this.accessExp = 0;
    this.me = null;
    this.refreshing = null;
    this.timer = null;
    this.onLogout = () => {};
    this.onTokens = () => {};
  }

  get refreshToken() {
    try { return sessionStorage.getItem(this.storageKey); } catch { return null; }
  }
  set refreshToken(v) {
    try {
      if (v) sessionStorage.setItem(this.storageKey, v);
      else sessionStorage.removeItem(this.storageKey);
    } catch {}
  }

  setPair(pair) {
    this.access = pair.access_token;
    this.accessExp = Date.parse(pair.access_expires_at);
    this.refreshToken = pair.refresh_token;
    this.me = pair.me;
    clearTimeout(this.timer);
    const inMs = Math.max(5_000, this.accessExp - Date.now() - 30_000);
    this.timer = setTimeout(() => this.refresh().catch(() => {}), inMs);
    this.onTokens(this.access);
  }

  clear() {
    clearTimeout(this.timer);
    this.access = null;
    this.me = null;
    this.refreshToken = null;
  }

  async raw(method, path, body, token) {
    const headers = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers.Authorization = `Bearer ${token}`;
    let res;
    try {
      res = await fetch(API_BASE + path, {
        method, headers, body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError(0, "Нет связи с сервером API. Проверьте, что он запущен и сертификат CA установлен.");
    }
    const text = await res.text();
    const data = text ? JSON.parse(text) : null;
    if (!res.ok) {
      const detail = typeof data?.detail === "string" ? data.detail : `Ошибка ${res.status}`;
      throw new ApiError(res.status, detail, data?.errors || []);
    }
    return data;
  }

  refresh() {
    if (!this.refreshing) {
      this.refreshing = (async () => {
        const rt = this.refreshToken;
        if (!rt) throw new ApiError(401, "Нет активной сессии");
        try {
          const pair = await this.raw("POST", "/api/auth/refresh", { refresh_token: rt });
          this.setPair(pair);
          return pair;
        } catch (e) {
          if (e.status === 401) {
            this.clear();
            this.onLogout("Сессия завершена. Войдите снова.");
          }
          throw e;
        } finally {
          this.refreshing = null;
        }
      })();
    }
    return this.refreshing;
  }

  async request(method, path, body) {
    if (!this.access) await this.refresh();
    try {
      return await this.raw(method, path, body, this.access);
    } catch (e) {
      if (e.status !== 401) throw e;
      await this.refresh();
      return this.raw(method, path, body, this.access);
    }
  }

  get(path) { return this.request("GET", path); }
  post(path, body = {}) { return this.request("POST", path, body); }
  put(path, body) { return this.request("PUT", path, body); }
  patch(path, body) { return this.request("PATCH", path, body); }
  del(path) { return this.request("DELETE", path); }

  public(method, path, body) { return this.raw(method, path, body); }

  async restore() {
    if (!this.refreshToken) return false;
    try { await this.refresh(); return true; } catch { return false; }
  }

  async logout() {
    const rt = this.refreshToken;
    this.clear();
    if (rt) { try { await this.raw("POST", "/api/auth/logout", { refresh_token: rt }); } catch {} }
  }

  can(perm) { return !!this.me?.permissions?.includes(perm); }
}
