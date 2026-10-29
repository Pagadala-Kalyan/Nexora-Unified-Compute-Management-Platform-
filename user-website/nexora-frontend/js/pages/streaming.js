/**
 * NEXORA UCMP — REMOTE LIVE STREAM STUDIO
 * Real-time OBS stream ingest, provider transcoding, and destination publishing.
 */

import { getIcon } from '../utils/icons.js';
import { showToast } from '../components/toast.js';
import { state } from '../state.js';
import { setCurrentUser } from '../auth.js';
import { getApiBase, getToken } from '../api.js';
import { requestBrowserCapture, startWhipPublisher, stopMediaStream } from '../utils/browser-capture.js';
import {
  createStreamSession,
  getActiveStreamSession,
  getStreamSession,
  stopStreamSession,
  apiRequest,
  getErrorMessage
} from '../api.js';
import { stopSessionAndCleanup } from '../utils/stream-stop.js';

let currentSession = null;
let streamWalletVerified = false;
let browserCaptureStream = null;
let browserWhipPublisher = null;
let browserCaptureStopping = false;
let browserCaptureStarting = false;
let captureAttemptId = 0;
let captureCleanupListenersInstalled = false;
const stopReconciliationSessions = new Set();

function escapeMarkup(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
}

const PLATFORM_PRESETS = {
  youtube: {
    name: 'YouTube Live',
    url: 'rtmp://a.rtmp.youtube.com/live2',
    help: 'Get your stream key from YouTube Studio > Go Live.'
  },
  twitch: {
    name: 'Twitch',
    url: 'rtmp://live.twitch.tv/app',
    help: 'Get your stream key from Twitch Creator Dashboard > Settings > Stream.'
  },
  custom_rtmp: {
    name: 'Custom RTMP / RTMPS',
    url: '',
    help: 'Enter the RTMP or RTMPS publish URL of your destination.'
  }
};

export function renderStreamingPage() {
  let initialHtml = `
    <div class="page-container stream-studio-page">
      <!-- Page Header -->
      <div class="page-header">
        <div class="header-titles">
          <div class="badge-tag live-badge-tag">
            <span class="live-dot-pulse"></span> REAL-TIME COMPUTE
          </div>
          <h1 class="page-title">Remote Live Stream Studio</h1>
          <p class="page-subtitle">Offload encoding to remote Nexora compute providers. Stream from OBS with minimal local CPU/GPU load.</p>
        </div>
        <div class="header-actions">
          <button class="btn btn-secondary btn-sm" id="btn-refresh-stream" title="Refresh Status">
            ${getIcon('refresh')} Refresh
          </button>
        </div>
      </div>

      <!-- Main Studio Body -->
      <div id="stream-studio-content" class="stream-studio-content">
        <div class="panel-loading-state">
          <div class="spinner"></div>
          <p>Connecting to control plane...</p>
        </div>
      </div>
    </div>
  `;

  return initialHtml;
}

export async function initStreamingEvents() {
  installBrowserCaptureCleanupListeners();
  const refreshBtn = document.getElementById('btn-refresh-stream');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
      fetchAndRenderStreamState();
    });
  }

  // Load initial state
  await fetchAndRenderStreamState();
}

async function fetchAndRenderStreamState() {
  const container = document.getElementById('stream-studio-content');
  if (!container) return;

  try {
    const [data, billing] = await Promise.all([
      getActiveStreamSession(),
      apiRequest('/billing').catch(() => null)
    ]);
    if (billing) {
      streamWalletVerified = true;
      state.billing = billing;
      if (state.dashboard) state.dashboard = { ...state.dashboard, token_balance: billing.token_balance };
      if (state.user) {
        state.user = { ...state.user, token_balance: billing.token_balance };
        setCurrentUser(state.user);
      }
    }
    if (data && data.active && data.session) {
      currentSession = data.session;
      state.streamSession = data.session;
      renderActiveSession(container, data.session);
    } else {
      currentSession = null;
      state.streamSession = null;
      renderSetupForm(container);
    }
  } catch (err) {
    container.innerHTML = `
      <div class="empty-state-card">
        <div class="empty-icon">${getIcon('alert')}</div>
        <h3>Failed to load streaming status</h3>
        <p class="text-muted">${err.message || 'Please check backend connectivity.'}</p>
        <button class="btn btn-primary btn-sm" id="btn-retry-stream">Retry</button>
      </div>
    `;
    const retryBtn = document.getElementById('btn-retry-stream');
    if (retryBtn) retryBtn.addEventListener('click', () => fetchAndRenderStreamState());
  }
}

export function updateStreamingView() {
  const container = document.getElementById('stream-studio-content');
  if (!container) return;
  currentSession = state.streamSession || null;
  if (currentSession) renderActiveSession(container, currentSession);
  else renderSetupForm(container);
}

function renderActiveSession(container, session) {
  const metrics = session.latest_metrics || {};
  const isEncoding = session.status === 'ENCODING' || session.status === 'STREAMING';
  const isReceiving = session.status === 'RECEIVING' || session.status === 'INGESTING';
  const isStopping = session.status === 'STOPPING';
  const isTerminal = ['STOPPED', 'COMPLETED', 'FAILED'].includes(session.status);
  const sourceMode = session.source_mode || session.encoding_config?.source_mode || 'obs';
  const isBrowserCapture = sourceMode === 'browser_capture';

  let statusClass = 'status-allocated';
  let statusLabel = 'Provider assigned';
  if (session.status === 'STARTING') {
    statusLabel = 'Starting provider encoder';
  } else if (session.status === 'WAITING_FOR_INPUT' || session.status === 'ALLOCATED') {
    statusLabel = 'Waiting for OBS input';
  } else if (isReceiving) {
    statusClass = 'status-ingesting';
    statusLabel = 'Receiving source media';
  } else if (session.status === 'ENCODING') {
    statusClass = 'status-encoding';
    statusLabel = 'Encoding media';
  } else if (session.status === 'STREAMING') {
    statusClass = 'status-encoding';
    statusLabel = 'LIVE & ENCODING';
  } else if (isStopping) {
    statusClass = 'status-stopping';
    statusLabel = 'Stopping Session...';
  } else if (session.status === 'FAILED') {
    statusClass = 'status-stopping';
    statusLabel = 'Stream failed';
  } else if (session.status === 'STOPPED') {
    statusClass = 'status-stopping';
    statusLabel = 'Stream stopped';
  } else if (session.status === 'COMPLETED') {
    statusClass = 'status-stopping';
    statusLabel = 'Stream completed';
  }
  const fpsTarget = session.encoding_config?.fps;
  const measured = (value, suffix = '') => value === undefined || value === null || value === '' ? '—' : `${value}${suffix}`;

  container.innerHTML = `
    <div class="stream-active-grid">
      <!-- Left Column: Session Telemetry & Controls -->
      <div class="stream-telemetry-card">
        <div class="card-header-flex">
          <div>
            <div class="stream-status-pill ${statusClass}">
              <span class="live-dot-pulse"></span> ${statusLabel}
            </div>
            <h2 class="session-heading">${session.destination_platform.toUpperCase()} &bull; ${session.profile_name}</h2>
          </div>
          <div>
            ${!isTerminal ? `<button class="btn btn-danger btn-sm" id="btn-stop-stream" ${isStopping ? 'disabled' : ''}>
              ${getIcon('stop')} Stop Stream
            </button>` : ''}
          </div>
        </div>

        <!-- Telemetry Gauges -->
        <div class="telemetry-metrics-grid">
          <div class="metric-gauge-box">
            <span class="metric-label">Output FPS</span>
            <span class="metric-value ${metrics.fps > 55 ? 'text-cyan' : ''}">${measured(metrics.fps)}</span>
            <span class="metric-sub">${fpsTarget ? `target: ${fpsTarget} fps` : 'measured from FFmpeg'}</span>
          </div>

          <div class="metric-gauge-box">
            <span class="metric-label">Bitrate</span>
            <span class="metric-value text-purple">${metrics.bitrate_kbps == null ? '—' : `${Math.round(metrics.bitrate_kbps)} kbps`}</span>
            <span class="metric-sub">audio: 160k aac</span>
          </div>

          <div class="metric-gauge-box">
            <span class="metric-label">Speed</span>
            <span class="metric-value">${measured(metrics.speed)}</span>
            <span class="metric-sub">real-time ratio</span>
          </div>

          <div class="metric-gauge-box">
            <span class="metric-label">Dropped Frames</span>
            <span class="metric-value ${metrics.dropped_frames > 0 ? 'text-amber' : ''}">${measured(metrics.dropped_frames)}</span>
            <span class="metric-sub">reported by FFmpeg when available</span>
          </div>
        </div>

        <!-- Session Meta Details -->
        <div class="session-meta-table">
          <div class="meta-row">
            <span class="meta-k">Assigned Encoder Provider</span>
            <span class="meta-v"><code>${session.provider_name || session.provider_id || 'Auto-assigned'}</code></span>
          </div>
          <div class="meta-row">
            <span class="meta-k">Destination Target</span>
            <span class="meta-v"><code>${session.destination_url}</code> &bull; <small>${session.destination_key_masked}</small></span>
          </div>
          <div class="meta-row">
            <span class="meta-k">Metered Usage</span>
            <span class="meta-v"><strong>${session.total_tokens_billed || 0} tokens</strong> (${session.tokens_per_minute} tokens/min)</span>
          </div>
          <div class="meta-row">
            <span class="meta-k">Elapsed Runtime</span>
            <span class="meta-v" id="live-uptime-counter">${metrics.uptime_seconds == null ? '—' : formatUptime(metrics.uptime_seconds)}</span>
          </div>
          ${session.error_message ? `<div class="meta-row"><span class="meta-k">Status detail</span><span class="meta-v">${escapeMarkup(session.error_message)}</span></div>` : ''}
        </div>
      </div>

      <!-- Right Column: Browser Capture or OBS Connection Details -->
      ${isBrowserCapture ? `
      <div class="obs-instructions-card browser-capture-card">
        <div class="obs-card-header">
          <div class="obs-icon-badge">${getIcon('terminal')}</div>
          <div>
            <h3>Browser Capture</h3>
            <p class="text-muted">Capture a screen, window, or tab here. The browser publishes to Nexora over authenticated WebRTC; your YouTube key stays on the provider.</p>
          </div>
        </div>
        <video id="browser-capture-preview" class="browser-capture-preview" autoplay muted playsinline></video>
        <p class="form-help-text" id="browser-capture-status" role="status">${browserCaptureStarting ? 'Choose a screen, window, or tab in the browser prompt.' : browserWhipPublisher ? 'Browser transport connected. Waiting for verified provider output.' : 'Start screen capture to open the browser’s native sharing prompt.'}</p>
        ${isTerminal ? '<p class="form-help-text">This session has ended. Create a new session to capture again.</p>' : `
        <div class="form-actions-bar browser-capture-actions">
          <button class="btn btn-primary" id="btn-start-screen-capture" ${browserCaptureStream || browserCaptureStarting ? 'disabled' : ''}>Start Screen Capture</button>
          <button class="btn btn-secondary" id="btn-stop-screen-capture" ${browserCaptureStream ? '' : 'disabled'}>Stop Capture</button>
        </div>`}
        <div class="obs-step-notice"><strong>Separate destinations:</strong> Browser Capture → Nexora ingest → assigned provider → YouTube. YouTube credentials are not used by the browser.</div>
      </div>` : `
      <div class="obs-instructions-card">
        <div class="obs-card-header">
          <div class="obs-icon-badge">${getIcon('terminal')}</div>
          <div>
            <h3>OBS Studio Connection Guide</h3>
            <p class="text-muted"><strong>OBS → Nexora ingest.</strong> Use the Nexora server and session key below in OBS. Your YouTube destination key was entered in Nexora and must not be used as the OBS key.</p>
          </div>
        </div>

        <div class="credential-field-group">
          <label>1. Service Type</label>
          <div class="code-box">Custom...</div>
        </div>

        <div class="credential-field-group">
          <label>2. Server (Ingest URL)</label>
          <div class="input-copy-group">
            <input type="text" readonly value="${session.ingest_server}" id="ingest-url-input" class="code-input">
            <button class="btn btn-secondary btn-icon" id="copy-ingest-url" title="Copy Ingest Server">
              ${getIcon('copy')}
            </button>
          </div>
        </div>

        <div class="credential-field-group">
          <label>3. Stream Key</label>
          <div class="input-copy-group">
            <input type="password" readonly value="${session.stream_key || ''}" id="stream-key-input" class="code-input">
            <button class="btn btn-secondary btn-sm" id="toggle-stream-key" title="Show/Hide">Show</button>
            <button class="btn btn-secondary btn-icon" id="copy-stream-key" title="Copy Stream Key">
              ${getIcon('copy')}
            </button>
          </div>
        </div>

        <div class="obs-step-notice">
        <strong>Next:</strong> In OBS, open <em>Settings → Stream</em>, choose <em>Custom...</em>, and paste the Nexora server and Nexora session key above. Then click <em>Start Streaming</em> in OBS. Wait for Nexora to show incoming media and encoded output; the assigned provider sends that output to YouTube.
        </div>
      </div>
      `}
    </div>
  `;

  const preview = document.getElementById('browser-capture-preview');
  if (preview && browserCaptureStream) preview.srcObject = browserCaptureStream;

  document.getElementById('btn-start-screen-capture')?.addEventListener('click', () => {
    startBrowserCapture(session);
  });
  document.getElementById('btn-stop-screen-capture')?.addEventListener('click', () => {
    finishBrowserCapture(session, 'Browser capture stopped.');
  });

  // Attach event handlers
  document.getElementById('copy-ingest-url')?.addEventListener('click', () => {
    navigator.clipboard.writeText(session.ingest_server);
    showToast('Ingest URL copied to clipboard', 'info');
  });

  const streamKeyInput = document.getElementById('stream-key-input');
  const toggleKeyBtn = document.getElementById('toggle-stream-key');
  if (toggleKeyBtn && streamKeyInput) {
    toggleKeyBtn.addEventListener('click', () => {
      if (streamKeyInput.type === 'password') {
        streamKeyInput.type = 'text';
        toggleKeyBtn.textContent = 'Hide';
      } else {
        streamKeyInput.type = 'password';
        toggleKeyBtn.textContent = 'Show';
      }
    });
  }

  document.getElementById('copy-stream-key')?.addEventListener('click', () => {
    if (session.stream_key) {
      navigator.clipboard.writeText(session.stream_key);
      showToast('Stream key copied to clipboard', 'info');
    }
  });

  document.getElementById('btn-stop-stream')?.addEventListener('click', async () => {
    if (confirm('Are you sure you want to stop this live stream session?')) {
      try {
        const btn = document.getElementById('btn-stop-stream');
        if (btn) btn.disabled = true;
        const { session: stopped, cleanupError } = await stopSessionAndCleanup(
          () => stopStreamSession(session.id),
          () => isBrowserCapture ? releaseBrowserCapture() : null
        );
        const realtimeSession = state.streamSession?.id === session.id ? state.streamSession : null;
        state.streamSession = realtimeSession && ['STOPPED', 'COMPLETED', 'FAILED'].includes(realtimeSession.status)
          ? realtimeSession : { ...session, ...stopped };
        currentSession = state.streamSession;
        showToast(cleanupError
          ? `Backend accepted the stop request, but browser publisher cleanup was not confirmed. ${cleanupError.message}`
          : currentSession.status === 'STOPPING' ? 'Stop request accepted. Waiting for provider confirmation.' : 'Stream stopped.',
        cleanupError ? 'warning' : 'info');
        renderActiveSession(document.getElementById('stream-studio-content'), currentSession);
        if (currentSession.status === 'STOPPING') reconcileStreamStop(session.id);
      } catch (e) {
        const btn = document.getElementById('btn-stop-stream');
        if (btn) btn.disabled = false;
        if (e.cleanupError) showToast(`Browser publisher cleanup was not confirmed: ${e.cleanupError.message}`, 'warning');
        showToast(getErrorMessage(e, 'Failed to stop the stream.'), 'error');
        await fetchAndRenderStreamState();
      }
    }
  });
}

function renderSetupForm(container) {
  // Prefer the most recently fetched server wallet values over the user object
  // persisted at login, which can be stale after billing updates.
  const userTokens = Number(state.billing?.token_balance ?? state.dashboard?.token_balance ?? state.user?.token_balance ?? 0);
  const needsReserve = streamWalletVerified && userTokens < 10;

  container.innerHTML = `
    <div class="stream-setup-card">
      <div class="setup-header">
        <h2>Launch a New Remote Live Stream</h2>
        <p class="text-muted">First enter the YouTube Live server and stream key here. Nexora sends encoded output to YouTube; your selected input source publishes to Nexora using a separate session credential.</p>
      </div>

      <form id="stream-create-form" class="stream-form">
        <div class="form-group">
          <label for="stream-source-mode">Input Source</label>
          <select id="stream-source-mode" class="form-control">
            <option value="obs">OBS Studio (RTMP)</option>
            <option value="browser_capture">Browser Capture (WebRTC)</option>
          </select>
          <small class="form-help-text">Browser Capture uses the browser’s native screen sharing prompt; OBS remains available.</small>
        </div>
        <div class="form-row-2">
          <!-- Platform Preset -->
          <div class="form-group">
            <label for="stream-platform">Destination Platform</label>
            <select id="stream-platform" class="form-control" required>
              <option value="youtube">YouTube Live</option>
              <option value="twitch">Twitch</option>
              <option value="custom_rtmp">Custom RTMP / RTMPS</option>
            </select>
          </div>

          <!-- Quality Profile -->
          <div class="form-group">
            <label for="stream-profile">Encoding Profile</label>
            <select id="stream-profile" class="form-control">
              <option value="720p60">Balanced — 720p 60fps (4500 kbps, 2 tokens/min)</option>
              <option value="1080p60">High Quality — 1080p 60fps (6500 kbps, 4 tokens/min)</option>
              <option value="720p30">Standard — 720p 30fps (3000 kbps, 1 token/min)</option>
            </select>
          </div>
        </div>

        <!-- Destination URL -->
        <div class="form-group">
          <label for="destination-url">Nexora → YouTube: Destination RTMP(S) Server URL</label>
          <input type="text" id="destination-url" class="form-control" value="rtmp://a.rtmp.youtube.com/live2" placeholder="rtmp://a.rtmp.youtube.com/live2" required>
          <small class="form-help-text" id="destination-help">Get your stream key from YouTube Studio > Go Live.</small>
        </div>

        <!-- Destination Stream Key -->
        <div class="form-group">
          <label for="destination-key">YouTube Destination Stream Key</label>
          <input type="password" id="destination-key" class="form-control" placeholder="Paste your YouTube/Twitch stream key" required autocomplete="off">
          <small class="form-help-text">Enter the key from YouTube Studio here. It is sent only to the assigned provider for publishing and is never the key you paste into OBS.</small>
        </div>

        <!-- Token Balance & Cost Summary -->
        <div class="stream-cost-summary">
          <div class="cost-item">
            <span>Available Token Balance:</span>
            <strong>${userTokens} Tokens</strong>
          </div>
          <div class="cost-item">
            <span>Minimum Initial Reserve:</span>
            <strong>10 Tokens</strong>
          </div>
          <div class="cost-item">
            <span>Rate:</span>
            <span id="rate-display">2 tokens / min</span>
          </div>
        </div>

        ${needsReserve ? '<p class="form-help-text" role="status" style="color: var(--status-error);">You need at least 10 tokens to start a stream. Add tokens in Wallet &amp; Billing.</p>' : ''}

        <div class="form-actions-bar">
          <button type="submit" class="btn btn-primary btn-lg" id="btn-start-stream" ${needsReserve ? 'disabled' : ''}>
            ${getIcon('play')} Start Stream Session
          </button>
        </div>
      </form>
    </div>
  `;

  // Dynamic platform switch
  const platformSelect = document.getElementById('stream-platform');
  const destUrlInput = document.getElementById('destination-url');
  const destHelp = document.getElementById('destination-help');
  const profileSelect = document.getElementById('stream-profile');
  const rateDisplay = document.getElementById('rate-display');

  platformSelect?.addEventListener('change', () => {
    const val = platformSelect.value;
    const preset = PLATFORM_PRESETS[val];
    if (preset) {
      destUrlInput.value = preset.url;
      destHelp.textContent = preset.help;
      if (val === 'custom_rtmp') {
        destUrlInput.removeAttribute('readonly');
      }
    }
  });

  profileSelect?.addEventListener('change', () => {
    const rates = { '720p60': '2 tokens / min', '1080p60': '4 tokens / min', '720p30': '1 token / min' };
    if (rateDisplay) rateDisplay.textContent = rates[profileSelect.value] || '2 tokens / min';
  });

  // Handle submit
  const form = document.getElementById('stream-create-form');
  let isSubmitting = false;
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (isSubmitting) return;

    const destinationKey = document.getElementById('destination-key').value.trim();
    const destinationUrl = destUrlInput.value.trim();
    const parsedDestination = (() => {
      try { return new URL(destinationUrl); } catch (_) { return null; }
    })();

    if (streamWalletVerified && userTokens < 10) {
      showToast(`Not enough tokens to start this stream. The minimum reserve is 10 tokens; your balance is ${userTokens} tokens. Add tokens in Wallet & Billing and try again.`, 'error');
      return;
    }
    if (!parsedDestination || !['rtmp:', 'rtmps:'].includes(parsedDestination.protocol) || !parsedDestination.hostname) {
      showToast('Enter a valid RTMP or RTMPS destination server URL.', 'error');
      destUrlInput.focus();
      return;
    }
    if (destinationKey.length < 3) {
      showToast('Enter a valid destination stream key.', 'error');
      document.getElementById('destination-key').focus();
      return;
    }

    const submitBtn = document.getElementById('btn-start-stream');
    isSubmitting = true;
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = `<span class="spinner-inline"></span> Allocating Provider...`;
    }

    try {
      const payload = {
        source_mode: document.getElementById('stream-source-mode').value,
        destination_platform: platformSelect.value,
        destination_url: destinationUrl,
        destination_key: destinationKey,
        profile: profileSelect.value
      };

      const result = await createStreamSession(payload);
      showToast('Remote stream session allocated successfully!', 'success');
      currentSession = result;
      state.streamSession = result;
      const container = document.getElementById('stream-studio-content');
      if (container) renderActiveSession(container, result);
    } catch (err) {
      showToast(getErrorMessage(err, 'Failed to start the stream session. Please try again.'), 'error');
    } finally {
      isSubmitting = false;
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `${getIcon('play')} Start Stream Session`;
      }
    }
  });
}

function browserPublishCredential(session) {
  const username = session.browser_publish_credential?.username;
  const password = session.browser_publish_credential?.password;
  if (!username || !password) throw new Error('The session publish credential is invalid. Recreate the stream session.');
  return { username, password };
}

async function startBrowserCapture(session) {
  if (browserCaptureStream || browserCaptureStarting || browserCaptureStopping) return;
  if (!window.isSecureContext) {
    showToast('Browser Capture requires HTTPS, or localhost during local development.', 'error');
    return;
  }

  const attemptId = ++captureAttemptId;
  browserCaptureStarting = true;
  let capture;
  try {
    // getDisplayMedia is reached only from the explicit Start Screen Capture click.
    capture = await requestBrowserCapture(navigator.mediaDevices);
    if (attemptId !== captureAttemptId) {
      stopMediaStream(capture);
      return;
    }
    browserCaptureStarting = false;
    browserCaptureStream = capture;
    const preview = document.getElementById('browser-capture-preview');
    if (preview) preview.srcObject = capture;
    for (const track of capture.getTracks()) {
      track.onended = () => finishBrowserCapture(session, 'Screen sharing ended. The Nexora stream session is stopping.');
    }
    renderActiveSession(document.getElementById('stream-studio-content'), currentSession || session);

    const { username, password } = browserPublishCredential(session);
    const publisher = await startWhipPublisher({
      endpoint: session.webrtc_publish_url,
      stream: capture,
      username,
      password
    });
    if (attemptId !== captureAttemptId) {
      await publisher.close();
      return;
    }
    browserWhipPublisher = publisher;
    const status = document.getElementById('browser-capture-status');
    if (status) status.textContent = 'Browser media transport connected. Nexora will show encoding only after provider FFmpeg reports real output.';
    showToast('Browser capture is connected to Nexora ingest; waiting for provider output.', 'info');
    renderActiveSession(document.getElementById('stream-studio-content'), currentSession || session);
  } catch (error) {
    if (attemptId !== captureAttemptId) return;
    browserCaptureStarting = false;
    let cleanupError = null;
    let stopped = null;
    try {
      const result = await stopSessionAndCleanup(
        () => stopStreamSession(session.id),
        () => releaseBrowserCapture()
      );
      stopped = result.session;
      cleanupError = result.cleanupError;
      const realtimeSession = state.streamSession?.id === session.id ? state.streamSession : null;
      currentSession = realtimeSession && ['STOPPED', 'COMPLETED', 'FAILED'].includes(realtimeSession.status)
        ? realtimeSession : { ...session, ...stopped };
      state.streamSession = currentSession;
    } catch (stopError) {
      cleanupError = stopError.cleanupError || null;
    }
    const cleanupNote = cleanupError ? ` Browser publisher cleanup was not confirmed: ${cleanupError.message}` : '';
    showToast(`${getErrorMessage(error, 'Browser capture could not be started.')}${cleanupNote}`, 'error');
    await fetchAndRenderStreamState();
    if (stopped && currentSession?.status === 'STOPPING') reconcileStreamStop(session.id);
  }
}

async function releaseBrowserCapture() {
  captureAttemptId += 1;
  browserCaptureStarting = false;
  const stream = browserCaptureStream;
  const publisher = browserWhipPublisher;
  browserCaptureStream = null;
  browserWhipPublisher = null;
  stopMediaStream(stream);
  if (publisher) {
    const result = await publisher.close();
    return result?.cleanupError || null;
  }
  return null;
}

async function finishBrowserCapture(session, message) {
  if (browserCaptureStopping) return;
  browserCaptureStopping = true;
  try {
    const { session: stopped, cleanupError } = await stopSessionAndCleanup(
      () => stopStreamSession(session.id),
      () => releaseBrowserCapture()
    );
    const realtimeSession = state.streamSession?.id === session.id ? state.streamSession : null;
    currentSession = realtimeSession && ['STOPPED', 'COMPLETED', 'FAILED'].includes(realtimeSession.status)
      ? realtimeSession : { ...session, ...stopped };
    state.streamSession = currentSession;
    showToast(cleanupError ? `${message} Browser publisher cleanup was not confirmed: ${cleanupError.message}` : message,
      cleanupError ? 'warning' : 'info');
    const container = document.getElementById('stream-studio-content');
    if (container) renderActiveSession(container, currentSession);
    if (currentSession.status === 'STOPPING') reconcileStreamStop(session.id);
  } catch (error) {
    if (error.cleanupError) {
      showToast(`Browser media was stopped locally, but publisher cleanup was not confirmed: ${error.cleanupError.message}`, 'warning');
    }
    showToast(getErrorMessage(error, 'Could not stop browser capture cleanly.'), 'error');
  } finally {
    browserCaptureStopping = false;
  }
}

function reconcileStreamStop(sessionId) {
  if (stopReconciliationSessions.has(sessionId)) return;
  stopReconciliationSessions.add(sessionId);
  void (async () => {
    try {
      // Stop can be asynchronous while the provider handles STOP_STREAM. Reconcile
      // the authoritative active-session endpoint if the WebSocket event is missed.
      for (let attempt = 0; attempt < 30; attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        if (currentSession?.id !== sessionId && state.streamSession?.id !== sessionId) return;
        let active;
        try {
          active = await getActiveStreamSession();
        } catch (_) {
          continue;
        }
        if (active?.active && active.session?.id === sessionId) {
          currentSession = active.session;
          state.streamSession = active.session;
          if (active.session.status === 'STOPPING') continue;
          const container = document.getElementById('stream-studio-content');
          if (container) renderActiveSession(container, active.session);
          continue;
        }

        try {
          const ended = await getStreamSession(sessionId);
          currentSession = ended;
          state.streamSession = ended;
          const container = document.getElementById('stream-studio-content');
          if (container) renderActiveSession(container, ended);
        } catch (_) {
          // The backend's active=false response is authoritative; if the terminal
          // record is unavailable, clear the active session without claiming a status.
          currentSession = null;
          state.streamSession = null;
          const container = document.getElementById('stream-studio-content');
          if (container) renderSetupForm(container);
        }
        return;
      }
      if (currentSession?.id === sessionId && currentSession.status === 'STOPPING') {
        showToast('Stop is still processing. Nexora has not yet confirmed provider shutdown; refresh status in a moment.', 'warning');
      }
    } catch (_) {
      // Do not infer success from a failed status request. Keep the last confirmed
      // state visible and let the user refresh or rely on the live WebSocket update.
    } finally {
      stopReconciliationSessions.delete(sessionId);
    }
  })();
}

function installBrowserCaptureCleanupListeners() {
  if (captureCleanupListenersInstalled) return;
  captureCleanupListenersInstalled = true;

  window.addEventListener('hashchange', () => {
    const nextRoute = window.location.hash.replace(/^#\/?/, '').split(/[/?]/)[0].toLowerCase();
    if (nextRoute !== 'streaming' && (browserCaptureStream || browserCaptureStarting) && currentSession) {
      finishBrowserCapture(currentSession, 'Screen sharing stopped because you left Live Stream Studio.');
    }
  });

  window.addEventListener('pagehide', () => {
    if ((!browserCaptureStream && !browserCaptureStarting) || !currentSession) return;
    const sessionId = currentSession.id;
    const token = getToken();
    const stream = browserCaptureStream;
    const publisher = browserWhipPublisher;
    browserCaptureStream = null;
    browserWhipPublisher = null;
    browserCaptureStarting = false;
    captureAttemptId += 1;
    stopMediaStream(stream);
    if (publisher) publisher.close();
    if (token) {
      fetch(`${getApiBase()}/stream/sessions/${encodeURIComponent(sessionId)}/stop`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        keepalive: true
      }).catch(() => {});
    }
  });
}

function formatUptime(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}
