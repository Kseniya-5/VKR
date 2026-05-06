// nginx/assets/js/app.js

const API_BASE_URL = `${window.location.origin}/api`;

export function getAccessToken() {
  return localStorage.getItem('access_token');
}

export function setAccessToken(token) {
  if (token) {
    localStorage.setItem('access_token', token);
  } else {
    localStorage.removeItem('access_token');
  }
}

export function logout() {
  setAccessToken(null);
  window.location.href = '/';
}

export async function apiFetch(path, options = {}) {
  const token = getAccessToken();
  const headers = new Headers(options.headers || {});

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const resp = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (resp.status === 401) {
    setAccessToken(null);
  }

  return resp;
}

export async function fetchCurrentUser() {
  const resp = await apiFetch('/users/me', { method: 'GET' });
  if (!resp.ok) return null;
  return await resp.json();
}

export async function loadProtectedImage(path) {
  const resp = await apiFetch(path, { method: 'GET' });
  if (!resp.ok) {
    throw new Error(`Failed to load protected image: ${resp.status}`);
  }
  const blob = await resp.blob();
  return URL.createObjectURL(blob);
}
