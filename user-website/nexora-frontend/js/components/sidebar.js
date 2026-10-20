/**
 * NEXORA UCMP — SIDEBAR COMPONENT
 * Visual Reference: rapt.ai GPU Management Sidebar
 * Features: Brand Identity, Sectional Nav, Status Widget & Operator Card
 */

import { getIcon } from '../utils/icons.js';
import { state, toggleSidebar } from '../state.js';
import { logout, openAuthModal, isAuthenticated } from '../auth.js';
import { formatNumber } from '../utils/formatters.js';

export function renderSidebar(currentRoute = 'overview') {
  const isAuth = isAuthenticated();
  const user = state.user;
  const activeJobsCount = (state.jobs || []).filter(j => ['SCHEDULED', 'RUNNING', 'RECOVERING'].includes(j.status)).length;
  const totalProviders = (state.providers || []).length;
  const onlineProvidersCount = (state.providers || []).filter(p => ['ONLINE', 'AVAILABLE', 'BUSY'].includes(p.status)).length;

  const computeNav = [
    { id: 'overview', label: 'Dashboard', icon: 'layers', badge: null },
    { id: 'jobs', label: 'Compute Jobs', icon: 'terminal', badge: activeJobsCount > 0 ? activeJobsCount : null },
    { id: 'streaming', label: 'Live Stream Studio', icon: 'radio', badge: null },
    { id: 'providers', label: 'Fleet Providers', icon: 'server', badge: onlineProvidersCount > 0 ? onlineProvidersCount : null },
    { id: 'resource-pool', label: 'Resource Pool', icon: 'cpu', badge: null },
  ];

  const platformNav = [
    { id: 'billing', label: 'Wallet & Billing', icon: 'wallet', badge: null },
    { id: 'analytics', label: 'Analytics', icon: 'chart', badge: null },
    { id: 'settings', label: 'Settings', icon: 'settings', badge: null },
  ];

  return `
    <aside class="app-sidebar ${state.sidebarCollapsed ? 'sidebar-collapsed' : ''}" id="main-sidebar">
      <!-- Sidebar Header -->
      <div class="sidebar-header">
        <a href="#/overview" class="brand-link" title="Nexora UCMP Console">
          <div class="brand-logo-wrap">
            ${getIcon('brandMark')}
          </div>
          <div class="brand-text">
            <span class="brand-name">NEXORA</span>
            <span class="brand-tagline">Compute Orchestration</span>
          </div>
        </a>
        <button class="sidebar-toggle-btn" id="sidebar-toggle-btn" title="Toggle Sidebar [Ctrl+B]" aria-label="Toggle Sidebar">
          ${getIcon('chevronLeft')}
        </button>
      </div>

      <!-- Navigation List -->
      <nav class="sidebar-nav">
        <!-- Landing Page Link -->
        <a href="#/home" class="nav-item" data-tooltip="Public Overview" style="margin-bottom: var(--space-2); border: 1px solid var(--border-subtle); color: var(--accent-cyan);">
          <span class="nav-icon" style="color: var(--accent-cyan);">${getIcon('chevronLeft')}</span>
          <span class="nav-text">Public Website</span>
        </a>

        <!-- Compute Section -->
        <div class="nav-section-title">Compute Control</div>
        ${computeNav.map(item => `
          <a href="#/${item.id}" class="nav-item ${currentRoute === item.id ? 'active' : ''}" data-tooltip="${item.label}">
            <span class="nav-icon">${getIcon(item.icon)}</span>
            <span class="nav-text">${item.label}</span>
            ${item.badge != null ? `<span class="nav-badge">${item.badge}</span>` : ''}
          </a>
        `).join('')}

        <!-- Platform Section -->
        <div class="nav-section-title">Platform</div>
        ${platformNav.map(item => `
          <a href="#/${item.id}" class="nav-item ${currentRoute === item.id ? 'active' : ''}" data-tooltip="${item.label}">
            <span class="nav-icon">${getIcon(item.icon)}</span>
            <span class="nav-text">${item.label}</span>
          </a>
        `).join('')}
      </nav>

      <!-- rapt.ai System Status Widget -->
      <div class="sidebar-status-widget">
        <div class="status-widget-top">
          <div class="status-widget-label">
            <span class="status-dot-pulse"></span>
            <span>SYSTEM STATUS</span>
          </div>
          <span class="status-widget-state">Operational</span>
        </div>
        <div class="status-widget-metrics">
          <span>Uptime 99.9%</span>
          <span>Nodes ${onlineProvidersCount}/${totalProviders || 1}</span>
        </div>
      </div>

      <!-- rapt.ai Operator Card / Footer -->
      <div class="sidebar-footer">
        ${isAuth ? `
          <div class="user-snippet" id="sidebar-user-card" title="Account settings">
            <div class="user-avatar-mini">${(user?.email || 'A')[0].toUpperCase()}</div>
            <div class="user-info-text">
              <div class="user-email-text">${user?.email || 'admin@nexora.io'}</div>
              <div class="user-balance-text">${formatNumber(user?.token_balance ?? 0)} TOKENS</div>
            </div>
            <button class="sidebar-toggle-btn" id="btn-sidebar-logout" title="Sign out" style="padding: 4px; color: var(--text-muted);">
              ${getIcon('logout')}
            </button>
          </div>
        ` : `
          <button class="btn btn-primary btn-sm" id="btn-sidebar-login" style="width: 100%;">
            ${getIcon('user')}
            <span class="nav-text">Sign In</span>
          </button>
        `}
      </div>
    </aside>
  `;
}

export function initSidebarEvents() {
  const toggleBtn = document.getElementById('sidebar-toggle-btn');
  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      toggleSidebar();
    });
  }

  const logoutBtn = document.getElementById('btn-sidebar-logout');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      logout();
    });
  }

  const loginBtn = document.getElementById('btn-sidebar-login');
  if (loginBtn) {
    loginBtn.addEventListener('click', (e) => {
      e.preventDefault();
      openAuthModal('login');
    });
  }
}
