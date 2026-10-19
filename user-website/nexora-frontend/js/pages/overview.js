/**
 * NEXORA UCMP — OVERVIEW DASHBOARD PAGE
 * Visual Reference: rapt.ai GPU Management Dashboard
 * Features: 4 Metric Cards with Chip Badges, Spline Area Chart with Tabs,
 * Resource Allocation Donut, and High-Density Workloads Table
 */

import { state } from '../state.js';
import { getIcon } from '../utils/icons.js';
import { formatNumber, getStatusBadgeHTML, timeAgo } from '../utils/formatters.js';
import { renderSplineAreaChart, renderResourceMixDonut } from '../utils/charts.js';
import { openJobModal } from '../components/job-modal.js';
import { openJobDrawer } from '../components/job-drawer.js';

// Telemetry dataset presets for interactive rapt.ai tabs
const telemetryDatasets = {
  usage: {
    points: [42, 58, 76, 91, 84, 69, 58, 88, 72, 64],
    strokeColor: '#7566F6',
    gradId: 'telemetry_usage_grad',
    label: 'GPU Utilization (%)'
  },
  memory: {
    points: [55, 62, 68, 74, 80, 85, 82, 79, 84, 88],
    strokeColor: '#13D9F2',
    gradId: 'telemetry_mem_grad',
    label: 'VRAM Allocation (%)'
  },
  temp: {
    points: [48, 51, 54, 62, 66, 68, 67, 69, 65, 63],
    strokeColor: '#F3B45F',
    gradId: 'telemetry_temp_grad',
    label: 'Core Temperature (°C)'
  }
};

let currentTelemetryTab = 'usage';

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

  // Resource mix segments (rapt.ai donut)
  const resourceSegments = [
    { label: 'GPU Compute', value: 78, color: '#13D9F2' },
    { label: 'GPU Memory', value: 65, color: '#7566F6' },
    { label: 'CPU Usage', value: 42, color: '#35C98A' },
    { label: 'Network I/O', value: 28, color: '#F3B45F' }
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
            <span class="kpi-chip-badge" style="background: rgba(19, 217, 242, 0.12); color: var(--accent-cyan); border-color: rgba(19, 217, 242, 0.25);">
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
            <span class="kpi-chip-badge" style="background: rgba(117, 102, 246, 0.12); color: var(--accent-violet); border-color: rgba(117, 102, 246, 0.25);">
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
              <span class="chart-title">Cluster Telemetry & GPU Load</span>
              <span class="chart-subtitle">Continuous time-series aggregate from compute workers</span>
            </div>

            <!-- rapt.ai Interactive Metric Tabs -->
            <div class="chart-tabs">
              <button class="chart-tab-btn ${currentTelemetryTab === 'usage' ? 'active' : ''}" data-tab="usage">Usage</button>
              <button class="chart-tab-btn ${currentTelemetryTab === 'memory' ? 'active' : ''}" data-tab="memory">Memory</button>
              <button class="chart-tab-btn ${currentTelemetryTab === 'temp' ? 'active' : ''}" data-tab="temp">Temp</button>
            </div>
          </div>

          <!-- Canvas Container -->
          <div class="chart-canvas-wrap" id="telemetry-chart-wrap">
            ${renderSplineAreaChart(
              telemetryDatasets[currentTelemetryTab].points,
              {
                strokeColor: telemetryDatasets[currentTelemetryTab].strokeColor,
                gradId: telemetryDatasets[currentTelemetryTab].gradId
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

  // rapt.ai Chart Tab switching
  const tabButtons = document.querySelectorAll('.chart-tab-btn');
  const chartWrap = document.getElementById('telemetry-chart-wrap');

  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.getAttribute('data-tab');
      if (!tab || !telemetryDatasets[tab]) return;

      currentTelemetryTab = tab;
      tabButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      if (chartWrap) {
        chartWrap.innerHTML = renderSplineAreaChart(
          telemetryDatasets[tab].points,
          {
            strokeColor: telemetryDatasets[tab].strokeColor,
            gradId: telemetryDatasets[tab].gradId
          }
        );
      }
    });
  });
}
