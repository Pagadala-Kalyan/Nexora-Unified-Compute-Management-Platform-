# Nexora UCMP — Frontend Console

**Tagline:** One Platform. Any Compute. Intelligent Execution.

A modern, high-performance web interface for the **Nexora Unified Compute Management Platform (UCMP)** built purely with **HTML5, CSS3, and Vanilla JavaScript (ES Modules)**. Zero build steps, zero bloated dependencies, ultra-fast loading, and direct connection to the FastAPI control plane.

---

## Features & Capabilities

* **Futuristic Compute Intelligence Design**:
  * Deep black & graphite themes with electric cyan and vivid violet luminous accents.
  * 4 selectable themes: **Palette A (Quantum Neon)**, **Palette B (Cyberpunk Obsidian)**, **Palette C (Deep Space Blue)**, and **Palette D (Arctic Light)**.
  * Micro-interactions, pulse rings for executing nodes, and smooth layout transitions.
* **Overview Dashboard**:
  * Real-time KPI summary cards (Total Jobs, Active Workloads, Available Providers, Token Balance).
  * Pure SVG Donut Gauges for cluster hardware telemetry (CPU, RAM, GPU utilization).
  * Recent executions list and live checkpoint activity feed.
* **Compute Jobs**:
  * Search, multi-criteria filtering (status, algorithm workload), and sorting.
  * Real-time progress tracking for running and recovering workloads.
  * Emergency **"Stop All Active Jobs"** cluster safeguard.
  * Deep slide-out **Job Inspection Drawer** displaying execution timeline, checkpoint history, output JSON/stdout, and cancellation controls.
* **Workload Launch Modal**:
  * Dynamic parameters for `matrix_multiply`, `prime_search`, `fibonacci`, and `custom_python`.
  * Real-time token reservation cost estimation matching control-plane formula.
  * Live candidate provider compatibility checking before submission.
* **Compute Providers Fleet**:
  * Node cards with hardware specifications: CPU cores, RAM GB, GPU model, VRAM capacity, CUDA support.
  * Real-time heartbeat health indicators (Online, Busy, Offline).
* **Resource Pool & Matcher**:
  * Aggregated cluster fabric capacity (pooled CPU cores, cluster RAM, GPU VRAM).
  * Interactive workload compatibility sandbox with sliders to simulate scheduler dispatch.
* **Wallet & Token Ledger**:
  * Two-phase token model tracking: Available Balance, In-Flight Reserved Tokens, and Settled Usage.
  * Instant token purchase packages (`Starter`, `Standard`, `Compute Pro`).
  * Demo credit card top-up simulation.
  * 50-entry chronological audit ledger of all wallet transactions.
* **Platform Analytics**:
  * Success rate %, total volume, and node recovery failover counter.
  * Workload distribution breakdown bar and status distribution summary.
* **Settings & Session Management**:
  * Interactive theme card switcher.
  * Live telemetry polling cadence selector (2s, 4s, 8s, or Paused).
  * Control plane URL override and clean session termination.

---

## Session Management & 401 Loop Resolution

Previously, expired JWT tokens stored in `localStorage` caused endless 401 error cascades.
The new API client (`js/api.js`) intercepts HTTP 401 responses, removes expired tokens from `localStorage`, stops active polling timers, shows an informative notification, and renders the authentication modal without page reloading or infinite request loops.

---

## Quick Start Instructions

### 1. Launch the FastAPI Backend
In a terminal, start the backend:
```bash
cd user-website/backend
start.bat
# Control plane will be active at http://127.0.0.1:8000
```

### 2. Launch the Frontend Console
In another terminal:
```bash
cd user-website/nexora-frontend
start.bat
# Or run: python -m http.server 5173
```
Open **`http://localhost:5173`** in your browser.

---

## Directory Structure

```
user-website/nexora-frontend/
├── index.html                  # Semantic HTML5 App Shell
├── favicon.svg                 # Brand mark icon
├── start.bat                   # 1-click launcher (Python http.server 5173)
├── README.md                   # Documentation
├── css/
│   ├── tokens.css              # Palettes A, B, C, D CSS variables & dimensions
│   ├── base.css                # Base typography, grid background, reset, scrollbars
│   ├── layout.css              # Persistent sidebar, topbar, responsive containers
│   ├── components.css          # Cards, buttons, tables, badges, modals, drawers, toasts
│   ├── animations.css          # Keyframes (pulse-ring, spin, slide-up, shimmer)
│   └── pages.css               # Page-specific layouts
└── js/
    ├── app.js                  # Application bootstrapper & global shortcuts
    ├── router.js               # Hash-based SPA routing (#/overview, #/jobs, etc.)
    ├── api.js                  # Fetch wrapper with 401 auto-logout & URL discovery
    ├── auth.js                 # Authentication state, login/register modal
    ├── state.js                # Reactive state store & polling lifecycle
    ├── components/
    │   ├── sidebar.js          # Collapsible navigation with active indicator & badges
    │   ├── topbar.js           # Breadcrumb, latency pill, token pill, theme switcher
    │   ├── job-modal.js        # Workload submission with live token estimator
    │   ├── job-drawer.js       # Slide-out job details, checkpoint logs, output
    │   ├── purchase-modal.js   # Token packages and demo card top-up
    │   └── toast.js            # Accessible stackable notification toasts
    ├── pages/
    │   ├── overview.js         # Dashboard, KPI cards, gauges, recent jobs, live feed
    │   ├── jobs.js             # Job filters, search, emergency stop all, data table
    │   ├── providers.js        # Worker nodes fleet, hardware specs, heartbeat status
    │   ├── resource-pool.js    # Cluster aggregation & interactive matcher sandbox
    │   ├── billing.js          # Token balance hero, packages, audit transaction ledger
    │   ├── analytics.js        # Success rate, workload distribution, recovery counts
    │   └── settings.js         # Theme picker, polling rate, session manager
    └── utils/
        ├── icons.js            # Technical inline SVG icons
        ├── formatters.js       # Formatting for tokens, dates, durations, byte sizes
        └── charts.js           # SVG Donut gauges and distribution bar generators
```
