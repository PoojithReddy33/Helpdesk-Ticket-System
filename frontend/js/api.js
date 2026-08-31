/**
 * The single place the frontend talks to Django.
 *
 * Everything else calls api.get/post/patch/del and never touches fetch(),
 * so token handling and error shaping live in one file.
 */

const API_BASE = "http://127.0.0.1:8000";

// Keys used in localStorage. Named constants so a typo becomes an error
// in one place rather than a silent "logged out" bug.
const ACCESS_KEY = "helpdesk_access";
const REFRESH_KEY = "helpdesk_refresh";
const USER_KEY = "helpdesk_user";

export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY);
  },
  get user() {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  },
  save({ access, refresh, user }) {
    if (access) localStorage.setItem(ACCESS_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clear() {
    [ACCESS_KEY, REFRESH_KEY, USER_KEY].forEach((k) =>
      localStorage.removeItem(k)
    );
  },
};

/** Thrown for any non-2xx response, carrying the parsed error body. */
export class ApiError extends Error {
  constructor(status, data) {
    super(`Request failed with ${status}`);
    this.status = status;
    this.data = data;
  }

  /** Turns DRF's {field: [messages]} shape into one readable line. */
  get readable() {
    if (!this.data) return this.message;
    if (typeof this.data === "string") return this.data;
    if (this.data.detail) return this.data.detail;

    return Object.entries(this.data)
      .map(([field, errors]) => {
        const text = Array.isArray(errors) ? errors.join(" ") : errors;
        return field === "non_field_errors" ? text : `${field}: ${text}`;
      })
      .join("\n");
  }
}

/** Exchanges the refresh token for a new access token. */
async function refreshAccessToken() {
  const refresh = tokens.refresh;
  if (!refresh) return false;

  const response = await fetch(`${API_BASE}/api/auth/token/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  });

  if (!response.ok) return false;

  tokens.save(await response.json());
  return true;
}

/**
 * One request. On a 401 it tries the refresh token once, then replays the
 * original call - so a 30-minute access token expiring is invisible.
 */
async function request(method, path, body = null, isRetry = false) {
  const headers = { "Content-Type": "application/json" };
  if (tokens.access) headers["Authorization"] = `Bearer ${tokens.access}`;

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : null,
  });

  if (response.status === 401 && !isRetry && tokens.refresh) {
    if (await refreshAccessToken()) {
      return request(method, path, body, true);
    }
    tokens.clear();
    window.location.href = "index.html";
    return null;
  }

  // 204 No Content has an empty body, so parsing it would throw.
  const data = response.status === 204 ? null : await response.json();

  if (!response.ok) throw new ApiError(response.status, data);
  return data;
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body),
  patch: (path, body) => request("PATCH", path, body),
  del: (path) => request("DELETE", path),
};

/** Login is special: it must not send an Authorization header. */
export async function login(email, password) {
  const response = await fetch(`${API_BASE}/api/auth/login/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  const data = await response.json();
  if (!response.ok) throw new ApiError(response.status, data);

  tokens.save(data);
  return data;
}

export async function register(payload) {
  const response = await fetch(`${API_BASE}/api/auth/register/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  if (!response.ok) throw new ApiError(response.status, data);
  return data;
}

export function logout() {
  tokens.clear();
  window.location.href = "index.html";
}

/** Sends anyone without a token back to the login page. */
export function requireAuth() {
  if (!tokens.access) {
    window.location.href = "index.html";
    return null;
  }
  return tokens.user;
}
