/** 与 kourichat.webui 插件的 JSON API 契约。 */

export const SECRET_MASK = "********";

export interface Account {
  accountId: string;
  userId: string;
  baseUrl?: string;
  status: "online" | "invalid" | "offline";
  savedAt?: number;
}

export interface LoginState {
  uid: string;
  qrcodeUrl: string;
  accountId?: string;
  userId?: string;
  status: "pending" | "success" | "failed";
  message?: string;
  refresh_count?: number;
  expireAt?: number;
}

export interface Status {
  connected: boolean;
  gateway_url: string;
  accounts: Account[];
  login: LoginState | null;
  needs_relogin: string[];
}

export interface LogRow {
  time: string;
  level: string;
  line: string;
}

export interface SettingsFields {
  core: { log_level: string };
  openclaw: {
    gateway_url: string;
    access_token: string;
    data_dir: string;
    autologin: boolean;
    poll_interval: number;
  };
  llm: { base_url: string; api_key: string; model: string; data_dir: string };
  webui: { host: string; port: number };
  persona: { personas_dir: string; enable: string };
  echo: { enabled: boolean };
}

export interface Dashboard {
  connected: boolean;
  accounts: Account[];
  login: LoginState | null;
  personas: { count: number; active: string | null };
  first_run: boolean;
}

export interface ApiError {
  ok?: boolean;
  error?: string;
}

interface AuthResponse {
  ok: boolean;
  token?: string;
}

function getToken(): string {
  try {
    return sessionStorage.getItem("kourichat.auth.token") || "";
  } catch {
    return "";
  }
}

function setToken(token: string): void {
  try {
    if (token) sessionStorage.setItem("kourichat.auth.token", token);
    else sessionStorage.removeItem("kourichat.auth.token");
  } catch {
    // Private browsing/storage-disabled browsers still get a usable request flow.
  }
}

function authExpired(): void {
  setToken("");
  window.dispatchEvent(new Event("kouri-auth-expired"));
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body !== undefined && init.body !== null) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(path, { ...init, headers });
  const data = (await res.json().catch(() => ({}))) as T & ApiError;
  if (res.status === 401) authExpired();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

export const api = {
  authStatus: () => req<{ ok: boolean; initialized: boolean; authenticated: boolean }>("/api/auth/status"),
  authSetup: async (username: string, password: string) => {
    const response = await req<AuthResponse>("/api/auth/setup", {
      method: "POST", body: JSON.stringify({ username, password }),
    });
    if (response.token) setToken(response.token);
    return response;
  },
  authLogin: async (username: string, password: string) => {
    const response = await req<AuthResponse>("/api/auth/login", {
      method: "POST", body: JSON.stringify({ username, password }),
    });
    if (response.token) setToken(response.token);
    return response;
  },
  authLogout: async () => {
    try {
      await req<{ ok: boolean }>("/api/auth/logout", { method: "POST", body: "{}" });
    } finally {
      setToken("");
      window.dispatchEvent(new Event("kouri-auth-expired"));
    }
  },
  status: () => req<Status>("/api/openclaw/status"),
  login: (accountId?: string) =>
    req<LoginState>("/api/openclaw/login", {
      method: "POST", body: JSON.stringify({ accountId: accountId || undefined }),
    }),
  loginRefresh: () =>
    req<LoginState>("/api/openclaw/login/refresh", {
      method: "POST", body: "{}",
    }),
  relogin: (accountId: string) =>
    req<LoginState>("/api/openclaw/relogin", {
      method: "POST", body: JSON.stringify({ accountId }),
    }),
  logout: (accountId: string) =>
    req<{ ok: boolean; note?: string }>("/api/openclaw/logout", {
      method: "POST", body: JSON.stringify({ accountId }),
    }),
  chatSend: (payload: { channel_id: string; channel_type: "private"; text: string }) =>
    req<{ ok: boolean; message_id: string }>("/api/chat/send", {
      method: "POST", body: JSON.stringify(payload),
    }),
  chatMock: (text: string, channelType: "private" = "private") =>
    req<{ ok: boolean }>("/api/chat/mock", {
      method: "POST", body: JSON.stringify({ text, channel_type: channelType }),
    }),
  logs: (limit = 200, level = "DEBUG", skip = 0) => {
    const query = new URLSearchParams({ limit: String(limit), level, skip: String(skip) });
    return req<{ logs: LogRow[] }>(`/api/logs?${query}`);
  },
  settingsGet: () => req<{ ok: boolean; fields: SettingsFields }>("/api/settings"),
  settingsSave: (fields: SettingsFields) =>
    req<{ ok: boolean; note?: string }>("/api/settings", {
      method: "POST", body: JSON.stringify({ fields }),
    }),
  setupStatus: () => req<{ ok: boolean; first_run: boolean }>("/api/setup/status"),
  dashboard: () => req<Dashboard>("/api/dashboard"),
  llmTest: (llm: SettingsFields["llm"]) =>
    req<{ ok: boolean; reply?: string; model?: string; note?: string; error?: string }>("/api/llm/test", {
      method: "POST", body: JSON.stringify({ llm }),
    }),
  llmReload: () =>
    req<{ ok: boolean; note?: string; error?: string }>("/api/llm/reload", {
      method: "POST", body: "{}",
    }),
};

/** 从本地 JWT 解析管理员用户名（`sub`）；解析失败返回空串。 */
export function authUsername(): string {
  try {
    const token = sessionStorage.getItem("kourichat.auth.token") || "";
    const payload = token.split(".")[1];
    if (!payload) return "";
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
    const bytes = Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
    const json = JSON.parse(new TextDecoder().decode(bytes)) as { sub?: unknown };
    return typeof json.sub === "string" ? json.sub : "";
  } catch {
    return "";
  }
}
