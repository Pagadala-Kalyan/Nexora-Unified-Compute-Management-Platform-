// ============================================================
// Nexora API / Control Plane
// ============================================================

// If the dashboard is running locally, it MUST use the local backend.
// This prevents an old Render URL saved in localStorage from taking
// priority over the local control plane.
//
// Local:
//   Frontend  -> http://127.0.0.1:5173
//   Backend   -> http://127.0.0.1:8000
//
// Hosted:
//   Frontend  -> Vercel / other host
//   Backend   -> Render
// ============================================================

const localHost =
  ['localhost', '127.0.0.1'].includes(window.location.hostname) ||
  window.location.port === '8000';

const localBase = 'http://127.0.0.1:8000';

const hostedBase =
  'https://nexora-unified-compute-management.onrender.com';

const fallbackBase =
  import.meta.env.VITE_API_URL ||
  (localHost ? localBase : hostedBase);

// Allow explicit control-plane override through URL.
// Example:
// http://localhost:5173/?controlPlane=http://127.0.0.1:8000
const sharedControlPlane =
  new URLSearchParams(window.location.search).get('controlPlane');

let base;

// ============================================================
// IMPORTANT:
// When running locally, ALWAYS use the local backend.
//
// This deliberately ignores a previously saved Render URL from
// localStorage. That was causing the frontend to talk to Render
// while the provider was connected to the local backend.
// ============================================================

if (localHost) {
  base = sharedControlPlane || localBase;

  // Keep localStorage synchronized with the backend actually used.
  localStorage.setItem('nexora_control_plane', base);
} else {
  // Hosted/Vercel application
  base =
    sharedControlPlane ||
    localStorage.getItem('nexora_control_plane') ||
    fallbackBase;

  if (sharedControlPlane) {
    localStorage.setItem('nexora_control_plane', base);
  }
}

// ============================================================
// Authentication token
// ============================================================

let token = localStorage.getItem('nexora_token');

export function setToken(v) {
  token = v;
  localStorage.setItem('nexora_token', v);
}

// ============================================================
// API request helper
// ============================================================

export async function api(path, options = {}) {
  let r;

  try {
    r = await fetch(base + path, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token
          ? {
              Authorization: `Bearer ${token}`,
            }
          : {}),
        ...(options.headers || {}),
      },
    });
  } catch {
    throw new Error(
      `Control plane is unavailable at ${base}. ` +
      `Start the local backend or check the hosted service.`
    );
  }

  const data = await r.json();

  if (!r.ok) {
    throw new Error(data.detail || 'Request failed');
  }

  return data;
}