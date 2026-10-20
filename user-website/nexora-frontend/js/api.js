/**
 * NEXORA UCMP — CONTROL PLANE API CLIENT
 * Handles base URL discovery, JWT auth headers, timeout aborts,
 * and automatic 401 session expiration without looping.
 */

const isLocalHost = ['localhost', '127.0.0.1'].includes(window.location.hostname);
const defaultLocalBase = 'http://127.0.0.1:8000';
const defaultHostedBase = 'https://nexora-unified-compute-management.onrender.com';

// URL override takes top priority: ?controlPlane=http://...
const urlOverride = new URLSearchParams(window.location.search).get('controlPlane');

let apiBase;
if (urlOverride) {
  apiBase = urlOverride.replace(/\/+$/, '');
  localStorage.setItem('nexora_control_plane', apiBase);
} else if (isLocalHost) {
  // If we are served from port 8000 directly, use relative path or 8000
  apiBase = window.location.port === '8000' ? '' : defaultLocalBase;
  localStorage.setItem('nexora_control_plane', apiBase);
} else {
  apiBase = localStorage.getItem('nexora_control_plane') || defaultHostedBase;
}

export function getApiBase() {
  return apiBase;
}

export function setApiBase(newBase) {
  apiBase = (newBase || '').replace(/\/+$/, '');
  localStorage.setItem('nexora_control_plane', apiBase);
}

export function getToken() {
  return localStorage.getItem('nexora_token') || null;
}

export function setToken(token) {
  if (token) {
    localStorage.setItem('nexora_token', token);
  } else {
    localStorage.removeItem('nexora_token');
  }
}

export function clearSession() {
  localStorage.removeItem('nexora_token');
  localStorage.removeItem('nexora_user');
}

/**
 * Universal API Request Wrapper
 */
export async function apiRequest(path, options = {}) {
  const token = getToken();
  const url = `${apiBase}${path.startsWith('/') ? path : '/' + path}`;
  
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  const headers = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    ...(options.headers || {})
  };

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), options.timeout || 15000);

  let response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal
    });
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === 'AbortError') {
      throw new Error(`Request timed out for endpoint ${path}`);
    }
    throw new Error(`Control plane unreachable at ${apiBase || window.location.origin}. Check backend status.`);
  } finally {
    clearTimeout(timeoutId);
  }

  // Handle Session Expiry (401)
  if (response.status === 401) {
    // Only fire session expiry event if we were making an authenticated call
    if (token && !path.includes('/auth/login') && !path.includes('/auth/register')) {
      clearSession();
      window.dispatchEvent(new CustomEvent('nexora:session-expired', {
        detail: { message: 'Your session has expired. Please sign in again.' }
      }));
    }
    
    let errorDetail = 'Authentication required or invalid session';
    try {
      const data = await response.json();
      errorDetail = data.detail || errorDetail;
    } catch (_) {}
    
    throw new Error(typeof errorDetail === 'string' ? errorDetail : JSON.stringify(errorDetail));
  }

  // Parse response
  let data;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch (parseErr) {
      data = { error: 'Invalid JSON response from server' };
    }
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    let message = 'Request failed';
    if (data && typeof data === 'object') {
      message = data.detail || data.message || JSON.stringify(data);
    } else if (typeof data === 'string' && data.length > 0) {
      message = data;
    }
    const err = new Error(message);
    err.status = response.status;
    err.payload = data;
    throw err;
  }

  return data;
}

export async function uploadArtifact(file) {
  const formData = new FormData();
  formData.append('file', file);
  return apiRequest('/media/artifacts/upload', {
    method: 'POST',
    body: formData,
    timeout: 120000 // 2 min timeout for video upload
  });
}

export async function createStreamSession(payload) {
  return apiRequest('/stream/sessions', {
    method: 'POST',
    body: payload
  });
}

export async function getActiveStreamSession() {
  return apiRequest('/stream/sessions/active');
}

export async function stopStreamSession(sessionId) {
  return apiRequest(`/stream/sessions/${encodeURIComponent(sessionId)}/stop`, {
    method: 'POST'
  });
}
