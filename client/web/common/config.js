export const API_PORT = 8443;
const secure = location.protocol === "https:";
export const API_BASE = `${secure ? "https" : "http"}://${location.hostname}:${API_PORT}`;
export const WS_BASE = `${secure ? "wss" : "ws"}://${location.hostname}:${API_PORT}`;
