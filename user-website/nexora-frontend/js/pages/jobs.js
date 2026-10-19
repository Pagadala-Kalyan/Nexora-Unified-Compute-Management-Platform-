/**
 * NEXORA UCMP — COMPUTE JOBS MANAGEMENT PAGE
 */

import { apiRequest } from '../api.js';
import { state, refreshAll } from '../state.js';
import { getIcon } from '../utils/icons.js';
import { getStatusBadgeHTML, formatNumber, formatDate, formatDuration, timeAgo } from '../utils/formatters.js';
import { openJobModal } from '../components/job-modal.js';
import { openJobDrawer } from '../components/job-drawer.js';
import { showToast } from '../components/toast.js';

let searchQuery = '';
let statusFilter = 'ALL';
let workloadFilter = 'ALL';
let sortOrder = 'desc';

export function renderJobsPage() {
  const allJobs = state.jobs || [];

  // Filter & Search logic
  const filtered = allJobs.filter(job => {
    if (statusFilter !== 'ALL' && job.status !== statusFilter) return false;
    if (workloadFilter !== 'ALL' && job.workload !== workloadFilter) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const matchName = (job.name || '').toLowerCase().includes(q);
      const matchId = (job.id || '').toLowerCase().includes(q);
      const matchProvider = (job.provider_id || '').toLowerCase().includes(q);
      if (!matchName && !matchId && !matchProvider) return false;
    }
    return true;
  });

  filtered.sort((a, b) => {
    const da = new Date(a.created_at).getTime();
    const db = new Date(b.created_at).getTime();
    return sortOrder === 'desc' ? db - da : da - db;
  });

  const activeCount = allJobs.filter(j => ['SCHEDULED', 'RUNNING', 'RECOVERING'].includes(j.status)).length;

  return `
    <div class="view-enter">
      <!-- Toolbar Header -->
      <div class="jobs-toolbar">
        <div>
          <h2>Compute Jobs Engine</h2>
          <p style="font-size: var(--text-xs); color: var(--text-muted);">
            ${allJobs.length} total jobs submitted · ${activeCount} active in cluster
          </p>
        </div>

        <div style="display: flex; align-items: center; gap: var(--space-3);">
          ${activeCount > 0 ? `
            <button class="btn btn-danger btn-sm" id="jobs-stop-all-btn">
              ${getIcon('stop')}
              Stop All Active Jobs (${activeCount})
            </button>
          ` : ''}

          <button class="btn btn-primary" id="jobs-launch-btn">
            ${getIcon('play')}
            Launch Workload
          </button>
        </div>
      </div>

      <!-- Filters Row -->
      <div class="jobs-toolbar" style="background: var(--surface-primary); padding: var(--space-3) var(--space-4); border: 1px solid var(--border-color); border-radius: var(--radius-lg);">
        <div class="jobs-filters">
          <!-- Search box -->
          <div class="search-box">
            ${getIcon('search')}
            <input type="text" id="jobs-search-input" class="input" placeholder="Search by name, ID, or node..." value="${searchQuery}" />
          </div>

          <!-- Status Filter -->
          <select id="jobs-status-select" class="select select-filter">
            <option value="ALL" ${statusFilter === 'ALL' ? 'selected' : ''}>All Statuses</option>
            <option value="RUNNING" ${statusFilter === 'RUNNING' ? 'selected' : ''}>Running</option>
            <option value="SCHEDULED" ${statusFilter === 'SCHEDULED' ? 'selected' : ''}>Scheduled</option>
            <option value="RECOVERING" ${statusFilter === 'RECOVERING' ? 'selected' : ''}>Recovering</option>
            <option value="COMPLETED" ${statusFilter === 'COMPLETED' ? 'selected' : ''}>Completed</option>
            <option value="FAILED" ${statusFilter === 'FAILED' ? 'selected' : ''}>Failed</option>
            <option value="CANCELLED" ${statusFilter === 'CANCELLED' ? 'selected' : ''}>Cancelled</option>
          </select>

          <!-- Workload Filter -->
          <select id="jobs-workload-select" class="select select-filter">
            <option value="ALL" ${workloadFilter === 'ALL' ? 'selected' : ''}>All Workloads</option>
            <option value="matrix_multiply" ${workloadFilter === 'matrix_multiply' ? 'selected' : ''}>Matrix Multiply</option>
            <option value="prime_search" ${workloadFilter === 'prime_search' ? 'selected' : ''}>Prime Search</option>
            <option value="fibonacci" ${workloadFilter === 'fibonacci' ? 'selected' : ''}>Fibonacci</option>
            <option value="custom_python" ${workloadFilter === 'custom_python' ? 'selected' : ''}>Custom Python</option>
          </select>
        </div>

        <div style="display: flex; align-items: center; gap: var(--space-2);">
          <span style="font-size: var(--text-2xs); color: var(--text-muted); text-transform: uppercase;">Sort Date:</span>
          <button class="btn btn-ghost btn-sm" id="jobs-sort-btn">
            ${sortOrder === 'desc' ? 'Newest First ↓' : 'Oldest First ↑'}
          </button>
        </div>
      </div>

      <!-- Jobs Data Table -->
      ${filtered.length > 0 ? `
        <div class="table-wrap" style="margin-top: var(--space-4);">
          <table class="data-table">
            <thead>
              <tr>
                <th>Job Identifier</th>
                <th>Workload Type</th>
                <th>Status</th>
                <th>Execution Progress</th>
                <th>Assigned Provider</th>
                <th>Tokens Reserved / Settled</th>
                <th>Duration</th>
                <th>Submission Time</th>
              </tr>
            </thead>
            <tbody>
              ${filtered.map(job => `
                <tr style="cursor: pointer;" class="job-table-row" data-job-id="${job.id}">
                  <td>
                    <div class="cell-primary">${job.name}</div>
                    <div class="cell-mono" style="font-size: 11px;">${job.id}</div>
                  </td>
                  <td class="cell-mono">${job.workload}</td>
                  <td>${getStatusBadgeHTML(job.status)}</td>
                  <td style="min-width: 140px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                      <div class="progress-bar-wrap" style="flex: 1;">
                        <div class="progress-bar-fill ${job.status === 'RECOVERING' ? 'recovering' : job.status === 'COMPLETED' ? 'completed' : ''}" style="width: ${job.progress ?? 0}%;"></div>
                      </div>
                      <span class="cell-mono">${job.progress ?? 0}%</span>
                    </div>
                  </td>
                  <td class="cell-mono">${job.actual_tokens != null ? `<span style="color: var(--status-success);">${job.actual_tokens} charged</span>` : `<span style="color: var(--accent-cyan);">${job.reserved_tokens ?? 0} reserved</span>`}</td>
                  <td class="cell-mono">${job.provider_id || 'Pending'}</td>
                  <td class="cell-mono">${formatDuration(job.result?.elapsed_seconds)}</td>
                  <td class="cell-mono" title="${formatDate(job.created_at)}">${timeAgo(job.created_at)}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      ` : `
        <div class="card" style="margin-top: var(--space-4);">
          <div class="empty-state">
            <div class="empty-state-icon">${getIcon('terminal')}</div>
            <div class="empty-state-title">No matching jobs found</div>
            <div class="empty-state-desc">Try clearing filters or search terms to inspect jobs.</div>
          </div>
        </div>
      `}
    </div>
  `;
}

export function initJobsEvents() {
  const searchInput = document.getElementById('jobs-search-input');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      searchQuery = e.target.value;
      window.dispatchEvent(new CustomEvent('nexora:rerender'));
    });
  }

  const statusSelect = document.getElementById('jobs-status-select');
  if (statusSelect) {
    statusSelect.addEventListener('change', (e) => {
      statusFilter = e.target.value;
      window.dispatchEvent(new CustomEvent('nexora:rerender'));
    });
  }

  const workloadSelect = document.getElementById('jobs-workload-select');
  if (workloadSelect) {
    workloadSelect.addEventListener('change', (e) => {
      workloadFilter = e.target.value;
      window.dispatchEvent(new CustomEvent('nexora:rerender'));
    });
  }

  const sortBtn = document.getElementById('jobs-sort-btn');
  if (sortBtn) {
    sortBtn.addEventListener('click', () => {
      sortOrder = sortOrder === 'desc' ? 'asc' : 'desc';
      window.dispatchEvent(new CustomEvent('nexora:rerender'));
    });
  }

  const launchBtn = document.getElementById('jobs-launch-btn');
  if (launchBtn) launchBtn.addEventListener('click', openJobModal);

  const stopAllBtn = document.getElementById('jobs-stop-all-btn');
  if (stopAllBtn) {
    stopAllBtn.addEventListener('click', async () => {
      if (!confirm('Are you sure you want to stop all active jobs in the cluster? Reserved tokens will be refunded.')) return;
      stopAllBtn.disabled = true;
      stopAllBtn.textContent = 'Stopping Jobs...';

      try {
        const res = await apiRequest('/jobs/stop-all', { method: 'POST' });
        showToast(`Stopped ${res.cancelled} active jobs! Tokens refunded.`, 'success');
        await refreshAll();
        window.dispatchEvent(new CustomEvent('nexora:rerender'));
      } catch (err) {
        showToast(err.message || 'Failed to stop all jobs', 'error');
        stopAllBtn.disabled = false;
        stopAllBtn.textContent = 'Stop All Active Jobs';
      }
    });
  }

  document.querySelectorAll('.job-table-row').forEach(row => {
    row.addEventListener('click', () => {
      const jobId = row.getAttribute('data-job-id');
      if (jobId) openJobDrawer(jobId);
    });
  });
}
