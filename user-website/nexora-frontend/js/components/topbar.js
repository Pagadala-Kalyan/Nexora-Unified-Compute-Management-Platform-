/**
 * NEXORA UCMP — TOPBAR COMPONENT
 * Visual Reference: rapt.ai GPU Dashboard & Sentinel Console
 * Features: High-density Breadcrumb/Title, ⌘K Quick Search, Cluster Telemetry & Actions
 */

import { getIcon } from '../utils/icons.js';
import { state, setTheme } from '../state.js';
import { isAuthenticated, openAuthModal } from '../auth.js';
import { formatNumber } from '../utils/formatters.js';
import { openPurchaseModal } from './purchase-modal.js';
import { showToast } from './toast.js';

export function renderTopbar(currentRoute = 'overview') {
  const routeMeta = {
    'overview': { title: 'Dashboard Overview', subtitle: 'Real-time infrastructure monitoring' },
    'jobs': { title: 'Compute Workloads', subtitle: 'Autonomous dispatch & fault recovery' },
    'providers': { title: 'Fleet Providers', subtitle: 'Active compute cluster nodes' },
    'resource-pool': { title: 'Resource Pool', subtitle: 'Aggregated CPU, RAM & GPU capacity' },
    'billing': { title: 'Wallet & Billing', subtitle: 'Token balances & transaction ledger' },
    'analytics': { title: 'Platform Analytics', subtitle: 'Cluster throughput & performance metrics' },
    'settings': { title: 'System Settings', subtitle: 'Telemetry polling & API connection' }
  };

  const meta = routeMeta[currentRoute] || { title: 'Overview', subtitle: 'Compute Orchestration' };
  const health = state.clusterHealth;
  const balance = state.dashboard?.token_balance ?? state.user?.token_balance ?? 0;

  const themes = [
    { id: 'quantum-neon', label: 'Quantum Neon', dot: '#8B64FF' },
    { id: 'cyberpunk-obsidian', label: 'Cyberpunk Obsidian', dot: '#6652D9' },
    { id: 'deep-space-blue', label: 'Deep Space Blue', dot: '#A78BFA' },
    { id: 'arctic-light', label: 'Arctic Light', dot: '#51416F' }
  ];

  return `
    <header class="app-topbar">
      <!-- Left: Mobile Toggle & Title -->
      <div class="topbar-left">
        <button class="mobile-menu-btn" id="mobile-menu-btn" aria-label="Open Navigation">
          ${getIcon('menu')}
        </button>

        <div class="topbar-title-wrap">
          <span class="topbar-page-title">${meta.title}</span>
          <span class="topbar-page-sub">| ${meta.subtitle}</span>
        </div>
      </div>

      <!-- Right: Search, Health, Balance & User Actions -->
      <div class="topbar-right">
        <!-- rapt.ai Search Box with ⌘K -->
        <div class="topbar-search-box">
          <span class="topbar-search-icon">${getIcon('search')}</span>
          <input
            type="text"
            class="topbar-search-input"
            id="topbar-search-input"
            placeholder="Search console..."
            autocomplete="off"
            aria-label="Search console"
          />
          <kbd class="topbar-search-kbd">⌘K</kbd>
        </div>

        <!-- Cluster Health Status Pill -->
        <div class="cluster-health-pill" title="Control-plane latency: ${health.latencyMs}ms">
          <span class="health-dot ${health.status}"></span>
          <span class="health-label">${health.status === 'online' ? `Online · ${health.latencyMs}ms` : health.status.toUpperCase()}</span>
        </div>

        <div id="realtime-status-pill" class="realtime-status-pill ${state.realtime.status === 'connected' ? 'connected' : 'stale'}" title="${state.realtime.status === 'connected' ? 'Connected to live event stream' : 'Waiting for live updates'}">
          ${state.realtime.status === 'connected' ? 'Live updates' : ['connecting', 'syncing'].includes(state.realtime.status) ? 'Syncing…' : 'Reconnecting · data may be stale'}
        </div>

        <!-- Token Balance Pill -->
        ${isAuthenticated() ? `
          <button class="token-balance-pill" id="topbar-token-pill" title="Click to view ledger or purchase tokens">
            ${getIcon('bolt')}
            <span>${formatNumber(balance)} TOKENS</span>
          </button>
        ` : ''}

        <!-- Notification Bell -->
        <button class="topbar-icon-btn" id="topbar-notifications-btn" title="System Notifications" aria-label="System Notifications">
          ${getIcon('bell')}
          <span class="bell-badge-dot"></span>
        </button>

        <!-- Theme Selector -->
        <div class="theme-selector-wrap">
          <button class="theme-btn" id="theme-menu-btn" title="Switch Theme Palette" aria-label="Switch Theme Palette">
            ${getIcon('palette')}
          </button>
          <div class="theme-dropdown" id="theme-dropdown">
            <div style="font-size: var(--text-2xs); font-weight: 700; color: var(--text-muted); padding: 4px 8px; text-transform: uppercase;">
              Select Theme
            </div>
            ${themes.map(t => `
              <button class="theme-option-btn ${state.selectedTheme === t.id ? 'active' : ''}" data-theme-id="${t.id}">
                <span class="theme-color-dot" style="background-color: ${t.dot};"></span>
                <span>${t.label}</span>
              </button>
            `).join('')}
          </div>
        </div>

        <!-- Auth button if unauthenticated -->
        ${!isAuthenticated() ? `
          <button class="btn btn-primary btn-sm" id="topbar-login-btn">
            ${getIcon('user')}
            <span>Sign In</span>
          </button>
        ` : ''}
      </div>
    </header>
  `;
}

export function initTopbarEvents() {
  // Theme Dropdown Toggle
  const themeBtn = document.getElementById('theme-menu-btn');
  const dropdown = document.getElementById('theme-dropdown');
  if (themeBtn && dropdown) {
    themeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      dropdown.classList.toggle('open');
    });

    dropdown.querySelectorAll('.theme-option-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const themeId = btn.getAttribute('data-theme-id');
        setTheme(themeId);
        dropdown.classList.remove('open');
        showToast(`Theme changed to ${btn.textContent.trim()}`, 'info');
      });
    });

    document.addEventListener('click', () => {
      dropdown.classList.remove('open');
    });
  }

  // Token Pill Purchase trigger
  const tokenPill = document.getElementById('topbar-token-pill');
  if (tokenPill) {
    tokenPill.addEventListener('click', () => {
      openPurchaseModal();
    });
  }

  // Notification Bell trigger
  const notifBtn = document.getElementById('topbar-notifications-btn');
  if (notifBtn) {
    notifBtn.addEventListener('click', () => {
      showToast('All compute orchestrator nodes reporting healthy status.', 'info');
    });
  }

  // Auth Button
  const loginBtn = document.getElementById('topbar-login-btn');
  if (loginBtn) {
    loginBtn.addEventListener('click', () => {
      openAuthModal('login');
    });
  }

  // Mobile Menu Toggle
  const mobileBtn = document.getElementById('mobile-menu-btn');
  if (mobileBtn) {
    mobileBtn.addEventListener('click', () => {
      const sidebar = document.querySelector('.app-sidebar');
      const backdrop = document.querySelector('.sidebar-backdrop');
      if (sidebar) sidebar.classList.add('mobile-open');
      if (backdrop) backdrop.classList.add('active');
    });
  }

  // Global ⌘K / Ctrl+K keyboard shortcut
  const searchInput = document.getElementById('topbar-search-input');
  window.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      if (searchInput) {
        searchInput.focus();
        searchInput.select();
      }
    }
  });

  // Search input feedback
  if (searchInput) {
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const query = searchInput.value.trim().toLowerCase();
        if (!query) return;
        if (query.includes('job') || query.includes('workload')) {
          window.location.hash = '#/jobs';
        } else if (query.includes('node') || query.includes('provider') || query.includes('gpu')) {
          window.location.hash = '#/providers';
        } else if (query.includes('wallet') || query.includes('token') || query.includes('bill')) {
          window.location.hash = '#/billing';
        } else if (query.includes('pool') || query.includes('resource')) {
          window.location.hash = '#/resource-pool';
        } else if (query.includes('analytic') || query.includes('metric')) {
          window.location.hash = '#/analytics';
        } else {
          showToast(`Searching console for "${query}"...`, 'info');
          window.location.hash = '#/jobs';
        }
      }
    });
  }
}
