/**
 * NEXORA UCMP — WORKLOAD LAUNCH MODAL
 * Dynamic workload configuration with real-time token cost estimation
 * and compatible provider matching.
 */

import { apiRequest } from '../api.js';
import { state, refreshAll } from '../state.js';
import { showToast } from './toast.js';
import { formatNumber } from '../utils/formatters.js';

export function openJobModal() {
  let modalWrap = document.getElementById('job-modal-wrap');
  if (!modalWrap) {
    modalWrap = document.createElement('div');
    modalWrap.id = 'job-modal-wrap';
    document.body.appendChild(modalWrap);
  }

  const userBalance = state.dashboard?.token_balance ?? state.user?.token_balance ?? 0;
  const onlineProviders = (state.providers || []).filter(p => ['ONLINE', 'AVAILABLE'].includes(p.status));

  modalWrap.innerHTML = `
    <div class="modal-backdrop active" id="job-modal-backdrop">
      <div class="modal-box" style="max-width: 680px;">
        <div class="modal-header">
          <div>
            <div class="modal-title">Launch Compute Workload</div>
            <div style="font-size: var(--text-2xs); color: var(--text-muted); font-family: var(--font-mono); margin-top: 2px;">
              DISTRIBUTED ORCHESTRATION & REMOTE EXECUTION
            </div>
          </div>
          <button class="modal-close-btn" id="job-modal-close-btn">&times;</button>
        </div>

        <form id="job-launch-form">
          <div class="modal-body">
            <!-- Job Name -->
            <div class="form-group">
              <label class="form-label" for="job-name">Workload Name / Identifier</label>
              <input type="text" id="job-name" class="input" placeholder="e.g., Matrix-Benchmark-500" required minlength="2" maxlength="100" value="Workload-${Date.now().toString().slice(-4)}" />
            </div>

            <!-- Workload Type -->
            <div class="form-group">
              <label class="form-label" for="job-workload">Compute Algorithm / Workload Type</label>
              <select id="job-workload" class="select">
                <option value="matrix_multiply" selected>Matrix Multiplication (PyTorch · CUDA / CPU)</option>
                <option value="prime_search">Distributed Prime Search (CPU Partitions)</option>
                <option value="fibonacci">Fibonacci Deep Iteration (Sequential CPU)</option>
                <option value="custom_python">Custom Python Code (Sandboxed Subprocess)</option>
              </select>
            </div>

            <!-- Workload Specific Parameters -->
            <div id="workload-specific-fields" style="padding: var(--space-4); background: var(--bg-secondary); border-radius: var(--radius-md); border: 1px solid var(--border-subtle); margin-bottom: var(--space-4);">
              <!-- Will be updated dynamically -->
            </div>

            <!-- Resource Constraints -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4);">
              <div class="form-group">
                <label class="form-label" for="job-cpu-cores">Min CPU Cores</label>
                <input type="number" id="job-cpu-cores" class="input input-mono" min="1" max="64" value="1" required />
              </div>

              <div class="form-group">
                <label class="form-label" for="job-ram-gb">Min RAM (GB)</label>
                <input type="number" id="job-ram-gb" class="input input-mono" min="1" max="128" step="0.5" value="2" required />
              </div>
            </div>

            <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: var(--surface-elevated); border: 1px solid var(--border-color); border-radius: var(--radius-md); margin-bottom: var(--space-4);">
              <div>
                <div style="font-size: var(--text-sm); font-weight: 600; color: var(--text-primary);">Require Dedicated GPU Acceleration</div>
                <div style="font-size: var(--text-2xs); color: var(--text-muted);">Matches only providers equipped with NVIDIA CUDA / PyTorch GPUs</div>
              </div>
              <input type="checkbox" id="job-gpu-req" style="width: 18px; height: 18px; accent-color: var(--accent-cyan); cursor: pointer;" />
            </div>

            <!-- Real-time Cost & Compatibility Summary Card -->
            <div style="padding: var(--space-4); background: linear-gradient(135deg, var(--surface-primary), var(--surface-elevated)); border: 1px solid var(--border-color); border-radius: var(--radius-md);">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                  <div style="font-size: var(--text-xs); color: var(--text-muted); text-transform: uppercase;">Estimated Token Reservation</div>
                  <div style="font-size: var(--text-xl); font-weight: 700; font-family: var(--font-mono); color: var(--accent-cyan);" id="cost-estimate-val">
                    -- Tokens
                  </div>
                </div>

                <div style="text-align: right;">
                  <div style="font-size: var(--text-xs); color: var(--text-muted); text-transform: uppercase;">Compatible Providers</div>
                  <div style="font-size: var(--text-sm); font-weight: 600; font-family: var(--font-mono);" id="compatible-providers-val">
                    Calculating...
                  </div>
                </div>
              </div>

              <div id="balance-warning-msg" style="display: none; margin-top: 10px; font-size: var(--text-2xs); color: var(--status-error); background: var(--status-error-soft); padding: 4px 8px; border-radius: 4px;">
                ⚠️ Insufficient balance for reservation. Please top up your wallet.
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <button type="button" class="btn btn-outline" id="job-modal-cancel-btn">Cancel</button>
            <button type="submit" class="btn btn-primary" id="job-modal-submit-btn">
              Dispatch to Cluster
            </button>
          </div>
        </form>
      </div>
    </div>
  `;

  const closeBtn = document.getElementById('job-modal-close-btn');
  const cancelBtn = document.getElementById('job-modal-cancel-btn');
  const workloadSelect = document.getElementById('job-workload');
  const specificContainer = document.getElementById('workload-specific-fields');
  const form = document.getElementById('job-launch-form');
  const submitBtn = document.getElementById('job-modal-submit-btn');
  const cpuInput = document.getElementById('job-cpu-cores');
  const ramInput = document.getElementById('job-ram-gb');
  const gpuCheckbox = document.getElementById('job-gpu-req');
  const estimateDisplay = document.getElementById('cost-estimate-val');
  const compatibleDisplay = document.getElementById('compatible-providers-val');
  const balanceWarning = document.getElementById('balance-warning-msg');

  function renderSpecificFields() {
    const val = workloadSelect.value;
    if (val === 'matrix_multiply') {
      specificContainer.innerHTML = `
        <div class="form-group" style="margin-bottom: 0;">
          <div style="display: flex; justify-content: space-between;">
            <label class="form-label" for="matrix-size">Matrix Dimension (N x N)</label>
            <span style="font-family: var(--font-mono); font-size: var(--text-xs); color: var(--accent-cyan);" id="matrix-size-display">400 x 400</span>
          </div>
          <input type="range" id="matrix-size" min="100" max="1200" step="50" value="400" style="width: 100%; accent-color: var(--accent-cyan);" />
          <div class="form-help">Executes in 4 partitioned sub-blocks with periodic checkpointing.</div>
        </div>
      `;
      const slider = document.getElementById('matrix-size');
      const display = document.getElementById('matrix-size-display');
      slider.addEventListener('input', () => {
        display.textContent = `${slider.value} x ${slider.value}`;
        updateEstimates();
      });
    } else if (val === 'prime_search') {
      specificContainer.innerHTML = `
        <div class="form-group" style="margin-bottom: 0;">
          <label class="form-label" for="prime-limit">Upper Search Limit (N)</label>
          <input type="number" id="prime-limit" class="input input-mono" value="50000" min="100" max="5000000" step="5000" required />
          <div class="form-help">Scans for prime numbers across 4 partitions with checkpoint recovery.</div>
        </div>
      `;
      document.getElementById('prime-limit').addEventListener('input', updateEstimates);
    } else if (val === 'fibonacci') {
      specificContainer.innerHTML = `
        <div class="form-group" style="margin-bottom: 0;">
          <label class="form-label" for="fibo-index">Fibonacci Calculation Index (N)</label>
          <input type="number" id="fibo-index" class="input input-mono" value="2000" min="50" max="50000" step="100" required />
          <div class="form-help">Calculates high-precision integer Fibonacci values with checkpoints.</div>
        </div>
      `;
      document.getElementById('fibo-index').addEventListener('input', updateEstimates);
    } else if (val === 'custom_python') {
      specificContainer.innerHTML = `
        <div class="form-group">
          <label class="form-label" for="custom-py-code">Python Execution Script</label>
          <textarea id="custom-py-code" class="textarea textarea-mono" spellcheck="false"># Nexora Workload Script
import sys, math

print("Initiating custom compute execution...")
total = sum(math.sqrt(i) for i in range(1, 100000))
print(f"Computed total checksum: {total:.4f}")
</textarea>
        </div>
        <div class="form-group" style="margin-bottom: 0;">
          <label class="form-label" for="py-timeout">Execution Timeout (Seconds)</label>
          <input type="number" id="py-timeout" class="input input-mono" value="20" min="5" max="180" />
        </div>
      `;
      document.getElementById('custom-py-code').addEventListener('input', updateEstimates);
    }
    updateEstimates();
  }

  function updateEstimates() {
    const workload = workloadSelect.value;
    const cpu = Number(cpuInput.value) || 1;
    const ram = Number(ramInput.value) || 1;
    const gpuReq = gpuCheckbox.checked;

    // Filter matching providers
    const matching = onlineProviders.filter(p => {
      if (p.cpu_cores < cpu) return false;
      if (p.ram_gb < ram) return false;
      if (gpuReq && (!p.gpu_name || p.gpu_memory_gb <= 0)) return false;
      return true;
    });

    if (matching.length === 0) {
      compatibleDisplay.innerHTML = `<span style="color: var(--status-error);">0 Nodes Available</span>`;
    } else {
      compatibleDisplay.innerHTML = `<span style="color: var(--status-success);">${matching.length} Available Node${matching.length > 1 ? 's' : ''}</span>`;
    }

    // Backend estimation formula:
    // hours = max(requirements.expected_runtime_hours, 0.01)
    // multiplier = 8 if gpu else 2 (or 10 if torch in python_code)
    // tokens = max(1, round(hours * 60 * multiplier + max(0, ram - 4) * 0.1))
    let expectedHours = 0.05;
    let multiplier = gpuReq ? 8 : 2;
    if (workload === 'custom_python') {
      const code = document.getElementById('custom-py-code')?.value || '';
      if (code.includes('torch')) multiplier = 10;
    }

    const estimatedTokens = Math.max(1, Math.round(expectedHours * 60 * multiplier + Math.max(0, ram - 4) * 0.1));
    estimateDisplay.textContent = `${estimatedTokens} Tokens`;

    if (userBalance < estimatedTokens) {
      balanceWarning.style.display = 'block';
      submitBtn.disabled = true;
    } else {
      balanceWarning.style.display = 'none';
      submitBtn.disabled = matching.length === 0;
    }

    return { estimatedTokens, matching };
  }

  workloadSelect.addEventListener('change', renderSpecificFields);
  cpuInput.addEventListener('input', updateEstimates);
  ramInput.addEventListener('input', updateEstimates);
  gpuCheckbox.addEventListener('change', updateEstimates);

  closeBtn.addEventListener('click', () => { modalWrap.innerHTML = ''; });
  cancelBtn.addEventListener('click', () => { modalWrap.innerHTML = ''; });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const { estimatedTokens, matching } = updateEstimates();
    if (matching.length === 0) {
      showToast('No compatible online provider matches the requested CPU/RAM/GPU requirements.', 'error');
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Scheduling & Reserving Tokens...';

    const workload = workloadSelect.value;
    const name = document.getElementById('job-name').value.trim();
    const requirements = {
      cpu_cores: Number(cpuInput.value),
      ram_gb: Number(ramInput.value),
      gpu_required: gpuCheckbox.checked,
      expected_runtime_hours: 0.05
    };

    if (workload === 'matrix_multiply') {
      requirements.matrix_size = Number(document.getElementById('matrix-size').value);
    } else if (workload === 'prime_search') {
      requirements.matrix_size = Number(document.getElementById('prime-limit').value);
    } else if (workload === 'fibonacci') {
      requirements.matrix_size = Number(document.getElementById('fibo-index').value);
    } else if (workload === 'custom_python') {
      requirements.python_code = document.getElementById('custom-py-code').value;
      requirements.timeout_seconds = Number(document.getElementById('py-timeout').value) || 20;
      requirements.file_name = `${name.replace(/\s+/g, '_')}.py`;
    }

    try {
      const job = await apiRequest('/jobs', {
        method: 'POST',
        body: JSON.stringify({
          name,
          workload,
          requirements
        })
      });

      showToast(`Workload "${job.name}" dispatched! Status: ${job.status}`, 'success');
      await refreshAll();
      modalWrap.innerHTML = '';
      window.location.hash = '#/jobs';
    } catch (err) {
      showToast(err.message || 'Job submission failed', 'error');
      submitBtn.disabled = false;
      submitBtn.textContent = 'Dispatch to Cluster';
    }
  });

  // Initial render
  renderSpecificFields();
}
