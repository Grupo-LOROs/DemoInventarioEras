export const apiBaseKey = 'apiBase';
export const tokenKey = 'jwt';

export function getApiBase() {
  return localStorage.getItem(apiBaseKey) || 'http://127.0.0.1:8000';
}
export function setApiBase(url) {
  localStorage.setItem(apiBaseKey, url);
}
export function getToken() {
  return localStorage.getItem(tokenKey) || '';
}
export function setToken(t) {
  localStorage.setItem(tokenKey, t || '');
}

export async function authedFetch(path, opts = {}) {
  const base = getApiBase();
  const token = getToken();
  const resp = await fetch(base + path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(opts.headers || {}),
      ...(token ? { Authorization: 'Bearer ' + token } : {}),
    },
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`HTTP ${resp.status} ${resp.statusText} — ${txt.slice(0, 240)}`);
  }
  return resp;
}

/* --- Role helpers --- */
// Base64URL decode with padding + unicode safety
function b64urlDecode(str) {
  try {
    str = str.replace(/-/g, '+').replace(/_/g, '/');
    while (str.length % 4) str += '=';
    const decoded = atob(str);
    // try unicode decode
    try { return decodeURIComponent(decoded.split('').map(c => '%'+('00'+c.charCodeAt(0).toString(16)).slice(-2)).join('')); }
    catch { return decoded; }
  } catch { return '{}'; }
}
export function parseJwt(token) {
  try {
    const parts = token.split('.');
    if (parts.length < 2) return {};
    return JSON.parse(b64urlDecode(parts[1]) || '{}');
  } catch { return {}; }
}

/** Try JWT payload first; if missing, ask the API (/auth/me). */
export async function getRoleReliable() {
  const t = getToken();
  if (!t) return 'user';
  const p = parseJwt(t);
  if (p && (p.role || (p.roles && p.roles[0]))) {
    return p.role || p.roles[0];
  }
  try {
    const r = await authedFetch('/auth/me');
    const j = await r.json();
    return j.role || 'user';
  } catch {
    return 'user';
  }
}
