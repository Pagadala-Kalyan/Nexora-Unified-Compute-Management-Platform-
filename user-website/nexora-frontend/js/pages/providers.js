/**
 * NEXORA UCMP — COMPUTE PROVIDERS FLEET PAGE
 */

import { state } from '../state.js';
import { getIcon } from '../utils/icons.js';
import { getStatusBadgeHTML, timeAgo, formatNumber } from '../utils/formatters.js';

export function renderProvidersPage() {
  const providers = state.providers || [];
  const total = providers.length;
  const online = providers.filter(p => p.status === 'ONLINE' || p.status === 'AVAILABLE').length;
  const busy = providers.filter(p => p.status === 'BUSY').length;
  const offline = providers.filter(p => p.status === 'OFFLINE').length;

  return `
    <div class="view-enter">
      <!-- Toolbar Header -->
      <div class="overview-header">
        <div>
          <h2>Compute Provider Fleet</h2>
          <p style="font-size: var(--text-xs); color: var(--text-muted);">
            Heterogeneous worker nodes registered with the Nexora control plane.
          </p>
        </div>

        <div style="display: flex; gap: var(--space-2);">
          <span class="badge badge-online"><span class="badge-dot"></span>${online} ONLINE</span>
          <span class="badge badge-busy"><span class="badge-dot"></span>${busy} BUSY</span>
          <span class="badge badge-offline"><span class="badge-dot"></span>${offline} OFFLINE</span>
        </div>
      </div>

      <!-- Provider Nodes Grid -->
      ${providers.length > 0 ? `
        <div class="providers-grid">
          ${providers.map(p => {
            const hasGpu = Boolean(p.gpu_name && p.gpu_name !== 'None' && p.gpu_memory_gb > 0);
            return `
              <div class="provider-card">
                <div class="provider-header">
                  <div class="provider-title-wrap">
                    <div class="provider-icon-node">
                      ${hasGpu ? getIcon('gpu') : getIcon('cpu')}
                    </div>
                    <div>
                      <div class="provider-name">${p.name || 'Nexora Provider'}</div>
                      <div class="provider-id">${p.id}</div>
                    </div>
                  </div>
                  ${getStatusBadgeHTML(p.status)}
                </div>

                <!-- Hardware Specs Matrix -->
                <div class="specs-grid">
                  <div class="spec-item">
                    <span class="spec-label">CPU Cores</span>
                    <span class="spec-value">${p.cpu_cores ?? '—'} Cores</span>
                  </div>

                  <div class="spec-item">
                    <span class="spec-label">Memory</span>
                    <span class="spec-value">${p.ram_gb ? `${p.ram_gb.toFixed(1)} GB` : '—'}</span>
                  </div>

                  <div class="spec-item" style="grid-column: span 2;">
                    <span class="spec-label">GPU Acceleration</span>
                    <span class="spec-value" style="color: ${hasGpu ? 'var(--accent-cyan-bright)' : 'var(--text-muted)'};">
                      ${hasGpu ? `${p.gpu_name} (${p.gpu_memory_gb} GB VRAM)` : 'No Dedicated GPU'}
                    </span>
                  </div>

                  <div class="spec-item">
                    <span class="spec-label">Reliability</span>
                    <span class="spec-value" style="color: var(--status-success);">${p.reliability ?? 100}%</span>
                  </div>

                  <div class="spec-item">
                    <span class="spec-label">Rate / Hour</span>
                    <span class="spec-value">$${(p.cost_per_hour ?? 0.25).toFixed(2)}/hr</span>
                  </div>
                </div>

                <!-- Footer with heartbeat pulse -->
                <div class="provider-footer">
                  <div style="display: flex; align-items: center; gap: 6px;">
                    <span class="health-dot ${p.status === 'OFFLINE' ? 'offline' : 'online'}" style="width: 6px; height: 6px;"></span>
                    <span style="font-family: var(--font-mono); font-size: 11px;">Heartbeat: ${timeAgo(p.last_heartbeat)}</span>
                  </div>
                  <span style="font-family: var(--font-mono); font-size: 11px; color: var(--accent-cyan);">
                    ${p.utilization?.cpu != null ? `CPU: ${p.utilization.cpu}%` : 'Idle'}
                  </span>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      ` : `
        <div class="card">
          <div class="empty-state">
            <div class="empty-state-icon">${getIcon('server')}</div>
            <div class="empty-state-title">No Compute Providers Registered</div>
            <div class="empty-state-desc">
              Run <code>start.bat</code> in the <code>provider-server/</code> directory to attach this machine to the cluster.
            </div>
          </div>
        </div>
      `}
    </div>
  `;
}

export function initProvidersEvents() {
  // Provider events if interactive features are added
}
