/**
 * Single authenticated control-plane event connection.
 * Credentials travel in the WebSocket subprotocol header, never in a URL.
 */
import { getApiBase, getToken } from './api.js';
import { applyRealtimeEvent, refreshAll, setRealtimeConnectionState } from './state.js';

let socket = null;
let reconnectTimer = null;
let pingTimer = null;
let explicitlyStopped = false;
let attempts = 0;
let connectionGeneration = 0;
let waitingForSubscription = null;
let synchronizationBuffer = [];
let synchronizing = false;
const TOPICS = ['telemetry', 'providers', 'jobs', 'checkpoints', 'billing', 'resources', 'streams'];

function realtimeUrl() {
  const base = getApiBase() || window.location.origin;
  const url = new URL(base, window.location.origin);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = `${url.pathname.replace(/\/$/, '')}/ws/realtime`;
  url.search = '';
  return url.toString();
}

function clearTimers() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  if (pingTimer) clearInterval(pingTimer);
  reconnectTimer = null;
  pingTimer = null;
  if (waitingForSubscription) clearTimeout(waitingForSubscription);
  waitingForSubscription = null;
}

function scheduleReconnect() {
  if (explicitlyStopped || reconnectTimer) return;
  attempts += 1;
  const capped = Math.min(30000, 1000 * (2 ** Math.min(attempts - 1, 5)));
  const delay = Math.round(capped * (0.8 + Math.random() * 0.4));
  setRealtimeConnectionState('reconnecting', attempts);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, delay);
}

function connect() {
  const token = getToken();
  if (!token || explicitlyStopped) return;
  const generation = ++connectionGeneration;
  setRealtimeConnectionState('connecting', attempts);
  synchronizationBuffer = [];
  synchronizing = true;
  try {
    const currentSocket = new WebSocket(realtimeUrl(), ['nexora.realtime.v1', `nexora.jwt.${token}`]);
    socket = currentSocket;
    const isCurrent = () => socket === currentSocket && generation === connectionGeneration;

    const synchronize = async () => {
      if (!isCurrent()) return;
      if (waitingForSubscription) clearTimeout(waitingForSubscription);
      waitingForSubscription = null;
      setRealtimeConnectionState('syncing', attempts);
      try {
        // Snapshot after subscription, then replay events received during the
        // snapshot so a concurrent update cannot be overwritten by stale REST.
        let snapshotStartedAt = Date.now();
        await refreshAll();
        if (!isCurrent()) return;
        let buffered = synchronizationBuffer;
        synchronizationBuffer = [];
        for (let pass = 0; pass < 3; pass += 1) {
          const needsResync = buffered.some(event => event?.requires_resync && Date.parse(event.timestamp) > snapshotStartedAt);
          if (!needsResync) break;
          snapshotStartedAt = Date.now();
          await refreshAll();
          if (!isCurrent()) return;
          buffered = [...buffered, ...synchronizationBuffer];
          synchronizationBuffer = [];
        }
        if (buffered.some(event => event?.requires_resync && Date.parse(event.timestamp) > snapshotStartedAt)) {
          currentSocket.close(1011, 'Unable to resync oversized events');
          return;
        }
        synchronizing = false;
        buffered
          .filter(event => !event?.requires_resync && Date.parse(event.timestamp) > snapshotStartedAt)
          .forEach(applyRealtimeEvent);
        attempts = 0;
        setRealtimeConnectionState('connected', 0);
      } catch (_) {
        if (isCurrent()) currentSocket.close(1011, 'Initial state sync failed');
      }
    };

    currentSocket.addEventListener('open', () => {
      if (!isCurrent()) return;
      setRealtimeConnectionState('syncing', attempts);
      currentSocket.send(JSON.stringify({ type: 'subscribe', topics: TOPICS }));
      waitingForSubscription = setTimeout(() => {
        if (isCurrent()) currentSocket.close(1011, 'Subscription acknowledgement timed out');
      }, 10000);
      pingTimer = setInterval(() => {
        if (isCurrent() && currentSocket.readyState === WebSocket.OPEN) currentSocket.send(JSON.stringify({ type: 'ping' }));
      }, 25000);
    });
    currentSocket.addEventListener('message', ({ data }) => {
      if (!isCurrent() || typeof data !== 'string' || data.length > 65536) return;
      try {
        const event = JSON.parse(data);
        if (event?.type === 'system.subscribed') {
          if (TOPICS.every(topic => event.data?.topics?.includes(topic))) synchronize();
          else currentSocket.close(1008, 'Incomplete event subscription');
          return;
        }
        if (event?.type === 'system.error' && event.data?.message === 'Authentication required') {
          window.dispatchEvent(new CustomEvent('nexora:session-expired', { detail: { message: 'Please sign in again.' } }));
          currentSocket.close(1008, 'Authentication required');
          return;
        }
        if (event?.type?.startsWith('system.')) return;
        if (synchronizing) synchronizationBuffer.push(event);
        else if (event?.requires_resync) refreshAll();
        else applyRealtimeEvent(event);
      } catch (_) { /* malformed network input is ignored */ }
    });
    currentSocket.addEventListener('close', event => {
      if (!isCurrent()) return;
      clearTimers();
      socket = null;
      synchronizing = false;
      synchronizationBuffer = [];
      setRealtimeConnectionState('disconnected', attempts);
      if (!explicitlyStopped && event.code !== 1008 && event.code !== 4401) scheduleReconnect();
      else if (event.code === 1008 || event.code === 4401) {
        window.dispatchEvent(new CustomEvent('nexora:session-expired', { detail: { message: 'Live session authentication expired. Please sign in again.' } }));
      }
    });
    currentSocket.addEventListener('error', () => { if (isCurrent()) currentSocket.close(); });
  } catch (_) {
    scheduleReconnect();
  }
}

export function startRealtime() {
  explicitlyStopped = false;
  if (socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING || reconnectTimer) return;
  connect();
}

export function stopRealtime() {
  explicitlyStopped = true;
  connectionGeneration += 1;
  clearTimers();
  if (socket) socket.close(1000, 'Session ended');
  socket = null;
  attempts = 0;
  synchronizing = false;
  synchronizationBuffer = [];
  setRealtimeConnectionState('disconnected', 0);
}
