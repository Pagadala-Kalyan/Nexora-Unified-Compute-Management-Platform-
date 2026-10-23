/**
 * NEXORA UCMP — REACTIVE APPLICATION STATE & LIVE UPDATE ENGINE
 * Maintains cached backend snapshots and applies authenticated realtime events.
 */

import { apiRequest, getActiveStreamSession } from './api.js';
import { isAuthenticated, getCurrentUser, setCurrentUser } from './auth.js';

export const state = {
  user: getCurrentUser(),
  clusterHealth: { status: 'checking', latencyMs: 0, lastChecked: null },
  dashboard: null,
  telemetryHistory: {
    cpu: [],
    ram: [],
    gpu_compute: [],
    gpu_memory: [],
    timestamps: []
  },
  jobs: [],
  providers: [],
  checkpoints: [],
  billing: null,
  transactions: [],
  streamSession: null,
  analytics: null,
  realtime: { status: 'disconnected', lastSequence: 0, reconnectAttempts: 0, lastEventAt: null },
  pollingIntervalMs: 15000,
  isPollingActive: false,
  selectedTheme: localStorage.getItem('nexora_theme') || 'quantum-neon',
  sidebarCollapsed: localStorage.getItem('nexora_sidebar_collapsed') === 'true'
};

const listeners = new Set();
const TELEMETRY_HISTORY_LIMIT = 60;
const seenRealtimeEventIds = new Set();

function recordTelemetrySnapshot(dashboard, timestamp = new Date().toISOString()) {
  if (!dashboard) return;
  const parsedTime = new Date(timestamp || Date.now()).getTime();
  if (!Number.isFinite(parsedTime)) return;
  const sampleTimestamp = new Date(parsedTime).toISOString();

  const readings = {
    cpu: dashboard.cpu_utilization,
    ram: dashboard.ram_utilization,
    gpu_compute: dashboard.gpu_compute_utilization,
    gpu_memory: state.providers.some(provider => provider.gpu_name || Number(provider.gpu_memory_gb) > 0)
      ? (dashboard.gpu_memory_utilization ?? dashboard.gpu_utilization)
      : null
  };

  const hasReading = Object.values(readings).some(value => value != null && Number.isFinite(Number(value)));
  if (!hasReading) return;

  const history = state.telemetryHistory;
  const existingIndex = history.timestamps.indexOf(sampleTimestamp);
  const insertionIndex = existingIndex >= 0
    ? existingIndex
    : history.timestamps.findIndex(value => new Date(value).getTime() > parsedTime);
  const index = existingIndex >= 0 ? existingIndex : (insertionIndex < 0 ? history.timestamps.length : insertionIndex);

  for (const [metric, value] of Object.entries(readings)) {
    const numericValue = value == null || value === '' ? null : Number(value);
    const normalizedValue = numericValue != null && Number.isFinite(numericValue) ? numericValue : null;
    if (existingIndex >= 0) history[metric][index] = normalizedValue;
    else history[metric].splice(index, 0, normalizedValue);
  }
  if (existingIndex < 0) history.timestamps.splice(index, 0, sampleTimestamp);

  while (history.timestamps.length > TELEMETRY_HISTORY_LIMIT) {
    history.timestamps.shift();
    for (const metric of ['cpu', 'ram', 'gpu_compute', 'gpu_memory']) history[metric].shift();
  }
}

function recordProviderSnapshot(providers) {
  const online = (providers || []).filter(provider => ['ONLINE', 'AVAILABLE', 'BUSY'].includes(provider.status));
  if (!online.length) return;
  const average = metric => {
    const values = online.map(provider => provider.utilization?.[metric])
      .filter(value => value != null && Number.isFinite(Number(value))).map(Number);
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  };
  const heartbeats = online.map(provider => provider.last_heartbeat).filter(Boolean).map(value => new Date(value).getTime()).filter(Number.isFinite);
  if (!heartbeats.length) return;
  const timestamp = new Date(Math.max(...heartbeats)).toISOString();
  recordTelemetrySnapshot({
    cpu_utilization: average('cpu'),
    ram_utilization: average('ram'),
    gpu_memory_utilization: average('gpu_memory') ?? average('gpu'),
    gpu_compute_utilization: average('gpu_compute')
  }, timestamp);
}

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

function replaceById(items, item) {
  if (!item?.id) return items;
  const index = items.findIndex(entry => entry.id === item.id);
  if (index === -1) return [item, ...items];
  const next = [...items];
  next[index] = { ...next[index], ...item };
  return next;
}

function updateDashboardFromProviders() {
  const providers = state.providers || [];
  const average = (metric) => {
    const values = providers.map(provider => provider.utilization?.[metric]).filter(value => value != null && Number.isFinite(Number(value))).map(Number);
    return values.length ? Math.round(values.reduce((sum, value) => sum + value, 0) / values.length * 10) / 10 : null;
  };
  if (!state.dashboard) return;
  state.dashboard = {
    ...state.dashboard,
    available_nodes: providers.filter(provider => ['ONLINE', 'AVAILABLE'].includes(provider.status)).length,
    gpu_utilization: average('gpu_memory') ?? average('gpu'),
    gpu_memory_utilization: average('gpu_memory') ?? average('gpu'),
    gpu_compute_utilization: average('gpu_compute'),
    cpu_utilization: average('cpu'),
    ram_utilization: average('ram'),
    disk_utilization: average('disk')
  };
}

/** Apply a validated, committed control-plane event without another request. */
export function applyRealtimeEvent(event) {
  if (!event || typeof event !== 'object' || typeof event.type !== 'string' || !event.event_id) return;
  if (seenRealtimeEventIds.has(event.event_id)) return;
  seenRealtimeEventIds.add(event.event_id);
  if (seenRealtimeEventIds.size > 1000) {
    seenRealtimeEventIds.delete(seenRealtimeEventIds.values().next().value);
  }
  if (Number.isFinite(Number(event.sequence)) && Number(event.sequence) <= state.realtime.lastSequence) return;
  if (Number.isFinite(Number(event.sequence))) state.realtime.lastSequence = Number(event.sequence);
  state.realtime.lastEventAt = new Date();
  const data = event.data || {};

  if (['telemetry.updated', 'provider.registered', 'provider.status_changed', 'resource_pool.updated'].includes(event.type) && data.provider) {
    state.providers = replaceById(state.providers, data.provider);
    updateDashboardFromProviders();
    if (event.type === 'telemetry.updated') {
      // Match REST snapshots to the heartbeat, not the later WebSocket envelope
      // timestamp, so the same measurement replaces rather than duplicates.
      recordTelemetrySnapshot(state.dashboard, data.provider?.last_heartbeat || event.timestamp);
    }
  }
  if (event.type.startsWith('job.') && data.job) {
    state.jobs = replaceById(state.jobs, data.job);
    if (state.dashboard) {
      state.dashboard = {
        ...state.dashboard,
        active_jobs: state.jobs.filter(job => ['SCHEDULED', 'RUNNING', 'RECOVERING'].includes(job.status)).length,
        recent_jobs: state.jobs.slice(0, 5)
      };
    }
  }
  if (event.type === 'checkpoint.saved' && data.checkpoint?.id) {
    state.checkpoints = [data.checkpoint, ...state.checkpoints.filter(item => item.id !== data.checkpoint.id)]
      .sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime())
      .slice(0, 200);
  }
  if (event.type === 'billing.updated' && data.token_balance != null) {
    if (state.dashboard) state.dashboard = { ...state.dashboard, token_balance: data.token_balance };
    if (state.billing) state.billing = { ...state.billing, token_balance: data.token_balance, wallet_balance: data.token_balance };
    if (state.user) {
      state.user = { ...state.user, token_balance: data.token_balance };
      setCurrentUser(state.user);
    }
  }
  if (event.type === 'billing.updated' && data.transaction?.id) {
    state.transactions = [data.transaction, ...state.transactions.filter(item => item.id !== data.transaction.id)].slice(0, 50);
  }
  if (event.type === 'stream.updated' && data.session) {
    const session = { ...(state.streamSession || {}), ...data.session };
    state.streamSession = ['COMPLETED', 'FAILED'].includes(session.status) ? null : session;
  }
  notify(event.type === 'telemetry.updated'
    ? 'telemetry'
    : event.type === 'stream.updated'
      ? 'stream'
      : event.type === 'checkpoint.saved'
        ? 'checkpoints'
        : 'realtime');
}

export function setRealtimeConnectionState(status, reconnectAttempts = state.realtime.reconnectAttempts) {
  state.realtime = { ...state.realtime, status, reconnectAttempts };
  if (status === 'connected') {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = null;
  } else {
    scheduleReconciliation();
  }
  notify('realtime-status');
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
let refreshInFlight = null;
export function refreshAll() {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = performRefreshAll().finally(() => { refreshInFlight = null; });
  return refreshInFlight;
}

async function performRefreshAll() {
  await checkClusterHealth();

  if (!isAuthenticated()) {
    notify('unauthenticated');
    return;
  }

  try {
    const [dashboard, jobs, providers, checkpoints, billing, analytics, stream] = await Promise.allSettled([
      apiRequest('/dashboard'),
      apiRequest('/jobs'),
      apiRequest('/providers'),
      apiRequest('/checkpoints'),
      apiRequest('/billing'),
      apiRequest('/analytics'),
      getActiveStreamSession()
    ]);

    if (dashboard.status === 'fulfilled') {
      state.dashboard = dashboard.value;
      if (state.user && dashboard.value.token_balance != null) {
        state.user.token_balance = dashboard.value.token_balance;
        setCurrentUser(state.user);
      }
    }

    if (jobs.status === 'fulfilled') state.jobs = jobs.value;
    if (providers.status === 'fulfilled') {
      state.providers = providers.value;
      recordProviderSnapshot(providers.value);
    }
    if (checkpoints.status === 'fulfilled') state.checkpoints = checkpoints.value;
    if (billing.status === 'fulfilled') state.billing = billing.value;
    if (analytics.status === 'fulfilled') state.analytics = analytics.value;
    if (stream.status === 'fulfilled') state.streamSession = stream.value?.active ? stream.value.session : null;

    notify('all');
  } catch (err) {
    console.warn('Nexora refresh error:', err);
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
 * REST is used for initial/reconnect snapshots and bounded reconciliation only
 * while the shared WebSocket is disconnected. Live pages do not poll in parallel.
 */
let pollTimer = null;
const RECONCILIATION_INTERVAL_MS = 15000;

function scheduleReconciliation() {
  if (!state.isPollingActive || state.pollingIntervalMs <= 0 || state.realtime.status === 'connected' || pollTimer) return;
  const delay = Math.max(RECONCILIATION_INTERVAL_MS, Number(state.pollingIntervalMs) || RECONCILIATION_INTERVAL_MS);
  pollTimer = setTimeout(async () => {
    pollTimer = null;
    if (!state.isPollingActive || state.realtime.status === 'connected') return;
    await refreshAll();
    scheduleReconciliation();
  }, delay);
}

export function startPolling() {
  if (state.isPollingActive) return;
  state.isPollingActive = true;
  scheduleReconciliation();
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
