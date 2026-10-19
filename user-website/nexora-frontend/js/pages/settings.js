/**
 * NEXORA UCMP — SETTINGS & PROFILE PAGE
 */

import { state, setTheme, setPollingCadence } from '../state.js';
import { getIcon } from '../utils/icons.js';
import { logout, openAuthModal, isAuthenticated } from '../auth.js';
import { getApiBase, setApiBase } from '../api.js';
import { showToast } from '../components/toast.js';
import { formatNumber } from '../utils/formatters.js';

export function renderSettingsPage() {
  const isAuth = isAuthenticated();
  const user = state.user;
  const currentTheme = state.selectedTheme;
  const currentCadence = state.pollingIntervalMs;
  const currentApiBase = getApiBase() || 'Relative / Localhost';

  const themes = [
    {
      id: 'quantum-neon',
      name: 'Palette A — Quantum Neon',
      desc: 'Deep black & graphite with electric cyan & vivid violet accents.',
      bg: '#07090F',
      surface: '#111827',
      cyan: '#00E5FF',
      violet: '#8B5CF6'
    },
    {
      id: 'cyberpunk-obsidian',
      name: 'Palette B — Cyberpunk Obsidian',
      desc: 'Obsidian black with neon turquoise & hot magenta.',
      bg: '#050505',
      surface: '#17171E',
      cyan: '#00FFD1',
      violet: '#FF36D1'
    },
    {
      id: 'deep-space-blue',
      name: 'Palette C — Deep Space Blue',
      desc: 'Navy space aesthetic inspired by cloud orchestration planes.',
      bg: '#050B18',
      surface: '#101E35',
      cyan: '#35E0E8',
      violet: '#4DA3FF'
    },
    {
      id: 'arctic-light',
      name: 'Palette D — Arctic Light',
      desc: 'Crisp, high-contrast light mode for bright environments.',
      bg: '#F4F7FB',
      surface: '#FFFFFF',
      cyan: '#087EA4',
      violet: '#7057E8'
    }
  ];

  return `
    <div class="view-enter">
      <!-- Header -->
      <div class="overview-header">
        <div>
          <h2>System Settings & Preferences</h2>
          <p style="font-size: var(--text-xs); color: var(--text-muted);">
            Visual identity, interface polling rate, and active session management.
          </p>
        </div>
      </div>

      <div class="settings-grid">
        <!-- Section 1: User Profile & Session -->
        <div class="card">
          <div class="card-header">
            <div>
              <div class="card-title">${getIcon('user')} User Account & Session</div>
              <div class="card-subtitle">Authenticated identity and token allocation</div>
            </div>
          </div>

          ${isAuth ? `
            <div style="display: flex; flex-direction: column; gap: var(--space-3);">
              <div style="display: flex; justify-content: space-between; padding: 10px; background: var(--bg-secondary); border-radius: 6px;">
                <span style="font-size: var(--text-xs); color: var(--text-muted);">Registered Email:</span>
                <span style="font-size: var(--text-sm); font-weight: 600; color: var(--text-primary);">${user?.email}</span>
              </div>

              <div style="display: flex; justify-content: space-between; padding: 10px; background: var(--bg-secondary); border-radius: 6px;">
                <span style="font-size: var(--text-xs); color: var(--text-muted);">User Account ID:</span>
                <span style="font-family: var(--font-mono); font-size: var(--text-xs); color: var(--accent-cyan);">${user?.id ?? '—'}</span>
              </div>

              <div style="display: flex; justify-content: space-between; padding: 10px; background: var(--bg-secondary); border-radius: 6px;">
                <span style="font-size: var(--text-xs); color: var(--text-muted);">Compute Balance:</span>
                <span style="font-family: var(--font-mono); font-size: var(--text-sm); font-weight: 700; color: var(--accent-cyan);">${formatNumber(user?.token_balance ?? 0)} Tokens</span>
              </div>

              <button class="btn btn-danger" id="settings-logout-btn" style="margin-top: var(--space-2);">
                ${getIcon('logout')}
                End Session & Sign Out
              </button>
            </div>
          ` : `
            <div class="empty-state" style="padding: var(--space-4);">
              <div class="empty-state-title">No Active Session</div>
              <div class="empty-state-desc">Sign in or create an account to submit jobs and manage compute credits.</div>
              <button class="btn btn-primary btn-sm" id="settings-login-btn" style="margin-top: var(--space-3);">
                Sign In
              </button>
            </div>
          `}
        </div>

        <!-- Section 2: Polling & Network Configuration -->
        <div class="card">
          <div class="card-header">
            <div>
              <div class="card-title">${getIcon('refresh')} Telemetry Polling Cadence</div>
              <div class="card-subtitle">Frequency of background heartbeat & status refreshes</div>
            </div>
          </div>

          <div class="form-group">
            <label class="form-label" for="polling-cadence-select">Live Telemetry Interval</label>
            <select id="polling-cadence-select" class="select">
              <option value="2000" ${currentCadence === 2000 ? 'selected' : ''}>2 Seconds (Real-time)</option>
              <option value="4000" ${currentCadence === 4000 ? 'selected' : ''}>4 Seconds (Recommended)</option>
              <option value="8000" ${currentCadence === 8000 ? 'selected' : ''}>8 Seconds (Conserve Network)</option>
              <option value="0" ${currentCadence === 0 ? 'selected' : ''}>Manual Refresh Only (Paused)</option>
            </select>
          </div>

          <div class="form-group" style="margin-top: var(--space-4);">
            <label class="form-label" for="control-plane-url-input">Active Control Plane URL</label>
            <div style="display: flex; gap: var(--space-2);">
              <input type="text" id="control-plane-url-input" class="input input-mono" value="${currentApiBase}" placeholder="http://127.0.0.1:8000" />
              <button class="btn btn-outline btn-sm" id="save-url-btn">Save</button>
            </div>
            <div class="form-help">Default: local backend at <code>http://127.0.0.1:8000</code> or hosted Render endpoint.</div>
          </div>
        </div>
      </div>

      <!-- Section 3: Visual Identity & Color Themes -->
      <div class="card" style="margin-top: var(--space-6);">
        <div class="card-header">
          <div>
            <div class="card-title">${getIcon('palette')} Visual Identity Themes</div>
            <div class="card-subtitle">Switch between the 4 designed color palettes. Changes apply instantly across the entire interface.</div>
          </div>
        </div>

        <div class="theme-card-picker">
          ${themes.map(t => {
            const isActive = currentTheme === t.id;
            return `
              <div class="theme-preview-card ${isActive ? 'active' : ''}" data-theme-target="${t.id}" style="background: ${t.surface};">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span style="font-size: var(--text-sm); font-weight: 700; color: ${t.id === 'arctic-light' ? '#172033' : '#F4F7FF'};">${t.name}</span>
                  ${isActive ? `<span style="font-size: 11px; color: ${t.cyan}; font-weight: 700; font-family: var(--font-mono);">ACTIVE</span>` : ''}
                </div>
                <p style="font-size: var(--text-2xs); color: ${t.id === 'arctic-light' ? '#58677D' : '#A2AEC4'};">${t.desc}</p>
                <div class="palette-dots-row">
                  <span class="palette-dot" style="background: ${t.bg}; border: 1px solid rgba(255,255,255,0.2);"></span>
                  <span class="palette-dot" style="background: ${t.surface}; border: 1px solid rgba(255,255,255,0.2);"></span>
                  <span class="palette-dot" style="background: ${t.cyan};"></span>
                  <span class="palette-dot" style="background: ${t.violet};"></span>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      </div>

      <!-- Scope note -->
      <div style="margin-top: var(--space-6); padding: var(--space-4); background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); font-size: var(--text-xs); color: var(--text-muted);">
        ℹ️ <strong>Architecture Note:</strong> Administrative cluster policies, provider credentials, and sandbox isolation limits are managed at the host/control-plane daemon level. Only authorized endpoints exposed by the backend are controllable through this interface.
      </div>
    </div>
  `;
}

export function initSettingsEvents() {
  const logoutBtn = document.getElementById('settings-logout-btn');
  if (logoutBtn) logoutBtn.addEventListener('click', logout);

  const loginBtn = document.getElementById('settings-login-btn');
  if (loginBtn) loginBtn.addEventListener('click', () => openAuthModal('login'));

  // Theme cards
  document.querySelectorAll('.theme-preview-card').forEach(card => {
    card.addEventListener('click', () => {
      const target = card.getAttribute('data-theme-target');
      if (target) {
        setTheme(target);
        showToast(`Theme updated to ${target}`, 'info');
        window.dispatchEvent(new CustomEvent('nexora:rerender'));
      }
    });
  });

  // Polling select
  const cadenceSelect = document.getElementById('polling-cadence-select');
  if (cadenceSelect) {
    cadenceSelect.addEventListener('change', (e) => {
      const ms = Number(e.target.value);
      setPollingCadence(ms);
      showToast(ms > 0 ? `Telemetry interval set to ${ms / 1000}s` : 'Polling paused', 'info');
    });
  }

  // URL override save
  const saveUrlBtn = document.getElementById('save-url-btn');
  const urlInput = document.getElementById('control-plane-url-input');
  if (saveUrlBtn && urlInput) {
    saveUrlBtn.addEventListener('click', () => {
      const val = urlInput.value.trim();
      setApiBase(val);
      showToast(`Control plane endpoint set to: ${val || 'Default'}`, 'success');
      window.dispatchEvent(new CustomEvent('nexora:rerender'));
    });
  }
}
