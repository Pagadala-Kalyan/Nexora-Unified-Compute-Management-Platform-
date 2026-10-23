/**
 * NEXORA UCMP — OVERVIEW DASHBOARD PAGE
 * Visual Reference: rapt.ai GPU Management Dashboard
 * Features: 4 Metric Cards with Chip Badges, Spline Area Chart with Tabs,
 * Resource Allocation Donut, and High-Density Workloads Table
 */

import { state } from '../state.js';
import { getIcon } from '../utils/icons.js';
import { formatNumber, getStatusBadgeHTML, timeAgo } from '../utils/formatters.js';
import { renderSplineAreaChart, updateSplineAreaChart, renderResourceMixDonut } from '../utils/charts.js';
import { openJobModal } from '../components/job-modal.js';
import { openJobDrawer } from '../components/job-drawer.js';

const telemetryMetrics = {
  cpu: {
    metric: 'cpu',
    dashboardKey: 'cpu_utilization',
    strokeColor: '#35C98A',
    gradId: 'telemetry_cpu_grad',
    label: 'CPU utilization (%)'
  },
  memory: {
    metric: 'ram',
    dashboardKey: 'ram_utilization',
    strokeColor: '#6652D9',
    gradId: 'telemetry_mem_grad',
    label: 'System memory utilization (%)'
  },
  gpu_compute: {
    metric: 'gpu_compute',
    dashboardKey: 'gpu_compute_utilization',
    strokeColor: '#13D9F2',
    gradId: 'telemetry_gpu_compute_grad',
    label: 'GPU compute utilization (%)'
  },
  gpu_memory: {
    metric: 'gpu_memory',
    dashboardKey: 'gpu_memory_utilization',
    strokeColor: '#8B64FF',
    gradId: 'telemetry_gpu_memory_grad',
    label: 'GPU memory utilization (%)'
  }
};

let currentTelemetryTab = 'gpu_memory';

function telemetryDatasetFor(tab) {
  const metric = telemetryMetrics[tab];
  const history = state.telemetryHistory || {};
  const timestamps = history.timestamps || [];
  const historicalPoints = history[metric.metric] || [];
  const latestRaw = state.dashboard?.[metric.dashboardKey];
  const latestValue = latestRaw == null ? null : Number(latestRaw);
  const hasLatestValue = latestValue !== null && Number.isFinite(latestValue);
  const points = historicalPoints.length > 0
    ? historicalPoints
    : (hasLatestValue ? [latestValue] : []);
  const sampleTimes = timestamps.slice(-points.length);

  return {
    ...metric,
    points,
    timestamps: sampleTimes,
    labels: sampleTimes.map(timestamp => new Date(timestamp).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    }))
  };
}

function percent(value) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? Math.max(0, Math.min(100, Math.round(numericValue))) : 0;
}

export function renderOverviewPage() {
  const dash = state.dashboard || {};
  const jobs = state.jobs || [];
  const providers = state.providers || [];

  const totalJobs = jobs.length;
  const activeJobs = dash.active_jobs ?? jobs.filter(j => ['SCHEDULED', 'RUNNING', 'RECOVERING'].includes(j.status)).length;
  const onlineNodes = dash.available_nodes ?? providers.filter(p => ['ONLINE', 'AVAILABLE', 'BUSY'].includes(p.status)).length;
  const totalNodes = providers.length || (onlineNodes > 0 ? onlineNodes : 1);
  const tokenBalance = dash.token_balance ?? state.user?.token_balance ?? 0;

  // Calculate success rate
  const completedCount = jobs.filter(j => j.status === 'COMPLETED').length;
  const failedCount = jobs.filter(j => j.status === 'FAILED').length;
  const successRate = totalJobs > 0 
    ? Math.round((completedCount / (completedCount + failedCount || 1)) * 100) 
    : 100;

  const recentJobs = dash.recent_jobs?.length > 0 ? dash.recent_jobs : jobs.slice(0, 6);

  const telemetryDataset = telemetryDatasetFor(currentTelemetryTab);

  // Live resource mix derived from provider heartbeat utilization.
  const resourceSegments = [
    { label: 'GPU Memory', value: percent(dash.gpu_utilization), color: '#8B64FF' },
    { label: 'System Memory', value: percent(dash.ram_utilization), color: '#6652D9' },
    { label: 'CPU Usage', value: percent(dash.cpu_utilization), color: '#A78BFA' },
    { label: 'Disk Usage', value: percent(dash.disk_utilization), color: '#51416F' }
  ];

  return `
    <div class="view-enter">
      <!-- Dashboard Header -->
      <div class="overview-header">
        <div class="overview-greeting">
          <h1>Cluster Overview</h1>
          <p>Autonomous workload scheduling, distributed compute, and real-time GPU telemetry.</p>
        </div>

        <div class="overview-actions">
          <a href="#/providers" class="btn btn-outline btn-sm">
            ${getIcon('server')}
            <span>Fleet Nodes (${onlineNodes}/${totalNodes})</span>
          </a>
          <button class="btn btn-primary btn-sm" id="overview-launch-btn">
            ${getIcon('play')}
            <span>Launch Compute Job</span>
          </button>
        </div>
      </div>

      <!-- rapt.ai 4 KPI Cards Grid -->
      <div class="kpi-grid">
        <!-- KPI 1: Cluster Nodes -->
        <div class="kpi-card">
          <div class="kpi-top">
            <span class="kpi-label">Compute Nodes</span>
            <span class="kpi-chip-badge cyan">${onlineNodes} ONLINE</span>
          </div>
          <div class="kpi-value">${onlineNodes} <span style="font-size: var(--text-sm); font-weight: 500; color: var(--text-muted);">/ ${totalNodes}</span></div>
          <div class="kpi-subtext">Active cluster compute workers</div>
        </div>

        <!-- KPI 2: Active Workloads -->
        <div class="kpi-card">
          <div class="kpi-top">
            <span class="kpi-label">Active Workloads</span>
            <span class="kpi-chip-badge" style="background: var(--accent-cyan-soft); color: var(--accent-cyan); border-color: var(--border-color);">
              DISPATCHED
            </span>
          </div>
          <div class="kpi-value" style="color: var(--accent-cyan);">${activeJobs}</div>
          <div class="kpi-subtext">Scheduled · Running · Recovering</div>
        </div>

        <!-- KPI 3: Execution Success Rate -->
        <div class="kpi-card">
          <div class="kpi-top">
            <span class="kpi-label">Workload Success</span>
            <span class="kpi-chip-badge">${successRate}%</span>
          </div>
          <div class="kpi-value" style="color: var(--status-success);">${completedCount} <span style="font-size: var(--text-sm); font-weight: 500; color: var(--text-muted);">done</span></div>
          <div class="kpi-subtext">${totalJobs} total historical executions</div>
        </div>

        <!-- KPI 4: Token Balance -->
        <div class="kpi-card">
          <div class="kpi-top">
            <span class="kpi-label">Available Tokens</span>
            <span class="kpi-chip-badge" style="background: var(--accent-violet-soft); color: var(--accent-violet); border-color: var(--border-color);">
              CREDITS
            </span>
          </div>
          <div class="kpi-value">${formatNumber(tokenBalance)}</div>
          <div class="kpi-subtext">Control-plane execution wallet</div>
        </div>
      </div>

      <!-- rapt.ai Split Charts Grid (65% Spline + 35% Donut) -->
      <div class="dashboard-charts-grid">
        <!-- Left: Telemetry Spline Chart -->
        <div class="card" style="margin-bottom: 0;">
          <div class="chart-card-header">
            <div class="chart-title-wrap">
              <span class="chart-title">Cluster Telemetry</span>
              <span class="chart-subtitle">${telemetryDataset.label} from provider heartbeats</span>
            </div>

            <!-- rapt.ai Interactive Metric Tabs -->
            <div class="chart-tabs">
              <button class="chart-tab-btn ${currentTelemetryTab === 'cpu' ? 'active' : ''}" data-tab="cpu">CPU</button>
              <button class="chart-tab-btn ${currentTelemetryTab === 'memory' ? 'active' : ''}" data-tab="memory">Memory</button>
              <button class="chart-tab-btn ${currentTelemetryTab === 'gpu_compute' ? 'active' : ''}" data-tab="gpu_compute">GPU Compute</button>
              <button class="chart-tab-btn ${currentTelemetryTab === 'gpu_memory' ? 'active' : ''}" data-tab="gpu_memory">GPU Memory</button>
            </div>
          </div>

          <!-- Canvas Container -->
          <div class="chart-canvas-wrap" id="telemetry-chart-wrap">
            ${renderSplineAreaChart(
              telemetryDataset.points,
              {
                strokeColor: telemetryDataset.strokeColor,
                gradId: telemetryDataset.gradId,
                labels: telemetryDataset.labels,
                timestamps: telemetryDataset.timestamps
              }
            )}
          </div>
        </div>

        <!-- Right: Hardware Allocation Donut -->
        <div class="card" style="margin-bottom: 0;">
          <div class="chart-card-header">
            <div class="chart-title-wrap">
              <span class="chart-title">Resource Allocation</span>
              <span class="chart-subtitle">Aggregated capacity breakdown</span>
            </div>
          </div>

          <div class="donut-card-content">
            ${renderResourceMixDonut(resourceSegments, { size: 175, stroke: 20 })}

            <!-- Donut Legend -->
            <div class="donut-legend-list">
              ${resourceSegments.map(seg => `
                <div class="donut-legend-item">
                  <div class="donut-legend-label">
                    <span class="donut-legend-dot" style="background-color: ${seg.color};"></span>
                    <span>${seg.label}</span>
                  </div>
                  <span class="donut-legend-value">${seg.value}%</span>
                </div>
              `).join('')}
            </div>
          </div>
        </div>
      </div>

      <!-- High-Density Recent Workloads Table -->
      <div class="card" style="margin-top: var(--space-5);">
        <div class="card-header">
          <div>
            <div class="card-title">${getIcon('terminal')} Recent Workload Executions</div>
            <div class="card-subtitle">Latest compute jobs dispatched across the decentralized cluster</div>
          </div>
          <a href="#/jobs" class="btn btn-outline btn-sm">View All Workloads &rarr;</a>
        </div>

        ${recentJobs.length > 0 ? `
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Job Name</th>
                  <th>Workload</th>
                  <th>Status</th>
                  <th>Progress</th>
                  <th>Tokens</th>
                  <th>Provider Node</th>
                  <th>Submitted</th>
                </tr>
              </thead>
              <tbody>
                ${recentJobs.map(job => `
                  <tr style="cursor: pointer;" class="overview-job-row" data-job-id="${job.id}" title="Click to view workload inspector">
                    <td class="cell-primary">${job.name}</td>
                    <td class="cell-mono">${job.workload}</td>
                    <td>${getStatusBadgeHTML(job.status)}</td>
                    <td style="min-width: 130px;">
                      <div style="display: flex; align-items: center; gap: 8px;">
                        <div class="progress-bar-wrap" style="flex: 1;">
                          <div class="progress-bar-fill ${job.status === 'RECOVERING' ? 'recovering' : job.status === 'COMPLETED' ? 'completed' : ''}" style="width: ${job.progress ?? 0}%;"></div>
                        </div>
                        <span class="cell-mono">${job.progress ?? 0}%</span>
                      </div>
                    </td>
                    <td class="cell-mono" style="color: var(--accent-cyan); font-weight: 600;">${job.actual_tokens ?? job.reserved_tokens ?? 0}</td>
                    <td class="cell-mono">${job.provider_id || 'Pending'}</td>
                    <td class="cell-mono">${timeAgo(job.created_at)}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        ` : `
          <div class="empty-state">
            <div class="empty-state-icon">${getIcon('terminal')}</div>
            <div class="empty-state-title">No Workloads Recorded</div>
            <div class="empty-state-desc">Submit your first computational workload to begin remote cluster execution.</div>
            <button class="btn btn-primary btn-sm" id="empty-launch-btn" style="margin-top: var(--space-4);">
              ${getIcon('play')}
              Launch Workload
            </button>
          </div>
        `}
      </div>
    </div>
  `;
}

export function initOverviewEvents() {
  // Launch job buttons
  const launchBtn = document.getElementById('overview-launch-btn');
  if (launchBtn) launchBtn.addEventListener('click', openJobModal);

  const emptyLaunch = document.getElementById('empty-launch-btn');
  if (emptyLaunch) emptyLaunch.addEventListener('click', openJobModal);

  // Job row drawer click
  document.querySelectorAll('.overview-job-row').forEach(row => {
    row.addEventListener('click', () => {
      const jobId = row.getAttribute('data-job-id');
      if (jobId) openJobDrawer(jobId);
    });
  });

  // One delegated listener per mounted tab group; repeated init calls on the
  // same dashboard node cannot stack duplicate chart-switch handlers.
  const chartTabs = document.querySelector('.chart-tabs');
  const chartWrap = document.getElementById('telemetry-chart-wrap');

  if (chartTabs && chartTabs.dataset.telemetryBound !== 'true') {
    chartTabs.dataset.telemetryBound = 'true';
    chartTabs.addEventListener('click', event => {
      const btn = event.target.closest?.('.chart-tab-btn');
      if (!btn || !chartTabs.contains(btn)) return;
      const tab = btn.getAttribute('data-tab');
      if (!tab || !telemetryMetrics[tab]) return;

      currentTelemetryTab = tab;
      chartTabs.querySelectorAll('.chart-tab-btn').forEach(button => button.classList.remove('active'));
      btn.classList.add('active');

      if (chartWrap) {
        const telemetryDataset = telemetryDatasetFor(tab);
        const subtitle = document.querySelector('.chart-subtitle');
        if (subtitle) subtitle.textContent = `${telemetryDataset.label} from provider heartbeats`;
        chartWrap.innerHTML = renderSplineAreaChart(
          telemetryDataset.points,
          {
            strokeColor: telemetryDataset.strokeColor,
            gradId: telemetryDataset.gradId,
            labels: telemetryDataset.labels,
            timestamps: telemetryDataset.timestamps
          }
        );
      }
    });
  }
}

/** Refresh the selected telemetry series in place when a real backend sample arrives. */
export function updateTelemetryChart() {
  const chartWrap = document.getElementById('telemetry-chart-wrap');
  const metric = telemetryMetrics[currentTelemetryTab];
  if (!chartWrap || !metric) return;
  const dataset = telemetryDatasetFor(currentTelemetryTab);
  const subtitle = document.querySelector('.chart-subtitle');
  if (subtitle) subtitle.textContent = `${dataset.label} from provider heartbeats`;
  updateSplineAreaChart(chartWrap, dataset.points, {
    strokeColor: dataset.strokeColor,
    gradId: dataset.gradId,
    labels: dataset.labels,
    timestamps: dataset.timestamps
  });
}
