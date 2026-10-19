/**
 * NEXORA UCMP — APPLICATION ROOT BOOTSTRAPPER
 * Fixed: Debounced state subscriber prevents continuous re-renders from poll cycles.
 * Shell (sidebar + topbar) now only re-renders on route changes, not data updates.
 * Data-driven elements (token pill, health dot, node counts) update in-place.
 */

import { state, subscribe, startPolling, stopPolling, refreshAll, setTheme, toggleSidebar } from './state.js';
import { isAuthenticated, openAuthModal } from './auth.js';
import { initRouter, handleRoute, getCurrentRoute } from './router.js';
import { showToast } from './components/toast.js';
import { formatNumber } from './utils/formatters.js';

// ──────────────────────────────────────────────────────────────────────────────
// TARGETED IN-PLACE UI PATCHES
// These update specific elements without re-rendering the entire page.
// ──────────────────────────────────────────────────────────────────────────────

function patchShellData() {
  // 1. Update token balance pill in topbar
  const tokenPillSpan = document.querySelector('.token-balance-pill span:last-child');
  if (tokenPillSpan) {
    const balance = state.dashboard?.token_balance ?? state.user?.token_balance ?? 0;
    tokenPillSpan.textContent = `${formatNumber(balance)} TOKENS`;
  }

  // 2. Update cluster health dot and label
  const health = state.clusterHealth;
  const healthDot = document.querySelector('.health-dot');
  const healthLabel = document.querySelector('.health-label');
  if (healthDot) {
    healthDot.className = `health-dot ${health.status}`;
  }
  if (healthLabel) {
    healthLabel.textContent = health.status === 'online'
      ? `Online · ${health.latencyMs}ms`
      : health.status.toUpperCase();
  }

  // 3. Update sidebar system status node count
  const nodeCountEl = document.querySelector('.status-widget-metrics span:last-child');
  if (nodeCountEl) {
    const online = (state.providers || []).filter(p => ['ONLINE', 'AVAILABLE', 'BUSY'].includes(p.status)).length;
    const total = (state.providers || []).length || 1;
    nodeCountEl.textContent = `Nodes ${online}/${total}`;
  }

  // 4. Update sidebar user token balance
  const sidebarBalance = document.querySelector('.user-balance-text');
  if (sidebarBalance) {
    const balance = state.dashboard?.token_balance ?? state.user?.token_balance ?? 0;
    sidebarBalance.textContent = `${formatNumber(balance)} TOKENS`;
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// DEBOUNCED PAGE CONTENT REFRESH
// Collapses multiple rapid notify() calls into a single deferred re-render.
// Only re-renders the #page-content area, not the whole shell.
// ──────────────────────────────────────────────────────────────────────────────

let _renderPending = false;
let _renderTimer = null;

function scheduleContentRefresh(notifyKey) {
  // Health-only updates: patch in-place, don't queue a full content re-render
  if (notifyKey === 'clusterHealth') {
    patchShellData();
    return;
  }

  // For sidebar/theme changes, patch shell without re-rendering page content
  if (notifyKey === 'sidebar' || notifyKey === 'theme') {
    return; // sidebar toggle is already handled in state.js directly
  }

  // Unauthenticated — just patch shell (no jobs/providers data)
  if (notifyKey === 'unauthenticated') {
    patchShellData();
    return;
  }

  // For 'all' data updates: patch shell immediately, then debounce page content
  patchShellData();

  if (_renderPending) return; // already queued
  _renderPending = true;

  clearTimeout(_renderTimer);
  _renderTimer = setTimeout(() => {
    _renderPending = false;

    // Skip re-render if user is actively typing in a form field
    const activeEl = document.activeElement;
    const isTyping = activeEl && (
      activeEl.tagName === 'INPUT' ||
      activeEl.tagName === 'TEXTAREA' ||
      activeEl.tagName === 'SELECT'
    );
    if (isTyping) return;

    // Only re-render the page content area, not the full route shell
    const contentContainer = document.getElementById('page-content');
    if (!contentContainer) return;

    // Use the router's page-only partial update
    refreshPageContent();
  }, 600); // 600ms debounce — collapses burst of notify calls
}

// Re-renders only the #page-content for current route without touching shell
function refreshPageContent() {
  if (!isAuthenticated()) return; // Guests remain on public landing page
  const route = getCurrentRoute();
  const routeMap = {
    'overview':      () => import('./pages/overview.js').then(m => ({ render: m.renderOverviewPage, init: m.initOverviewEvents })),
    'jobs':          () => import('./pages/jobs.js').then(m => ({ render: m.renderJobsPage, init: m.initJobsEvents })),
    'providers':     () => import('./pages/providers.js').then(m => ({ render: m.renderProvidersPage, init: m.initProvidersEvents })),
    'resource-pool': () => import('./pages/resource-pool.js').then(m => ({ render: m.renderResourcePoolPage, init: m.initResourcePoolEvents })),
    'billing':       () => import('./pages/billing.js').then(m => ({ render: m.renderBillingPage, init: m.initBillingEvents })),
    'analytics':     () => import('./pages/analytics.js').then(m => ({ render: m.renderAnalyticsPage, init: m.initAnalyticsEvents })),
    'settings':      () => import('./pages/settings.js').then(m => ({ render: m.renderSettingsPage, init: m.initSettingsEvents })),
    'home':          null, // landing page doesn't need live refresh
    'landing':       null,
  };

  const loader = routeMap[route];
  if (!loader) return; // landing page — skip live refresh

  loader().then(({ render, init }) => {
    const container = document.getElementById('page-content');
    if (!container) return;
    container.innerHTML = render();
    if (init) {
      try { init(); } catch (e) { console.warn('Page init error:', e); }
    }
  }).catch(e => console.warn('Page refresh error:', e));
}

// ──────────────────────────────────────────────────────────────────────────────
// APP INIT
// ──────────────────────────────────────────────────────────────────────────────

function initApp() {
  // 1. Initialize Theme
  document.documentElement.setAttribute('data-theme', state.selectedTheme);

  // 2. Subscribe to state changes with debounced targeted updates
  subscribe((key) => {
    scheduleContentRefresh(key);
  });

  // 3. Handle Session Expiry (401 loop fix)
  window.addEventListener('nexora:session-expired', (e) => {
    stopPolling();
    showToast(e.detail?.message || 'Session expired. Please sign in again.', 'warning', 5000);
    // Only prompt login if the user is currently in a console route, not the public landing page
    const route = getCurrentRoute();
    if (route !== 'home' && route !== 'landing') {
      openAuthModal('login');
    }
  });

  // 4. Handle Authentication Changes
  window.addEventListener('nexora:auth-changed', (e) => {
    if (e.detail?.user) {
      showToast(`Welcome back, ${e.detail.user.email}!`, 'success');
      startPolling();
    } else {
      showToast('Signed out of Nexora Control Plane.', 'info');
      stopPolling();
      // On signout, smoothly take the user to the public landing page (no blocking modal)
      window.location.hash = '#/home';
    }
    handleRoute();
  });

  // 5. Global Keyboard Shortcuts
  window.addEventListener('keydown', (e) => {
    // ESC closes active modals / drawers
    if (e.key === 'Escape') {
      const modal = document.querySelector('.modal-backdrop.active');
      if (modal) modal.parentElement.innerHTML = '';
      const drawer = document.getElementById('drawer-backdrop');
      if (drawer) drawer.parentElement.innerHTML = '';
    }
    // Ctrl/Cmd+B toggles sidebar
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
      e.preventDefault();
      toggleSidebar();
    }
  });

  // 6. Mobile sidebar backdrop close
  const backdrop = document.getElementById('sidebar-backdrop');
  if (backdrop) {
    backdrop.addEventListener('click', () => {
      const sidebar = document.querySelector('.app-sidebar');
      if (sidebar) sidebar.classList.remove('mobile-open');
      backdrop.classList.remove('active');
    });
  }

  // 7. Initialize Router (renders shell + page for current hash)
  initRouter();

  // 8. Start Telemetry Polling
  startPolling();

  // 9. Default to public landing page if no hash is present
  if (!window.location.hash || window.location.hash === '#' || window.location.hash === '#/') {
    window.location.hash = '#/home';
  }
}

// Boot when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}
