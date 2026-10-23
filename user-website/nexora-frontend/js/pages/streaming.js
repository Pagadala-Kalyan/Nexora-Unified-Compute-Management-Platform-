/**
 * NEXORA UCMP — REMOTE LIVE STREAM STUDIO
 * Real-time OBS stream ingest, provider transcoding, and destination publishing.
 */

import { getIcon } from '../utils/icons.js';
import { showToast } from '../components/toast.js';
import { state } from '../state.js';
import {
  createStreamSession,
  getActiveStreamSession,
  stopStreamSession
} from '../api.js';

let currentSession = null;

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
    const data = await getActiveStreamSession();
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
  const isEncoding = session.status === 'ENCODING';
  const isIngesting = session.status === 'INGESTING';
  const isStopping = session.status === 'STOPPING';

  let statusClass = 'status-allocated';
  let statusLabel = 'Provider Assigned (Waiting for OBS)';
  if (isEncoding) {
    statusClass = 'status-encoding';
    statusLabel = 'LIVE & ENCODING';
  } else if (isIngesting) {
    statusClass = 'status-ingesting';
    statusLabel = 'Source Connected (Launching Encoder)';
  } else if (isStopping) {
    statusClass = 'status-stopping';
    statusLabel = 'Stopping Session...';
  }

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
            <button class="btn btn-danger btn-sm" id="btn-stop-stream" ${isStopping ? 'disabled' : ''}>
              ${getIcon('stop')} Stop Stream
            </button>
          </div>
        </div>

        <!-- Telemetry Gauges -->
        <div class="telemetry-metrics-grid">
          <div class="metric-gauge-box">
            <span class="metric-label">Output FPS</span>
            <span class="metric-value ${metrics.fps > 55 ? 'text-cyan' : ''}">${metrics.fps || '0.0'}</span>
            <span class="metric-sub">target: 60 fps</span>
          </div>

          <div class="metric-gauge-box">
            <span class="metric-label">Bitrate</span>
            <span class="metric-value text-purple">${metrics.bitrate_kbps ? Math.round(metrics.bitrate_kbps) + ' kbps' : '0 kbps'}</span>
            <span class="metric-sub">audio: 160k aac</span>
          </div>

          <div class="metric-gauge-box">
            <span class="metric-label">Speed</span>
            <span class="metric-value">${metrics.speed || '0.0x'}</span>
            <span class="metric-sub">real-time ratio</span>
          </div>

          <div class="metric-gauge-box">
            <span class="metric-label">Dropped Frames</span>
            <span class="metric-value ${metrics.dropped_frames > 0 ? 'text-amber' : ''}">${metrics.dropped_frames || '0'}</span>
            <span class="metric-sub">network / drop</span>
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
            <span class="meta-v" id="live-uptime-counter">${formatUptime(metrics.uptime_seconds || 0)}</span>
          </div>
        </div>
      </div>

      <!-- Right Column: OBS Connection Details -->
      <div class="obs-instructions-card">
        <div class="obs-card-header">
          <div class="obs-icon-badge">${getIcon('terminal')}</div>
          <div>
            <h3>OBS Studio Connection Guide</h3>
            <p class="text-muted">Configure OBS to push your raw capture stream to Nexora Ingest.</p>
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
          <strong>Next step:</strong> Open OBS &rarr; Click <em>Start Streaming</em>. The remote Nexora encoder will detect the input and begin transcoding to your destination automatically.
        </div>
      </div>
    </div>
  `;

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
        await stopStreamSession(session.id);
        showToast('Stream stop signal transmitted', 'info');
        await fetchAndRenderStreamState();
      } catch (e) {
        showToast(e.message || 'Failed to stop stream', 'error');
      }
    }
  });
}

function renderSetupForm(container) {
  const userTokens = state.user?.token_balance || 0;

  container.innerHTML = `
    <div class="stream-setup-card">
      <div class="setup-header">
        <h2>Launch a New Remote Live Stream</h2>
        <p class="text-muted">Encode high-fps live streams on distributed compute nodes without stressing your local gaming PC.</p>
      </div>

      <form id="stream-create-form" class="stream-form">
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
          <label for="destination-url">Destination RTMP(S) Server URL</label>
          <input type="text" id="destination-url" class="form-control" value="rtmp://a.rtmp.youtube.com/live2" placeholder="rtmp://a.rtmp.youtube.com/live2" required>
          <small class="form-help-text" id="destination-help">Get your stream key from YouTube Studio > Go Live.</small>
        </div>

        <!-- Destination Stream Key -->
        <div class="form-group">
          <label for="destination-key">Destination Stream Key</label>
          <input type="password" id="destination-key" class="form-control" placeholder="Paste your YouTube/Twitch stream key" required autocomplete="off">
          <small class="form-help-text">Your destination key is encrypted with AES/Fernet in transit and memory.</small>
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

        <div class="form-actions-bar">
          <button type="submit" class="btn btn-primary btn-lg" id="btn-start-stream">
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
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();

    const submitBtn = document.getElementById('btn-start-stream');
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = `<span class="spinner-inline"></span> Allocating Provider...`;
    }

    try {
      const payload = {
        destination_platform: platformSelect.value,
        destination_url: destUrlInput.value.trim(),
        destination_key: document.getElementById('destination-key').value.trim(),
        profile: profileSelect.value
      };

      const result = await createStreamSession(payload);
      showToast('Remote stream session allocated successfully!', 'success');
      currentSession = result;
      state.streamSession = result;
      const container = document.getElementById('stream-studio-content');
      if (container) renderActiveSession(container, result);
    } catch (err) {
      showToast(err.message || 'Failed to start stream session', 'error');
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `${getIcon('play')} Start Stream Session`;
      }
    }
  });
}

function formatUptime(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}
