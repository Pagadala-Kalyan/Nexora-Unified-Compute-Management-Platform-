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

function redactSensitiveConnectionDetails(message) {
  return String(message)
    .replace(/\brtmps?:\/\/[^\s"'`<>]+/gi, '[destination server]')
    .replace(/\bnxt_live_[a-z0-9_-]+/gi, '[stream credential]')
    .replace(/((?:stream|destination)\s*key|password|credential|token)\s*[:=]\s*[^,\s;]+/gi, '$1=[redacted]');
}

function messageFromDetail(detail) {
  if (typeof detail === 'string') return detail.trim() === '[object Object]' ? '' : detail.trim();
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      if (typeof item === 'string') return item;
      if (!item || typeof item !== 'object') return '';
      // Pydantic validation items may include the submitted `input`; never
      // surface it because it could be a stream key or RTMP destination.
      return typeof item.msg === 'string' ? item.msg : typeof item.message === 'string' ? item.message : '';
    }).filter(Boolean).join('. ');
  }
  if (detail && typeof detail === 'object') {
    if (typeof detail.message === 'string') return detail.message.trim();
    if (typeof detail.msg === 'string') return detail.msg.trim();
  }
  return '';
}

/** Convert fetch/API errors into readable, non-sensitive text for the UI. */
export function getErrorMessage(error, fallback = 'Something went wrong. Please try again.') {
  if (typeof error === 'string') return redactSensitiveConnectionDetails(error.trim()) || fallback;

  const payload = error?.payload ?? error?.response?.data ?? error?.data;
  const detail = payload?.detail ?? error?.detail;
  const detailMessage = messageFromDetail(detail);
  const message = detailMessage || messageFromDetail(payload?.message) || messageFromDetail(payload?.error)
    || messageFromDetail(error?.message)
    || (typeof error?.message === 'string' && error.message !== '[object Object]' ? error.message.trim() : '');
  const status = Number(error?.status ?? error?.response?.status);

  if ((status === 402 || /insufficient token balance/i.test(message)) && /insufficient token balance/i.test(message)) {
    const info = detail && typeof detail === 'object' && !Array.isArray(detail) ? detail : payload;
    const required = Number(info?.required);
    const available = Number(info?.available);
    if (Number.isFinite(required) && Number.isFinite(available)) {
      return `Not enough tokens to start this stream. The minimum reserve is ${required} tokens; your balance is ${available} tokens. Add tokens in Wallet & Billing and try again.`;
    }
    return 'There are not enough tokens to start this stream. Add tokens in Wallet & Billing and try again.';
  }

  if (/no compatible online provider with ffmpeg/i.test(message)) {
    return 'No eligible online provider with FFmpeg is available for this stream. Connect a compatible provider and try again.';
  }
  if (/already have an active stream session/i.test(message)) {
    return 'You already have an active stream session. Stop it before starting another one.';
  }

  return message ? redactSensitiveConnectionDetails(message) : fallback;
}

function createApiError(message, status, payload) {
  const error = new Error(getErrorMessage({ message, status, payload }));
  error.status = status;
  error.payload = payload;
  return error;
}

/**
 * Universal API Request Wrapper
 */
export async function apiRequest(path, options = {}) {
  const token = getToken();
  const url = `${apiBase}${path.startsWith('/') ? path : '/' + path}`;
  
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  // Callers may provide either pre-serialized JSON strings or plain objects.
  // Fetch does not JSON-encode objects automatically; without this conversion
  // FastAPI receives an invalid body and responds with a JSON decode error.
  const requestBody = !isFormData && options.body && typeof options.body === 'object'
    ? JSON.stringify(options.body)
    : options.body;
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
      body: requestBody,
      headers,
      signal: controller.signal
    });
  } catch (err) {
    clearTimeout(timeoutId);
    console.error('[API Fetch Error]', path, err);
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
    
    let data = null;
    try {
      data = await response.json();
    } catch (_) {}
    throw createApiError('Authentication required or invalid session', response.status, data);
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
    const message = typeof data === 'string' && data.length > 0 ? data : 'Request failed';
    throw createApiError(message, response.status, data);
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

export async function getStreamSession(sessionId) {
  return apiRequest(`/stream/sessions/${encodeURIComponent(sessionId)}`);
}

export async function stopStreamSession(sessionId) {
  return apiRequest(`/stream/sessions/${encodeURIComponent(sessionId)}/stop`, {
    method: 'POST'
  });
}
