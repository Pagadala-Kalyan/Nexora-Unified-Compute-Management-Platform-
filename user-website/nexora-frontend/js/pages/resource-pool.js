/**
 * NEXORA UCMP — RESOURCE POOL & COMPATIBILITY SANDBOX PAGE
 */

import { state } from '../state.js';
import { getIcon } from '../utils/icons.js';
import { formatNumber, getStatusBadgeHTML } from '../utils/formatters.js';

let testCpu = 2;
let testRam = 4;
let testGpu = false;

export function renderResourcePoolPage() {
  const providers = state.providers || [];
  const onlineProviders = providers.filter(p => ['ONLINE', 'AVAILABLE', 'BUSY'].includes(p.status));

  // Compute aggregated cluster metrics
  const totalCores = providers.reduce((sum, p) => sum + (p.cpu_cores || 0), 0);
  const totalRam = providers.reduce((sum, p) => sum + (p.ram_gb || 0), 0);
  const totalVram = providers.reduce((sum, p) => sum + (p.gpu_memory_gb || 0), 0);

  // Evaluate candidate matching against test criteria
  const evaluated = providers.map(p => {
    const isOnline = ['ONLINE', 'AVAILABLE'].includes(p.status);
    const hasCpu = p.cpu_cores >= testCpu;
    const hasRam = p.ram_gb >= testRam;
    const hasGpu = !testGpu || (p.gpu_name && p.gpu_memory_gb > 0);

    const reasons = [];
    if (!isOnline) reasons.push('Provider node is currently OFFLINE');
    if (!hasCpu) reasons.push(`Insufficient CPU (${p.cpu_cores} < ${testCpu} cores)`);
    if (!hasRam) reasons.push(`Insufficient RAM (${p.ram_gb} < ${testRam} GB)`);
    if (!hasGpu) reasons.push('Missing required CUDA GPU');

    return {
      provider: p,
      isCompatible: isOnline && hasCpu && hasRam && hasGpu,
      reasons
    };
  });

  const compatibleCount = evaluated.filter(e => e.isCompatible).length;

  return `
    <div class="view-enter">
      <!-- Aggregated Fabric Banner -->
      <div class="pool-hero">
        <div class="pool-metric">
          <span class="pool-metric-label">Aggregated CPU Cores</span>
          <span class="pool-metric-value">${totalCores} Cores</span>
        </div>
        <div class="pool-metric">
          <span class="pool-metric-label">Cluster Memory</span>
          <span class="pool-metric-value">${totalRam.toFixed(1)} GB</span>
        </div>
        <div class="pool-metric">
          <span class="pool-metric-label">Pooled GPU VRAM</span>
          <span class="pool-metric-value" style="color: var(--accent-violet-vivid);">${totalVram.toFixed(1)} GB</span>
        </div>
        <div class="pool-metric">
          <span class="pool-metric-label">Active Compute Nodes</span>
          <span class="pool-metric-value" style="color: var(--status-success);">${onlineProviders.length} / ${providers.length}</span>
        </div>
      </div>

      <!-- Sandbox Grid -->
      <div class="sandbox-container">
        <!-- Left: Matcher Constraints -->
        <div class="card">
          <div class="card-header">
            <div>
              <div class="card-title">${getIcon('settings')} Workload Compatibility Matcher</div>
              <div class="card-subtitle">Simulate scheduler candidate filtering against cluster resources</div>
            </div>
          </div>

          <div class="form-group">
            <div style="display: flex; justify-content: space-between;">
              <label class="form-label">Required CPU Cores: <span id="pool-cpu-val" style="color: var(--accent-cyan); font-family: var(--font-mono);">${testCpu} Cores</span></label>
            </div>
            <input type="range" id="pool-cpu-range" min="1" max="32" value="${testCpu}" style="width: 100%; accent-color: var(--accent-cyan);" />
          </div>

          <div class="form-group">
            <div style="display: flex; justify-content: space-between;">
              <label class="form-label">Required Memory (GB): <span id="pool-ram-val" style="color: var(--accent-cyan); font-family: var(--font-mono);">${testRam} GB</span></label>
            </div>
            <input type="range" id="pool-ram-range" min="1" max="64" value="${testRam}" style="width: 100%; accent-color: var(--accent-cyan);" />
          </div>

          <div style="display: flex; align-items: center; justify-content: space-between; padding: 12px; background: var(--bg-secondary); border-radius: var(--radius-md); border: 1px solid var(--border-subtle); margin-top: var(--space-4);">
            <div>
              <div style="font-size: var(--text-sm); font-weight: 600; color: var(--text-primary);">Enforce CUDA GPU Acceleration</div>
              <div style="font-size: var(--text-2xs); color: var(--text-muted);">Exclude CPU-only machines from scheduler dispatch</div>
            </div>
            <input type="checkbox" id="pool-gpu-toggle" ${testGpu ? 'checked' : ''} style="width: 18px; height: 18px; accent-color: var(--accent-cyan); cursor: pointer;" />
          </div>

          <div style="margin-top: var(--space-6); padding: var(--space-3); background: var(--surface-elevated); border-radius: var(--radius-md); border: 1px solid var(--border-color); display: flex; align-items: center; justify-content: space-between;">
            <span style="font-size: var(--text-xs); color: var(--text-secondary);">Scheduler Match Outcome:</span>
            <span style="font-family: var(--font-mono); font-weight: 700; color: ${compatibleCount > 0 ? 'var(--status-success)' : 'var(--status-error)'}; font-size: var(--text-sm);">
              ${compatibleCount} Eligible Node${compatibleCount === 1 ? '' : 's'}
            </span>
          </div>
        </div>

        <!-- Right: Node Eligibility Status List -->
        <div class="card">
          <div class="card-header">
            <div>
              <div class="card-title">${getIcon('server')} Node Eligibility Analysis</div>
              <div class="card-subtitle">Live compatibility evaluation for all registered machines</div>
            </div>
          </div>

          <div style="display: flex; flex-direction: column; gap: var(--space-3); max-height: 400px; overflow-y: auto;">
            ${evaluated.map(item => {
              const p = item.provider;
              return `
                <div style="padding: var(--space-3); border-radius: var(--radius-md); border: 1px solid ${item.isCompatible ? 'var(--status-success)' : 'var(--border-color)'}; background: var(--surface-primary);">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                      <span class="health-dot ${item.isCompatible ? 'online' : 'offline'}" style="width: 8px; height: 8px;"></span>
                      <span style="font-weight: 600; font-size: var(--text-sm); color: var(--text-primary);">${p.name}</span>
                    </div>
                    <span style="font-size: var(--text-2xs); font-family: var(--font-mono); padding: 2px 8px; border-radius: var(--radius-full); background: ${item.isCompatible ? 'var(--status-success-soft)' : 'var(--status-error-soft)'}; color: ${item.isCompatible ? 'var(--status-success)' : 'var(--status-error)'};">
                      ${item.isCompatible ? 'ELIGIBLE' : 'INELIGIBLE'}
                    </span>
                  </div>

                  <div style="font-size: var(--text-2xs); font-family: var(--font-mono); color: var(--text-muted); margin-top: 4px;">
                    Specs: ${p.cpu_cores} Cores · ${p.ram_gb} GB RAM · ${p.gpu_name ? `${p.gpu_name} (${p.gpu_memory_gb}GB)` : 'No GPU'}
                  </div>

                  ${!item.isCompatible ? `
                    <div style="font-size: 11px; color: var(--status-error); margin-top: 6px; padding: 4px 8px; background: var(--status-error-soft); border-radius: 4px;">
                      ✕ ${item.reasons.join(' · ')}
                    </div>
                  ` : ''}
                </div>
              `;
            }).join('')}
          </div>
        </div>
      </div>
    </div>
  `;
}

export function initResourcePoolEvents() {
  const cpuRange = document.getElementById('pool-cpu-range');
  const ramRange = document.getElementById('pool-ram-range');
  const gpuToggle = document.getElementById('pool-gpu-toggle');

  if (cpuRange) {
    cpuRange.addEventListener('input', (e) => {
      testCpu = Number(e.target.value);
      window.dispatchEvent(new CustomEvent('nexora:rerender'));
    });
  }

  if (ramRange) {
    ramRange.addEventListener('input', (e) => {
      testRam = Number(e.target.value);
      window.dispatchEvent(new CustomEvent('nexora:rerender'));
    });
  }

  if (gpuToggle) {
    gpuToggle.addEventListener('change', (e) => {
      testGpu = e.target.checked;
      window.dispatchEvent(new CustomEvent('nexora:rerender'));
    });
  }
}
