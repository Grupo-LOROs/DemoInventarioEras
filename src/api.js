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

export async function authedFetch(path, opts={}) {
  const base = getApiBase();
  const token = getToken();
  const resp = await fetch(base + path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(opts.headers||{}),
      ...(token ? {'Authorization': 'Bearer ' + token} : {}),
    }
  });
  if(!resp.ok){
    const txt = await resp.text();
    throw new Error(`HTTP ${resp.status} ${resp.statusText} — ${txt.slice(0,240)}`);
  }
  return resp;
}

export function parseJwt(token) {
  try {
    const [, payload] = token.split('.');
    return JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
  } catch { return {}; }
}

export function getRole() {
  const t = getToken();
  if (!t) return 'user';
  const p = parseJwt(t);
  return p.role || p.roles?.[0] || 'user';
}

