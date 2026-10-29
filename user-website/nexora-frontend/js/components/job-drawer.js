/**
 * NEXORA UCMP — JOB INSPECTION DRAWER
 * Deep inspection drawer showing live progress, provider telemetry,
 * saved checkpoint logs, output artifacts, and cancellation controls.
 */

import { apiRequest, getApiBase, getToken } from '../api.js';
import { state, refreshAll } from '../state.js';
import { showToast } from './toast.js';
import { getStatusBadgeHTML, formatDate, formatDuration, formatNumber, formatBytes, copyToClipboard } from '../utils/formatters.js';
import { getIcon } from '../utils/icons.js';

function escapeMarkup(str) {
  return String(str ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

export function openJobDrawer(jobId) {
  let drawerWrap = document.getElementById('job-drawer-wrap');
  if (!drawerWrap) {
    drawerWrap = document.createElement('div');
    drawerWrap.id = 'job-drawer-wrap';
    document.body.appendChild(drawerWrap);
  }

  const job = (state.jobs || []).find(j => j.id === jobId);
  if (!job) {
    showToast('Job record not found in local cache', 'error');
    return;
  }

  const provider = (state.providers || []).find(p => p.id === job.provider_id);
  const checkpoints = (state.checkpoints || []).filter(c => c.job_id === job.id);
  const isCancellable = ['QUEUED', 'SCHEDULED', 'RUNNING', 'RECOVERING'].includes(job.status);

  drawerWrap.innerHTML = `
    <div class="drawer-backdrop active" id="drawer-backdrop"></div>
    <div class="drawer-panel active" id="drawer-panel">
      <div class="drawer-header">
        <div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <h3 style="font-size: var(--text-md);">${job.name}</h3>
            ${getStatusBadgeHTML(job.status)}
          </div>
          <div style="display: flex; align-items: center; gap: 6px; margin-top: 4px;">
            <span style="font-family: var(--font-mono); font-size: var(--text-2xs); color: var(--text-muted);">${job.id}</span>
            <button id="copy-job-id-btn" style="background: transparent; border: none; color: var(--text-muted); cursor: pointer; display: flex; align-items: center;" title="Copy Job ID">
              ${getIcon('copy')}
            </button>
          </div>
        </div>
        <button class="modal-close-btn" id="drawer-close-btn">&times;</button>
      </div>

      <div class="drawer-body">
        <!-- Progress Bar Section -->
        <div style="background: var(--bg-secondary); padding: var(--space-4); border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
          <div style="display: flex; justify-content: space-between; font-size: var(--text-xs); margin-bottom: 6px;">
            <span style="color: var(--text-muted);">Execution Progress</span>
            <span style="font-family: var(--font-mono); font-weight: 700; color: var(--accent-cyan);">${job.progress ?? 0}%</span>
          </div>
          <div class="progress-bar-wrap" style="height: 8px;">
            <div class="progress-bar-fill ${job.status === 'RECOVERING' ? 'recovering' : job.status === 'COMPLETED' ? 'completed' : ''}" style="width: ${job.progress ?? 0}%;"></div>
          </div>
        </div>

        <!-- Provider Execution Node -->
        <div>
          <div style="font-size: var(--text-xs); font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: var(--space-2);">
            Target Compute Provider
          </div>
          <div style="background: var(--surface-primary); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: var(--space-3); display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 10px;">
              <div style="width: 28px; height: 28px; border-radius: 6px; background: var(--surface-elevated); display: flex; align-items: center; justify-content: center; color: var(--accent-cyan);">
                ${getIcon('server')}
              </div>
              <div>
                <div style="font-size: var(--text-sm); font-weight: 600; color: var(--text-primary);">${provider ? provider.name : (job.provider_id || 'Pending assignment')}</div>
                <div style="font-size: var(--text-2xs); font-family: var(--font-mono); color: var(--text-muted);">${job.provider_id || 'Unassigned'}</div>
              </div>
            </div>
            ${provider ? getStatusBadgeHTML(provider.status) : ''}
          </div>
        </div>

        <!-- Token Settlement Stats -->
        <div>
          <div style="font-size: var(--text-xs); font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: var(--space-2);">
            Token Settlement Details
          </div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); background: var(--bg-secondary); padding: var(--space-3); border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
            <div>
              <div style="font-size: var(--text-2xs); color: var(--text-muted);">Estimated Tokens</div>
              <div style="font-size: var(--text-sm); font-family: var(--font-mono); font-weight: 600; color: var(--text-primary);">${job.estimated_tokens ?? 0} Tokens</div>
            </div>
            <div>
              <div style="font-size: var(--text-2xs); color: var(--text-muted);">Reserved Tokens</div>
              <div style="font-size: var(--text-sm); font-family: var(--font-mono); font-weight: 600; color: var(--accent-cyan);">${job.reserved_tokens ?? 0} Tokens</div>
            </div>
            <div>
              <div style="font-size: var(--text-2xs); color: var(--text-muted);">Actual Settled</div>
              <div style="font-size: var(--text-sm); font-family: var(--font-mono); font-weight: 600; color: var(--status-success);">${job.actual_tokens != null ? `${job.actual_tokens} Tokens` : 'In Flight'}</div>
            </div>
            <div>
              <div style="font-size: var(--text-2xs); color: var(--text-muted);">Elapsed Runtime</div>
              <div style="font-size: var(--text-sm); font-family: var(--font-mono); font-weight: 600; color: var(--text-primary);">${formatDuration(job.result?.elapsed_seconds)}</div>
            </div>
          </div>
        </div>

        <!-- Saved Checkpoints History -->
        <div>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2);">
            <div style="font-size: var(--text-xs); font-weight: 700; color: var(--text-muted); text-transform: uppercase;">
              Saved Checkpoints (${checkpoints.length})
            </div>
          </div>
          ${checkpoints.length > 0 ? `
            <div style="display: flex; flex-direction: column; gap: 6px; max-height: 180px; overflow-y: auto;">
              ${checkpoints.map(cp => `
                <div style="background: var(--surface-primary); border: 1px solid var(--border-color); border-radius: 6px; padding: 8px 12px; display: flex; justify-content: space-between; align-items: center; font-size: var(--text-xs);">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="width: 8px; height: 8px; border-radius: 50%; background: var(--accent-violet);"></span>
                    <span style="font-family: var(--font-mono); color: var(--accent-cyan); font-weight: 600;">${cp.progress}% checkpoint</span>
                  </div>
                  <span style="font-family: var(--font-mono); font-size: var(--text-2xs); color: var(--text-muted);">${formatDate(cp.created_at)}</span>
                </div>
              `).join('')}
            </div>
          ` : `
            <div style="font-size: var(--text-xs); color: var(--text-muted); padding: 12px; background: var(--bg-secondary); border-radius: 6px; text-align: center;">
              No intermediate recovery checkpoints recorded yet.
            </div>
          `}
        </div>

        ${job.result?.video ? `
        <!-- Video Compression Output Card -->
        <div style="background: linear-gradient(135deg, var(--accent-cyan-soft), var(--accent-violet-soft)); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: var(--space-4);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-3);">
            <div>
              <div style="font-size: var(--text-xs); font-weight: 700; color: var(--accent-cyan); text-transform: uppercase; letter-spacing: 0.5px;">
                Compressed Media Output
              </div>
              <div style="font-size: var(--text-2xs); color: var(--text-muted); font-family: var(--font-mono); margin-top: 2px;">
                Validated FFprobe stream output · ${job.result.video.codec?.toUpperCase()} / ${job.result.video.target_resolution}
              </div>
            </div>
            <button class="btn btn-primary btn-sm" id="btn-download-video-artifact" style="display: flex; align-items: center; gap: 6px;">
              ${getIcon('download')}
              Download Output Video
            </button>
          </div>

          <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.08);">
            <div>
              <div style="font-size: var(--text-2xs); color: var(--text-muted);">Original Size</div>
              <div style="font-size: var(--text-sm); font-family: var(--font-mono); font-weight: 600; color: var(--text-primary);">${formatBytes(job.result.video.input_size_bytes)}</div>
            </div>
            <div>
              <div style="font-size: var(--text-2xs); color: var(--text-muted);">Compressed Size</div>
              <div style="font-size: var(--text-sm); font-family: var(--font-mono); font-weight: 600; color: var(--status-success);">${formatBytes(job.result.video.output_size_bytes)}</div>
            </div>
            <div>
              <div style="font-size: var(--text-2xs); color: var(--text-muted);">Space Saved</div>
              <div style="font-size: var(--text-sm); font-family: var(--font-mono); font-weight: 700; color: var(--accent-cyan);">
                ${job.result.video.input_size_bytes > 0 ? (Math.max(0, (1 - job.result.video.output_size_bytes / job.result.video.input_size_bytes) * 100)).toFixed(1) : '0'}%
                <span style="font-size: var(--text-2xs); font-weight: 400; color: var(--text-muted);">(${job.result.video.compression_ratio}x)</span>
              </div>
            </div>
          </div>
        </div>
        ` : ''}

        <!-- Output / Execution Result Payload -->
        <div>
          <div style="font-size: var(--text-xs); font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: var(--space-2);">
            Workload Result & Artifacts
          </div>
          ${job.workload === 'custom_python' && job.result?.output ? `
            <div style="margin-bottom: var(--space-3);">
              <div style="font-size: var(--text-2xs); color: var(--accent-cyan); font-weight: 600; text-transform: uppercase; margin-bottom: 4px;">Standard Output (stdout)</div>
              <pre style="background: #0d1117; border: 1px solid rgba(56, 189, 248, 0.25); border-radius: var(--radius-md); padding: var(--space-3); font-size: 12px; font-family: var(--font-mono); color: #39d353; overflow-x: auto; max-height: 220px; white-space: pre-wrap; line-height: 1.45;">${escapeMarkup(job.result.output)}</pre>
            </div>
          ` : ''}
          <pre style="background: var(--bg-app); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: var(--space-3); font-size: var(--text-xs); color: var(--accent-cyan-bright); overflow-x: auto; max-height: 220px; white-space: pre-wrap;">${job.result ? JSON.stringify(job.result, null, 2) : '// Awaiting workload completion...'}</pre>
        </div>
      </div>

      <!-- Drawer Footer with Cancel action -->
      <div class="drawer-footer" style="display: flex; justify-content: space-between; align-items: center;">
        <span style="font-size: var(--text-2xs); color: var(--text-muted); font-family: var(--font-mono);">
          SUBMITTED: ${formatDate(job.created_at)}
        </span>
        ${isCancellable ? `
          <button class="btn btn-danger btn-sm" id="btn-cancel-job-action">
            ${getIcon('stop')}
            Cancel Workload
          </button>
        ` : ''}
      </div>
    </div>
  `;

  function closeDrawer() {
    const backdrop = document.getElementById('drawer-backdrop');
    const panel = document.getElementById('drawer-panel');
    if (panel) panel.classList.remove('active');
    if (backdrop) backdrop.classList.remove('active');
    setTimeout(() => { drawerWrap.innerHTML = ''; }, 240);
  }

  document.getElementById('drawer-close-btn').addEventListener('click', closeDrawer);
  document.getElementById('drawer-backdrop').addEventListener('click', closeDrawer);

  const copyBtn = document.getElementById('copy-job-id-btn');
  if (copyBtn) {
    copyBtn.addEventListener('click', async () => {
      const ok = await copyToClipboard(job.id);
      if (ok) showToast(`Job ID copied to clipboard: ${job.id}`, 'info');
    });
  }

  const cancelBtn = document.getElementById('btn-cancel-job-action');
  if (cancelBtn) {
    cancelBtn.addEventListener('click', async () => {
      if (!confirm(`Are you sure you want to cancel "${job.name}"? Reserved tokens will be refunded.`)) return;
      cancelBtn.disabled = true;
      cancelBtn.textContent = 'Cancelling...';

      try {
        await apiRequest(`/jobs/${job.id}/cancel`, { method: 'POST' });
        showToast(`Workload "${job.name}" cancelled. Tokens refunded.`, 'success');
        await refreshAll();
        closeDrawer();
      } catch (err) {
        showToast(err.message || 'Failed to cancel job', 'error');
        cancelBtn.disabled = false;
        cancelBtn.textContent = 'Cancel Workload';
      }
    });
  }

  const downloadBtn = document.getElementById('btn-download-video-artifact');
  if (downloadBtn && job.result?.video?.output_artifact_id) {
    downloadBtn.addEventListener('click', async () => {
      downloadBtn.disabled = true;
      downloadBtn.innerHTML = `Downloading...`;
      try {
        const token = getToken();
        const base = getApiBase();
        const artifactId = job.result.video.output_artifact_id;
        const url = `${base}/jobs/${job.id}/artifacts/${artifactId}/download`;
        const res = await fetch(url, {
          headers: token ? { 'Authorization': `Bearer ${token}` } : {}
        });
        if (!res.ok) throw new Error(`Download failed with status ${res.status}`);
        const blob = await res.blob();
        const blobUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = `${job.name}_compressed.mp4`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(blobUrl);
        showToast('Video downloaded successfully', 'success');
      } catch (err) {
        showToast(err.message || 'Failed to download artifact', 'error');
      } finally {
        downloadBtn.disabled = false;
        downloadBtn.innerHTML = `${getIcon('download')} Download Output Video`;
      }
    });
  }
}
