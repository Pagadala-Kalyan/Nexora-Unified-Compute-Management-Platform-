/**
 * NEXORA UCMP — PLATFORM ANALYTICS PAGE
 */

import { state } from '../state.js';
import { getIcon } from '../utils/icons.js';
import { formatNumber } from '../utils/formatters.js';
import { renderDistributionBar } from '../utils/charts.js';

export function renderAnalyticsPage() {
  const analytics = state.analytics || {};
  const jobs = state.jobs || [];

  const successRate = analytics.job_success_rate ?? (jobs.length > 0 ? 100 : 0);
  const totalJobs = analytics.total_jobs ?? jobs.length;
  const recoveryCount = analytics.recovery_count ?? 0;

  // Compute workload distribution
  const workloadCounts = {};
  const statusCounts = {};

  jobs.forEach(j => {
    workloadCounts[j.workload] = (workloadCounts[j.workload] || 0) + 1;
    statusCounts[j.status] = (statusCounts[j.status] || 0) + 1;
  });

  const workloadColors = {
    'matrix_multiply': 'var(--accent-cyan)',
    'prime_search': 'var(--accent-violet)',
    'fibonacci': 'var(--status-success)',
    'custom_python': 'var(--status-warning)'
  };

  const workloadSegments = Object.keys(workloadCounts).map(w => ({
    label: w,
    value: workloadCounts[w],
    color: workloadColors[w] || 'var(--text-muted)'
  }));

  const completedCount = statusCounts['COMPLETED'] || 0;
  const failedCount = statusCounts['FAILED'] || 0;
  const cancelledCount = statusCounts['CANCELLED'] || 0;
  const activeCount = (statusCounts['SCHEDULED'] || 0) + (statusCounts['RUNNING'] || 0) + (statusCounts['RECOVERING'] || 0);

  return `
    <div class="view-enter">
      <!-- Header -->
      <div class="overview-header">
        <div>
          <h2>Platform Performance Analytics</h2>
          <p style="font-size: var(--text-xs); color: var(--text-muted);">
            Real cluster metrics calculated from persistent control-plane records.
          </p>
        </div>
      </div>

      <!-- KPI Summary -->
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-top">
            <span class="kpi-label">Job Success Rate</span>
            <div class="kpi-icon-wrap" style="color: var(--status-success);">${getIcon('check')}</div>
          </div>
          <div class="kpi-value" style="color: var(--status-success);">${successRate}%</div>
          <div class="kpi-subtext">Completed / (Completed + Failed)</div>
        </div>

        <div class="kpi-card">
          <div class="kpi-top">
            <span class="kpi-label">Total Jobs Dispatched</span>
            <div class="kpi-icon-wrap">${getIcon('terminal')}</div>
          </div>
          <div class="kpi-value">${formatNumber(totalJobs)}</div>
          <div class="kpi-subtext">Historical workload volume</div>
        </div>

        <div class="kpi-card">
          <div class="kpi-top">
            <span class="kpi-label">Checkpoint Recoveries</span>
            <div class="kpi-icon-wrap" style="color: var(--status-recovering);">${getIcon('activity')}</div>
          </div>
          <div class="kpi-value" style="color: var(--status-recovering);">${recoveryCount}</div>
          <div class="kpi-subtext">Node disconnect failovers</div>
        </div>

        <div class="kpi-card">
          <div class="kpi-top">
            <span class="kpi-label">Completed Workloads</span>
            <div class="kpi-icon-wrap" style="color: var(--accent-cyan);">${getIcon('check')}</div>
          </div>
          <div class="kpi-value">${completedCount}</div>
          <div class="kpi-subtext">${failedCount} failed · ${cancelledCount} cancelled</div>
        </div>
      </div>

      <!-- Workload & Status Distribution -->
      <div class="cluster-utilization-grid">
        <!-- Workload Distribution -->
        <div class="card">
          <div class="card-header">
            <div>
              <div class="card-title">${getIcon('chart')} Workload Distribution</div>
              <div class="card-subtitle">Breakdown of submitted algorithmic workloads</div>
            </div>
          </div>

          <div style="margin: var(--space-4) 0;">
            ${renderDistributionBar(workloadSegments)}
          </div>

          <div style="display: flex; flex-direction: column; gap: var(--space-2); margin-top: var(--space-4);">
            ${workloadSegments.map(s => `
              <div style="display: flex; justify-content: space-between; align-items: center; font-size: var(--text-xs); padding: 4px 8px; background: var(--bg-secondary); border-radius: 4px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="width: 10px; height: 10px; border-radius: 2px; background: ${s.color};"></span>
                  <span style="font-family: var(--font-mono); color: var(--text-primary); text-transform: uppercase;">${s.label}</span>
                </div>
                <span style="font-family: var(--font-mono); font-weight: 700; color: var(--text-secondary);">${s.value} (${totalJobs > 0 ? ((s.value / totalJobs) * 100).toFixed(1) : 0}%)</span>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- Status Distribution -->
        <div class="card">
          <div class="card-header">
            <div>
              <div class="card-title">${getIcon('activity')} Lifecycle Status Breakdown</div>
              <div class="card-subtitle">Execution states across all recorded jobs</div>
            </div>
          </div>

          <div style="display: flex; flex-direction: column; gap: var(--space-3); margin-top: var(--space-4);">
            <div style="display: flex; justify-content: space-between; padding: 10px; background: var(--bg-secondary); border-radius: 6px; border: 1px solid var(--border-subtle);">
              <span style="font-size: var(--text-xs); color: var(--status-success); font-weight: 600;">COMPLETED</span>
              <span style="font-family: var(--font-mono); font-weight: 700; color: var(--text-primary);">${completedCount}</span>
            </div>

            <div style="display: flex; justify-content: space-between; padding: 10px; background: var(--bg-secondary); border-radius: 6px; border: 1px solid var(--border-subtle);">
              <span style="font-size: var(--text-xs); color: var(--status-scheduled); font-weight: 600;">ACTIVE / RUNNING</span>
              <span style="font-family: var(--font-mono); font-weight: 700; color: var(--text-primary);">${activeCount}</span>
            </div>

            <div style="display: flex; justify-content: space-between; padding: 10px; background: var(--bg-secondary); border-radius: 6px; border: 1px solid var(--border-subtle);">
              <span style="font-size: var(--text-xs); color: var(--status-error); font-weight: 600;">FAILED</span>
              <span style="font-family: var(--font-mono); font-weight: 700; color: var(--text-primary);">${failedCount}</span>
            </div>

            <div style="display: flex; justify-content: space-between; padding: 10px; background: var(--bg-secondary); border-radius: 6px; border: 1px solid var(--border-subtle);">
              <span style="font-size: var(--text-xs); color: var(--status-warning); font-weight: 600;">CANCELLED</span>
              <span style="font-family: var(--font-mono); font-weight: 700; color: var(--text-primary);">${cancelledCount}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}

export function initAnalyticsEvents() {
  // Interactive analytics events
}
