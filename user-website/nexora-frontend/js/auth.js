/**
 * NEXORA UCMP — AUTHENTICATION SERVICE
 * Manages user credentials, JWT sessions, and the Auth Modal.
 * Guaranteed: Public landing page is visible to all; modal can be closed anytime.
 */

import { apiRequest, setToken, clearSession, getToken } from './api.js';

let currentUser = null;

try {
  const saved = localStorage.getItem('nexora_user');
  if (saved) currentUser = JSON.parse(saved);
} catch (e) {
  currentUser = null;
}

export function getCurrentUser() {
  return currentUser;
}

export function setCurrentUser(user) {
  currentUser = user;
  if (user) {
    localStorage.setItem('nexora_user', JSON.stringify(user));
  } else {
    localStorage.removeItem('nexora_user');
  }
}

export function isAuthenticated() {
  return Boolean(getToken() && currentUser);
}

export async function login(email, password) {
  const res = await apiRequest('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email: email.trim().toLowerCase(), password })
  });
  
  if (res.access_token) {
    setToken(res.access_token);
    setCurrentUser(res.user);
    window.dispatchEvent(new CustomEvent('nexora:auth-changed', { detail: { user: res.user } }));
    return res.user;
  }
  throw new Error('No access token returned by server');
}

export async function register(email, password) {
  const res = await apiRequest('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email: email.trim().toLowerCase(), password })
  });
  
  if (res.access_token) {
    setToken(res.access_token);
    setCurrentUser(res.user);
    window.dispatchEvent(new CustomEvent('nexora:auth-changed', { detail: { user: res.user } }));
    return res.user;
  }
  throw new Error('Registration succeeded but token was not returned');
}

export function logout() {
  clearSession();
  currentUser = null;
  window.dispatchEvent(new CustomEvent('nexora:auth-changed', { detail: { user: null } }));
}

/**
 * Close the Authentication Modal
 */
export function closeAuthModal() {
  const modalWrap = document.getElementById('auth-modal-wrap');
  if (modalWrap) {
    modalWrap.innerHTML = '';
  }
}

/**
 * Render the dedicated Authentication Modal (Login / Register Tabs)
 * Can be dismissed at any time so the public landing page is always accessible.
 */
export function openAuthModal(mode = 'login') {
  let modalWrap = document.getElementById('auth-modal-wrap');
  if (!modalWrap) {
    modalWrap = document.createElement('div');
    modalWrap.id = 'auth-modal-wrap';
    document.body.appendChild(modalWrap);
  }

  modalWrap.innerHTML = `
    <div class="modal-backdrop active" id="auth-backdrop">
      <div class="modal-box" style="max-width: 440px;" role="dialog" aria-modal="true" aria-labelledby="auth-modal-title">
        <div class="modal-header">
          <div style="display: flex; align-items: center; gap: 8px;">
            <div style="width: 28px; height: 28px; border-radius: 6px; background: var(--accent-cyan-soft); display: flex; align-items: center; justify-content: center; color: var(--accent-cyan);">
              <svg width="18" height="18" viewBox="0 0 32 32" fill="none"><path d="M16 2L28.1244 8.99999V23L16 30L3.87564 23V8.99999L16 2Z" stroke="currentColor" stroke-width="2.5"/><circle cx="16" cy="16" r="4" fill="currentColor"/></svg>
            </div>
            <div>
              <div class="modal-title" id="auth-modal-title" style="font-size: var(--text-md);">Nexora Control Plane</div>
              <div style="font-size: var(--text-2xs); color: var(--text-muted); font-family: var(--font-mono);">SECURE CONSOLE ACCESS</div>
            </div>
          </div>
          <!-- Close button is ALWAYS visible and accessible -->
          <button class="modal-close-btn" id="auth-close-btn" aria-label="Close" title="Close [Esc]">&times;</button>
        </div>

        <div class="modal-body" style="padding: var(--space-5);">
          <div class="tab-list" style="margin-bottom: var(--space-4);">
            <button class="tab-btn ${mode === 'login' ? 'active' : ''}" id="tab-login-btn">Sign In</button>
            <button class="tab-btn ${mode === 'register' ? 'active' : ''}" id="tab-register-btn">Create Account</button>
          </div>
          
          <form id="auth-form">
            <div id="auth-error-msg" style="display: none; padding: 8px 12px; margin-bottom: 12px; border-radius: 6px; background: var(--status-error-soft); border: 1px solid var(--status-error); color: var(--status-error); font-size: var(--text-xs);"></div>

            <div class="form-group">
              <label class="form-label" for="auth-email">Email Address</label>
              <input type="email" id="auth-email" class="input" placeholder="developer@organization.io" required autocomplete="email" />
            </div>

            <div class="form-group">
              <label class="form-label" for="auth-password">Password</label>
              <input type="password" id="auth-password" class="input" placeholder="••••••••••••" required autocomplete="current-password" minlength="${mode === 'register' ? 8 : 1}" />
              <div class="form-help" id="pwd-help" style="${mode === 'register' ? '' : 'display: none;'}">Must be at least 8 characters.</div>
            </div>

            <button type="submit" class="btn btn-primary" id="auth-submit-btn" style="width: 100%; margin-top: var(--space-3);">
              ${mode === 'login' ? 'Authenticate & Enter' : 'Register Account (1,000 Tokens Included)'}
            </button>
          </form>

          <!-- Return to Landing Page option -->
          <div style="text-align: center; margin-top: var(--space-4); padding-top: var(--space-3); border-top: 1px solid var(--border-subtle);">
            <button type="button" class="btn btn-ghost btn-sm" id="auth-guest-btn" style="color: var(--text-muted); font-size: var(--text-xs);">
              &larr; Return to Public Website
            </button>
          </div>
        </div>
      </div>
    </div>
  `;

  let currentMode = mode;
  const form = document.getElementById('auth-form');
  const emailInput = document.getElementById('auth-email');
  const passwordInput = document.getElementById('auth-password');
  const errorMsg = document.getElementById('auth-error-msg');
  const submitBtn = document.getElementById('auth-submit-btn');
  const tabLogin = document.getElementById('tab-login-btn');
  const tabReg = document.getElementById('tab-register-btn');
  const pwdHelp = document.getElementById('pwd-help');
  const closeBtn = document.getElementById('auth-close-btn');
  const backdrop = document.getElementById('auth-backdrop');
  const guestBtn = document.getElementById('auth-guest-btn');

  function switchMode(newMode) {
    currentMode = newMode;
    errorMsg.style.display = 'none';
    if (newMode === 'login') {
      tabLogin.classList.add('active');
      tabReg.classList.remove('active');
      submitBtn.textContent = 'Authenticate & Enter';
      pwdHelp.style.display = 'none';
      passwordInput.removeAttribute('minlength');
    } else {
      tabLogin.classList.remove('active');
      tabReg.classList.add('active');
      submitBtn.textContent = 'Register Account (1,000 Tokens Included)';
      pwdHelp.style.display = 'block';
      passwordInput.setAttribute('minlength', '8');
    }
  }

  if (tabLogin) tabLogin.addEventListener('click', () => switchMode('login'));
  if (tabReg) tabReg.addEventListener('click', () => switchMode('register'));

  // Close handlers: Button, Backdrop, and Guest button
  if (closeBtn) {
    closeBtn.addEventListener('click', () => closeAuthModal());
  }

  if (backdrop) {
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) {
        closeAuthModal();
      }
    });
  }

  if (guestBtn) {
    guestBtn.addEventListener('click', () => {
      closeAuthModal();
      if (!window.location.hash.startsWith('#/home')) {
        window.location.hash = '#/home';
      }
    });
  }

  // Form submission
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      errorMsg.style.display = 'none';
      submitBtn.disabled = true;
      submitBtn.textContent = 'Connecting to Control Plane...';

      try {
        if (currentMode === 'login') {
          await login(emailInput.value, passwordInput.value);
        } else {
          await register(emailInput.value, passwordInput.value);
        }
        closeAuthModal();
        // Forward to console overview once logged in
        window.location.hash = '#/overview';
      } catch (err) {
        errorMsg.textContent = err.message || 'Authentication failed';
        errorMsg.style.display = 'block';
        submitBtn.disabled = false;
        submitBtn.textContent = currentMode === 'login' ? 'Authenticate & Enter' : 'Register Account';
      }
    });
  }

  // Auto-focus email field
  setTimeout(() => {
    if (emailInput) emailInput.focus();
  }, 60);
}
