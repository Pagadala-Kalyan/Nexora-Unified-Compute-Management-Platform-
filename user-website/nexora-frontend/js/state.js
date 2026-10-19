/**
 * NEXORA UCMP — REACTIVE APPLICATION STATE & POLLING ENGINE
 * Maintains cached real backend data and drives live UI updates.
 */

import { apiRequest } from './api.js';
import { isAuthenticated, getCurrentUser, setCurrentUser } from './auth.js';

export const state = {
  user: getCurrentUser(),
  clusterHealth: { status: 'checking', latencyMs: 0, lastChecked: null },
  dashboard: null,
  jobs: [],
  providers: [],
  checkpoints: [],
  billing: null,
  transactions: [],
  analytics: null,
  pollingIntervalMs: 4000,
  isPollingActive: false,
  selectedTheme: localStorage.getItem('nexora_theme') || 'quantum-neon',
  sidebarCollapsed: localStorage.getItem('nexora_sidebar_collapsed') === 'true'
};

const listeners = new Set();

export function subscribe(callback) {
  listeners.add(callback);
  return () => listeners.delete(callback);
}

export function notify(key) {
  for (const cb of listeners) {
    try {
      cb(key, state);
    } catch (e) {
      console.error('State subscriber error:', e);
    }
  }
}

/**
 * Health check ping (no auth needed)
 */
export async function checkClusterHealth() {
  const start = performance.now();
  try {
    const res = await apiRequest('/health', { timeout: 4000 });
    const latency = Math.round(performance.now() - start);
    state.clusterHealth = {
      status: res.status === 'ok' ? 'online' : 'unhealthy',
      latencyMs: latency,
      lastChecked: new Date()
    };
  } catch (e) {
    state.clusterHealth = {
      status: 'offline',
      latencyMs: 0,
      lastChecked: new Date()
    };
  }
  notify('clusterHealth');
  return state.clusterHealth;
}

/**
 * Fetch all authorized control plane datasets
 */
let isFetching = false;
export async function refreshAll() {
  await checkClusterHealth();

  if (!isAuthenticated()) {
    notify('unauthenticated');
    return;
  }

  if (isFetching) return;
  isFetching = true;

  try {
    const [dashboard, jobs, providers, checkpoints, billing, analytics] = await Promise.allSettled([
      apiRequest('/dashboard'),
      apiRequest('/jobs'),
      apiRequest('/providers'),
      apiRequest('/checkpoints'),
      apiRequest('/billing'),
      apiRequest('/analytics')
    ]);

    if (dashboard.status === 'fulfilled') {
      state.dashboard = dashboard.value;
      if (state.user && dashboard.value.token_balance != null) {
        state.user.token_balance = dashboard.value.token_balance;
        setCurrentUser(state.user);
      }
    }

    if (jobs.status === 'fulfilled') state.jobs = jobs.value;
    if (providers.status === 'fulfilled') state.providers = providers.value;
    if (checkpoints.status === 'fulfilled') state.checkpoints = checkpoints.value;
    if (billing.status === 'fulfilled') state.billing = billing.value;
    if (analytics.status === 'fulfilled') state.analytics = analytics.value;

    notify('all');
  } catch (err) {
    console.warn('Nexora refresh error:', err);
  } finally {
    isFetching = false;
  }
}

/**
 * Fetch transaction history
 */
export async function refreshTransactions() {
  if (!isAuthenticated()) return [];
  try {
    const txs = await apiRequest('/billing/transactions');
    state.transactions = txs;
    notify('transactions');
    return txs;
  } catch (e) {
    console.warn('Failed to load transactions:', e);
    return [];
  }
}

/**
 * Polling Lifecycle
 */
let pollTimer = null;

export function startPolling() {
  if (state.isPollingActive) return;
  state.isPollingActive = true;

  refreshAll();

  function scheduleNext() {
    if (!state.isPollingActive) return;
    pollTimer = setTimeout(async () => {
      if (state.isPollingActive) {
        await refreshAll();
        scheduleNext();
      }
    }, state.pollingIntervalMs);
  }

  scheduleNext();
}

export function stopPolling() {
  state.isPollingActive = false;
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

export function setPollingCadence(ms) {
  state.pollingIntervalMs = Number(ms);
  stopPolling();
  if (state.pollingIntervalMs > 0) {
    startPolling();
  }
}

export function setTheme(themeName) {
  state.selectedTheme = themeName;
  localStorage.setItem('nexora_theme', themeName);
  document.documentElement.setAttribute('data-theme', themeName);
  notify('theme');
}

export function toggleSidebar() {
  state.sidebarCollapsed = !state.sidebarCollapsed;
  localStorage.setItem('nexora_sidebar_collapsed', String(state.sidebarCollapsed));
  const sidebar = document.querySelector('.app-sidebar');
  if (sidebar) {
    sidebar.classList.toggle('sidebar-collapsed', state.sidebarCollapsed);
  }
  notify('sidebar');
}
