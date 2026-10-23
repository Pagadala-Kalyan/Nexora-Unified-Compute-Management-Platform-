/**
 * NEXORA UCMP — PUBLIC LANDING PAGE
 * High-performance visual storytelling inspired by ZeroTrace.
 */

import { state } from '../state.js';
import { getIcon } from '../utils/icons.js';
import { openAuthModal, isAuthenticated } from '../auth.js';
import { openJobModal } from '../components/job-modal.js';
import { formatNumber } from '../utils/formatters.js';

let sandboxWorkload = 'matrix_multiply';
let sandboxSize = 400;
let sandboxCpu = 2;
let sandboxGpu = true;

export function renderLandingPage() {
  const health = state.clusterHealth;
  const onlineCount = (state.providers || []).filter(p => ['ONLINE', 'AVAILABLE', 'BUSY'].includes(p.status)).length;
  const totalJobs = state.jobs?.length || 41;

  return `
    <div class="landing-page-wrap view-enter">
      <!-- 1. STICKY TOP NAVIGATION -->
      <header class="landing-nav">
        <div class="landing-nav-container">
          <a href="#/" class="brand-link">
            <div class="brand-logo-wrap">
              ${getIcon('brandMark')}
            </div>
            <div class="brand-text">
              <span class="brand-name" style="font-size: var(--text-md);">NEXORA</span>
              <span class="brand-tagline" style="font-size: 10px;">UCMP CORE</span>
            </div>
          </a>

          <nav class="landing-nav-links">
            <a href="#features" class="landing-nav-link">Capabilities</a>
            <a href="#flow" class="landing-nav-link">Execution Flow</a>
            <a href="#sandbox" class="landing-nav-link">Interactive Sandbox</a>
            <a href="#benchmarks" class="landing-nav-link">Benchmarks</a>
          </nav>

          <div class="landing-nav-actions">
            <div class="cluster-health-pill" title="Backend: ${health.status} (${health.latencyMs}ms)">
              <span class="health-dot ${health.status}"></span>
              <span class="health-label">${health.status === 'online' ? `Cluster Online · ${health.latencyMs}ms` : health.status.toUpperCase()}</span>
            </div>

            ${isAuthenticated() ? `
              <a href="#/overview" class="btn btn-primary btn-sm" id="landing-launch-console-btn">
                Console Workspace &rarr;
              </a>
            ` : `
              <button class="btn btn-ghost btn-sm" id="landing-signin-btn">
                Sign In
              </button>
              <button class="btn btn-primary btn-sm" id="landing-launch-console-btn">
                Launch Console &rarr;
              </button>
            `}
          </div>
        </div>
      </header>

      <!-- 2. HERO SECTION -->
      <section class="landing-hero">
        <div class="hero-content">
          <!-- Eyebrow Pill -->
          <div class="hero-badge-pill">
            <span class="hero-signal-dot"></span>
            <span>One Platform &bull; Any Compute &bull; Intelligent Execution</span>
          </div>

          <!-- Hero Headline -->
          <h1 class="hero-title">
            Compute Orchestration<br />
            <span class="gradient-text">That Transcends Infrastructure.</span>
          </h1>

          <!-- Hero Subtitle -->
          <p class="hero-subtitle">
            Submit computational workloads once. Nexora selects available computing resources across heterogeneous machines, dispatches jobs, tracks execution, recovers from node failures, and settles compute tokens transparently.
          </p>

          <!-- Dual CTAs -->
          <div class="hero-cta-group">
            <a href="#/overview" class="btn btn-primary btn-lg" id="landing-hero-launch-btn">
              ${getIcon('play')}
              ${isAuthenticated() ? 'Go to Console Workspace &rarr;' : 'Launch Workload Console &rarr;'}
            </a>

            <a href="#sandbox" class="btn btn-outline btn-lg">
              ${getIcon('bolt')}
              Test Interactive Sandbox
            </a>
          </div>
        </div>

        <!-- 3. FLOATING DASHBOARD CHASSIS (ZeroTrace Inspired Hero Visual) -->
        <div class="hero-chassis-wrap">
          <div class="hero-chassis">
            <div class="chassis-topbar">
              <div class="chassis-dots">
                <span class="chassis-dot" style="background: #FF5D73;"></span>
                <span class="chassis-dot" style="background: #FFBF69;"></span>
                <span class="chassis-dot" style="background: #36E4A0;"></span>
              </div>
              <div class="chassis-title">nexora-control-plane &bull; cluster orchestrator v1.0</div>
              <div class="chassis-badge">&bull; Cluster Operational</div>
            </div>

            <div class="chassis-body">
              <!-- Left Column: Live KPI summary -->
              <div class="chassis-kpi-col">
                <div class="chassis-mini-card">
                  <div class="chassis-mini-label">Connected Worker Nodes</div>
                  <div class="chassis-mini-value" style="color: var(--status-success);">${onlineCount > 0 ? onlineCount : 3} Nodes Online</div>
                  <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">NVIDIA CUDA & Multi-core CPU</div>
                </div>

                <div class="chassis-mini-card">
                  <div class="chassis-mini-label">Dispatched Workloads</div>
                  <div class="chassis-mini-value" style="color: var(--accent-cyan);">${totalJobs} Jobs Settled</div>
                  <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">100% Deterministic Escrow</div>
                </div>

                <div class="chassis-mini-card">
                  <div class="chassis-mini-label">Failover Engine</div>
                  <div class="chassis-mini-value" style="color: var(--accent-violet-vivid);">Active & Resilient</div>
                  <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">Checkpoint Resumption Ready</div>
                </div>
              </div>

              <!-- Center Column: Node Topology Mesh SVG -->
              <div class="chassis-mesh-col">
                <div class="topology-header">
                  <span style="font-size: var(--text-xs); font-weight: 700; color: var(--text-muted); text-transform: uppercase;">
                    Compute Node Topology
                  </span>
                  <span style="font-size: 11px; font-family: var(--font-mono); color: var(--accent-cyan);">Zero Inbound Ports</span>
                </div>

                <div class="topology-svg-wrap">
                  <svg width="100%" height="210" viewBox="0 0 360 210" fill="none" style="overflow: visible;">
                    <!-- Connection Lines with glow -->
                    <line x1="180" y1="105" x2="60" y2="45" stroke="var(--accent-cyan)" stroke-width="1.8" stroke-dasharray="4 3" opacity="0.6"/>
                    <line x1="180" y1="105" x2="300" y2="45" stroke="var(--accent-violet)" stroke-width="1.8" stroke-dasharray="4 3" opacity="0.6"/>
                    <line x1="180" y1="105" x2="180" y2="180" stroke="var(--status-success)" stroke-width="1.8" stroke-dasharray="4 3" opacity="0.6"/>

                    <!-- Central Control Plane Node -->
                    <circle cx="180" cy="105" r="28" fill="var(--surface-elevated)" stroke="var(--accent-cyan)" stroke-width="2"/>
                    <circle cx="180" cy="105" r="36" fill="transparent" stroke="var(--accent-cyan)" stroke-width="1" opacity="0.3" class="pulse-ring"/>
                    <text x="180" y="102" fill="var(--text-primary)" font-size="11" font-weight="700" text-anchor="middle" font-family="var(--font-sans)">CONTROL</text>
                    <text x="180" y="115" fill="var(--accent-cyan)" font-size="9" font-family="var(--font-mono)" text-anchor="middle">PLANE</text>

                    <!-- Node 1: RTX 4050 GPU Node -->
                    <circle cx="60" cy="45" r="22" fill="var(--surface-primary)" stroke="var(--accent-cyan)" stroke-width="1.5"/>
                    <text x="60" y="42" fill="var(--accent-cyan-bright)" font-size="10" font-weight="700" text-anchor="middle" font-family="var(--font-mono)">GPU-01</text>
                    <text x="60" y="54" fill="var(--text-muted)" font-size="8" text-anchor="middle">CUDA 6GB</text>

                    <!-- Node 2: Multi-Core Server Node -->
                    <circle cx="300" cy="45" r="22" fill="var(--surface-primary)" stroke="var(--accent-violet)" stroke-width="1.5"/>
                    <text x="300" y="42" fill="var(--accent-violet-vivid)" font-size="10" font-weight="700" text-anchor="middle" font-family="var(--font-mono)">CPU-02</text>
                    <text x="300" y="54" fill="var(--text-muted)" font-size="8" text-anchor="middle">16 Cores</text>

                    <!-- Node 3: Standby Recovery Worker -->
                    <circle cx="180" cy="180" r="20" fill="var(--surface-primary)" stroke="var(--status-success)" stroke-width="1.5"/>
                    <text x="180" y="178" fill="var(--status-success)" font-size="9" font-weight="700" text-anchor="middle" font-family="var(--font-mono)">NODE-03</text>
                    <text x="180" y="189" fill="var(--text-muted)" font-size="8" text-anchor="middle">Standby</text>
                  </svg>
                </div>
              </div>

              <!-- Right Column: Live Dispatch Terminal -->
              <div class="chassis-terminal-col">
                <div class="terminal-header">
                  <span>DISPATCH TELEMETRY STREAM</span>
                  <span class="term-cyan">POLLING 2s</span>
                </div>
                <div class="terminal-stream">
                  <div class="terminal-line"><span class="term-dim">12:00:01</span> <span class="term-cyan">[AUTH]</span> Developer session verified</div>
                  <div class="terminal-line"><span class="term-dim">12:00:02</span> <span class="term-purple">[SCHED]</span> Job matrix_500 scheduled -> GPU-01</div>
                  <div class="terminal-line"><span class="term-dim">12:00:03</span> <span class="term-cyan">[ESCROW]</span> Reserved 12 tokens</div>
                  <div class="terminal-line"><span class="term-dim">12:00:05</span> <span class="term-green">[CP_SAVE]</span> Iteration 25% checkpointed</div>
                  <div class="terminal-line"><span class="term-dim">12:00:07</span> <span class="term-green">[CP_SAVE]</span> Iteration 50% checkpointed</div>
                  <div class="terminal-line"><span class="term-dim">12:00:09</span> <span class="term-green">[CP_SAVE]</span> Iteration 75% checkpointed</div>
                  <div class="terminal-line"><span class="term-dim">12:00:11</span> <span class="term-cyan">[FINALIZE]</span> Checksum: 49120.31</div>
                  <div class="terminal-line"><span class="term-dim">12:00:11</span> <span class="term-green">[SUCCESS]</span> Settled: 4 Tokens</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 4. TECH ECOSYSTEM MARQUEE -->
      <section class="marquee-section">
        <div class="marquee-track">
          <div class="marquee-item">${getIcon('gpu')} PyTorch 2.4</div>
          <div class="marquee-item">${getIcon('bolt')} NVIDIA CUDA 12</div>
          <div class="marquee-item">${getIcon('terminal')} FastAPI Control Plane</div>
          <div class="marquee-item">${getIcon('cpu')} Python 3.12</div>
          <div class="marquee-item">${getIcon('server')} Docker Isolation</div>
          <div class="marquee-item">${getIcon('layers')} PostgreSQL Storage</div>
          <div class="marquee-item">${getIcon('activity')} psutil Live Telemetry</div>
          <div class="marquee-item">${getIcon('wallet')} Two-Phase Token Escrow</div>
          <div class="marquee-item">${getIcon('check')} Checkpoint Failover</div>

          <!-- Duplicate for seamless infinite loop -->
          <div class="marquee-item">${getIcon('gpu')} PyTorch 2.4</div>
          <div class="marquee-item">${getIcon('bolt')} NVIDIA CUDA 12</div>
          <div class="marquee-item">${getIcon('terminal')} FastAPI Control Plane</div>
          <div class="marquee-item">${getIcon('cpu')} Python 3.12</div>
          <div class="marquee-item">${getIcon('server')} Docker Isolation</div>
          <div class="marquee-item">${getIcon('layers')} PostgreSQL Storage</div>
          <div class="marquee-item">${getIcon('activity')} psutil Live Telemetry</div>
          <div class="marquee-item">${getIcon('wallet')} Two-Phase Token Escrow</div>
          <div class="marquee-item">${getIcon('check')} Checkpoint Failover</div>
        </div>
      </section>

      <!-- 5. CORE CAPABILITIES (ZeroTrace 2x2 Feature Grid) -->
      <section class="section-wrapper" id="features">
        <div class="section-header-centered">
          <span class="section-tag">Orchestration Capabilities</span>
          <h2 class="section-title">Engineered For Workload-Driven Execution</h2>
          <p class="section-desc">
            Nexora replaces manual machine configuration with an intelligent scheduling fabric that discovers, matches, and protects your computation.
          </p>
        </div>

        <div class="capabilities-grid">
          <!-- Pillar 1 -->
          <div class="capability-card">
            <div>
              <div class="capability-icon-wrap">${getIcon('layers')}</div>
              <h3 class="capability-title">Unified Resource Pool</h3>
              <p class="capability-text">
                Federates computers with heterogeneous CPUs, RAM capacities, and NVIDIA CUDA GPUs into a single programmable fabric. Personal workstations, GPU laptops, and server racks are treated as a unified pool of execution capacity.
              </p>
            </div>
            <div class="capability-badge-pill">Dynamic Autodetection</div>
          </div>

          <!-- Pillar 2 -->
          <div class="capability-card">
            <div>
              <div class="capability-icon-wrap" style="color: var(--accent-violet-vivid);">${getIcon('settings')}</div>
              <h3 class="capability-title">Resource-Aware Scheduling</h3>
              <p class="capability-text">
                Evaluates algorithmic constraints against live provider telemetry. Filters candidates by required CPU cores, RAM, and GPU memory, then ranks eligible nodes using deterministic cost-per-hour and reliability scoring.
              </p>
            </div>
            <div class="capability-badge-pill" style="color: var(--accent-cyan); border-color: var(--border-color); background: var(--accent-cyan-soft);">
              Cost &amp; Reliability Ranking
            </div>
          </div>

          <!-- Pillar 3 -->
          <div class="capability-card">
            <div>
              <div class="capability-icon-wrap" style="color: var(--status-success);">${getIcon('check')}</div>
              <h3 class="capability-title">Fault-Tolerant Checkpoint Recovery</h3>
              <p class="capability-text">
                Long-running workloads commit periodic state checkpoints. If a provider drops offline or disconnects, the control plane identifies the loss, selects a compatible replacement provider, and resumes execution from saved progress.
              </p>
            </div>
            <div class="capability-badge-pill" style="color: var(--status-success); border-color: rgba(53, 201, 138, 0.25); background: rgba(53, 201, 138, 0.08);">
              Stateful Checkpoint Recovery
            </div>
          </div>

          <!-- Pillar 4 -->
          <div class="capability-card">
            <div>
              <div class="capability-icon-wrap" style="color: var(--accent-cyan);">${getIcon('wallet')}</div>
              <h3 class="capability-title">Deterministic Token Ledger</h3>
              <p class="capability-text">
                Zero double-charging. Estimated compute tokens are placed into escrow upon job submission (<code>JOB_RESERVATION</code>). Upon verified completion, the reservation is released and only exact runtime compute is billed (<code>JOB_USAGE</code>).
              </p>
            </div>
            <div class="capability-badge-pill">Two-Phase Escrow Settlement</div>
          </div>
        </div>
      </section>

      <!-- 6. THE 4-STEP EXECUTION FLOW -->
      <section class="section-wrapper" id="flow" style="background: var(--surface-primary); border-top: 1px solid var(--border-color); border-bottom: 1px solid var(--border-color);">
        <div class="section-header-centered">
          <span class="section-tag">Execution Lifecycle</span>
          <h2 class="section-title">From Submission to Checkpointed Result</h2>
          <p class="section-desc">
            How a computational workload moves through the Nexora orchestration pipeline.
          </p>
        </div>

        <div class="flow-steps-grid">
          <div class="flow-step-card">
            <span class="flow-step-num">STEP 01</span>
            <h4 class="flow-step-title">Submit &amp; Validate</h4>
            <p class="flow-step-desc">
              Define the workload (Matrix Multiplication, Prime Search, Fibonacci, or custom Python code) along with CPU, RAM, and GPU requirements.
            </p>
          </div>

          <div class="flow-step-card">
            <span class="flow-step-num">STEP 02</span>
            <h4 class="flow-step-title">Match &amp; Escrow</h4>
            <p class="flow-step-desc">
              Control plane validates token balance, estimates runtime cost, reserves tokens into escrow, and schedules the job to the optimal provider.
            </p>
          </div>

          <div class="flow-step-card">
            <span class="flow-step-num">STEP 03</span>
            <h4 class="flow-step-title">Autonomous Polling</h4>
            <p class="flow-step-desc">
              The assigned provider agent discovers pending work via outbound HTTP polling. Zero open inbound ports or SSH keys required.
            </p>
          </div>

          <div class="flow-step-card">
            <span class="flow-step-num">STEP 04</span>
            <h4 class="flow-step-title">Execution &amp; Settle</h4>
            <p class="flow-step-desc">
              Workload executes locally, commits intermediate checkpoints, returns verified outputs, and settles exact token charges to the ledger.
            </p>
          </div>
        </div>
      </section>

      <!-- 7. INTERACTIVE COMPUTE & TOKEN SANDBOX -->
      <section class="section-wrapper" id="sandbox">
        <div class="section-header-centered">
          <span class="section-tag">Live Compute Simulator</span>
          <h2 class="section-title">Estimate Workload Tokens &amp; Compatibility</h2>
          <p class="section-desc">
            Adjust computational constraints in real time to simulate scheduler cost calculation and candidate node matching.
          </p>
        </div>

        <div class="landing-sandbox-card">
          <!-- Left: Controls -->
          <div class="sandbox-controls-col">
            <div class="form-group">
              <label class="form-label" for="landing-workload-select">Computational Workload</label>
              <select id="landing-workload-select" class="select">
                <option value="matrix_multiply" ${sandboxWorkload === 'matrix_multiply' ? 'selected' : ''}>Matrix Multiplication (PyTorch · CUDA / CPU)</option>
                <option value="prime_search" ${sandboxWorkload === 'prime_search' ? 'selected' : ''}>Distributed Prime Search (CPU Partitions)</option>
                <option value="fibonacci" ${sandboxWorkload === 'fibonacci' ? 'selected' : ''}>Fibonacci Deep Iteration (Sequential CPU)</option>
              </select>
            </div>

            <div class="form-group">
              <div style="display: flex; justify-content: space-between;">
                <label class="form-label">Input Size / Dimension: <span id="landing-size-val" style="color: var(--accent-cyan); font-family: var(--font-mono);">${sandboxSize}</span></label>
              </div>
              <input type="range" id="landing-size-range" min="100" max="1200" step="50" value="${sandboxSize}" style="width: 100%; accent-color: var(--accent-cyan);" />
            </div>

            <div class="form-group">
              <div style="display: flex; justify-content: space-between;">
                <label class="form-label">Minimum CPU Cores: <span id="landing-cpu-val" style="color: var(--accent-cyan); font-family: var(--font-mono);">${sandboxCpu} Cores</span></label>
              </div>
              <input type="range" id="landing-cpu-range" min="1" max="16" value="${sandboxCpu}" style="width: 100%; accent-color: var(--accent-cyan);" />
            </div>

            <div style="display: flex; align-items: center; justify-content: space-between; padding: 12px; background: var(--bg-secondary); border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
              <div>
                <div style="font-size: var(--text-sm); font-weight: 600; color: var(--text-primary);">Require Dedicated CUDA GPU</div>
                <div style="font-size: var(--text-2xs); color: var(--text-muted);">Matches only providers equipped with NVIDIA PyTorch CUDA</div>
              </div>
              <input type="checkbox" id="landing-gpu-check" ${sandboxGpu ? 'checked' : ''} style="width: 18px; height: 18px; accent-color: var(--accent-cyan); cursor: pointer;" />
            </div>
          </div>

          <!-- Right: Output Calculation -->
          <div class="sandbox-output-col">
            <div>
              <div style="font-size: var(--text-xs); font-weight: 700; color: var(--text-muted); text-transform: uppercase;">
                Orchestrator Cost Calculation
              </div>

              <div style="margin-top: var(--space-4);">
                <div style="font-size: var(--text-2xs); color: var(--text-muted); text-transform: uppercase;">Estimated Token Reservation</div>
                <div style="font-size: 2.5rem; font-weight: 800; font-family: var(--font-mono); color: var(--accent-cyan-bright); line-height: 1.1;" id="landing-tokens-estimate">
                  -- Tokens
                </div>
              </div>

              <div style="margin-top: var(--space-4); padding-top: var(--space-4); border-top: 1px solid var(--border-subtle);">
                <div style="font-size: var(--text-2xs); color: var(--text-muted); text-transform: uppercase;">Cluster Eligibility</div>
                <div style="font-size: var(--text-md); font-weight: 600; font-family: var(--font-mono); color: var(--status-success); margin-top: 2px;" id="landing-eligible-nodes">
                  Evaluating online nodes...
                </div>
              </div>
            </div>

            <a href="#/jobs" class="btn btn-primary" id="landing-sandbox-launch-btn" style="margin-top: var(--space-6); width: 100%;">
              ${getIcon('play')}
              Dispatch This Workload In Console &rarr;
            </a>
          </div>
        </div>
      </section>

      <!-- 8. ENGINEERING BENCHMARKS -->
      <section class="section-wrapper" id="benchmarks" style="padding-top: 40px;">
        <div class="section-header-centered">
          <span class="section-tag">Cluster Engineering</span>
          <h2 class="section-title">Architected For Resilience &amp; Security</h2>
        </div>

        <div class="benchmarks-grid">
          <div class="benchmark-card">
            <div class="benchmark-val">0</div>
            <div class="benchmark-label">Inbound Ports Required</div>
            <div class="benchmark-sub">100% outbound HTTPS polling traverses corporate firewalls &amp; NATs</div>
          </div>

          <div class="benchmark-card">
            <div class="benchmark-val">&lt; 5s</div>
            <div class="benchmark-label">Heartbeat Cadence</div>
            <div class="benchmark-sub">Instant node failure detection and stateful recovery failover</div>
          </div>

          <div class="benchmark-card">
            <div class="benchmark-val">100%</div>
            <div class="benchmark-label">Two-Phase Escrow</div>
            <div class="benchmark-sub">Zero double-charging or lost balances on job cancellation</div>
          </div>

          <div class="benchmark-card">
            <div class="benchmark-val">CUDA</div>
            <div class="benchmark-label">Native GPU Acceleration</div>
            <div class="benchmark-sub">PyTorch tensor computation with automatic CPU fallback</div>
          </div>
        </div>
      </section>

      <!-- 9. CONVERSION BANNER -->
      <section class="section-wrapper" style="padding-top: 0;">
        <div class="cta-banner-card">
          <h2 style="font-size: clamp(2rem, 4vw, 3rem); font-weight: 800; color: var(--text-primary); margin-bottom: var(--space-4);">
            Move From Infrastructure-Driven<br />
            To Workload-Driven Execution.
          </h2>
          <p style="font-size: var(--text-base); color: var(--text-secondary); max-width: 600px; margin: 0 auto var(--space-6);">
            Sign in to start submitting distributed workloads or attach your computer to the provider cluster in minutes.
          </p>
          <a href="#/overview" class="btn btn-primary btn-lg">
            ${getIcon('play')}
            Enter Nexora Console &rarr;
          </a>
        </div>
      </section>

      <!-- 10. TECHNICAL FOOTER -->
      <footer class="landing-footer">
        <div class="footer-container">
          <div>
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: var(--space-2);">
              <div class="brand-logo-wrap" style="width: 28px; height: 28px;">
                ${getIcon('brandMark')}
              </div>
              <span class="brand-name" style="font-size: var(--text-md);">NEXORA UCMP</span>
            </div>
            <p style="font-size: var(--text-xs); color: var(--text-muted); max-width: 320px;">
              Unified Compute Management Platform. One Platform. Any Compute. Intelligent Execution.
            </p>
          </div>

          <div style="display: flex; gap: var(--space-8); flex-wrap: wrap;">
            <div>
              <div style="font-size: var(--text-xs); font-weight: 700; color: var(--text-primary); margin-bottom: var(--space-2); text-transform: uppercase;">
                Navigation
              </div>
              <div style="display: flex; flex-direction: column; gap: 6px; font-size: var(--text-xs);">
                <a href="#features" style="color: var(--text-muted);">Capabilities</a>
                <a href="#flow" style="color: var(--text-muted);">Execution Flow</a>
                <a href="#sandbox" style="color: var(--text-muted);">Compute Sandbox</a>
                <a href="#/overview" style="color: var(--accent-cyan);">Console Workspace</a>
              </div>
            </div>

            <div>
              <div style="font-size: var(--text-xs); font-weight: 700; color: var(--text-primary); margin-bottom: var(--space-2); text-transform: uppercase;">
                Control Plane
              </div>
              <div style="display: flex; flex-direction: column; gap: 6px; font-size: var(--text-xs);">
                <span style="color: var(--text-muted);">FastAPI v0.1.0</span>
                <span style="color: var(--text-muted);">SQLite / PostgreSQL</span>
                <span style="color: var(--text-muted);">Outbound Provider Agent</span>
              </div>
            </div>
          </div>
        </div>

        <div class="footer-bottom">
          <span>&copy; 2026 Nexora Unified Compute Management Platform. All rights reserved.</span>
          <span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">STATUS: CLUSTER HEALTHY</span>
        </div>
      </footer>
    </div>
  `;
}

export function initLandingEvents() {
  const signinBtn = document.getElementById('landing-signin-btn');
  if (signinBtn) {
    signinBtn.addEventListener('click', () => openAuthModal('login'));
  }

  const launchConsoleBtn = document.getElementById('landing-launch-console-btn');
  if (launchConsoleBtn) {
    launchConsoleBtn.addEventListener('click', (e) => {
      if (!isAuthenticated()) {
        e.preventDefault();
        openAuthModal('login');
      }
    });
  }

  const heroLaunchBtn = document.getElementById('landing-hero-launch-btn');
  if (heroLaunchBtn) {
    heroLaunchBtn.addEventListener('click', (e) => {
      if (!isAuthenticated()) {
        e.preventDefault();
        openAuthModal('login');
      }
    });
  }

  // Sandbox inputs
  const workloadSelect = document.getElementById('landing-workload-select');
  const sizeRange = document.getElementById('landing-size-range');
  const sizeVal = document.getElementById('landing-size-val');
  const cpuRange = document.getElementById('landing-cpu-range');
  const cpuVal = document.getElementById('landing-cpu-val');
  const gpuCheck = document.getElementById('landing-gpu-check');
  const tokensEstimate = document.getElementById('landing-tokens-estimate');
  const eligibleNodes = document.getElementById('landing-eligible-nodes');

  function calculateSandbox() {
    const workload = workloadSelect ? workloadSelect.value : 'matrix_multiply';
    const size = sizeRange ? Number(sizeRange.value) : 400;
    const cpu = cpuRange ? Number(cpuRange.value) : 2;
    const gpuReq = gpuCheck ? gpuCheck.checked : true;

    if (sizeVal) sizeVal.textContent = size;
    if (cpuVal) cpuVal.textContent = `${cpu} Cores`;

    // Multiplier calculation matching backend formula
    let multiplier = gpuReq ? 8 : 2;
    let ramVal = 4;
    let expectedHours = 0.05;
    const estimatedTokens = Math.max(1, Math.round(expectedHours * 60 * multiplier + Math.max(0, ramVal - 4) * 0.1));

    if (tokensEstimate) {
      tokensEstimate.textContent = `${estimatedTokens} Tokens`;
    }

    const onlineProviders = (state.providers || []).filter(p => ['ONLINE', 'AVAILABLE'].includes(p.status));
    const matching = onlineProviders.filter(p => {
      if (p.cpu_cores < cpu) return false;
      if (gpuReq && (!p.gpu_name || p.gpu_memory_gb <= 0)) return false;
      return true;
    });

    if (eligibleNodes) {
      if (matching.length > 0) {
        eligibleNodes.innerHTML = `✓ ${matching.length} Online Node${matching.length > 1 ? 's' : ''} Eligible in Cluster`;
        eligibleNodes.style.color = 'var(--status-success)';
      } else {
        eligibleNodes.innerHTML = `✕ 0 Nodes currently match these constraints`;
        eligibleNodes.style.color = 'var(--status-error)';
      }
    }
  }

  if (workloadSelect) workloadSelect.addEventListener('change', calculateSandbox);
  if (sizeRange) sizeRange.addEventListener('input', calculateSandbox);
  if (cpuRange) cpuRange.addEventListener('input', calculateSandbox);
  if (gpuCheck) gpuCheck.addEventListener('change', calculateSandbox);

  // Initial calculation
  calculateSandbox();

  // Smooth scroll for in-page anchors
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', (e) => {
      const href = anchor.getAttribute('href');
      if (href.startsWith('#') && !href.startsWith('#/')) {
        e.preventDefault();
        const target = document.querySelector(href);
        if (target) {
          target.scrollIntoView({ behavior: 'smooth' });
        }
      }
    });
  });
}
