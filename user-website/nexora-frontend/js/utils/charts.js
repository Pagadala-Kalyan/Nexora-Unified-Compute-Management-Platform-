/**
 * NEXORA UCMP — PURE SVG CHARTS ENGINE
 * Visual Reference: rapt.ai Spline Area Chart, Donut Gauges & Resource Allocation
 */

/**
 * Smooth spline area chart (rapt.ai GPU Utilization)
 * Renders an SVG bezier curve with gradient fill and telemetry gridlines.
 */
export function renderSplineAreaChart(dataPoints = [], options = {}) {
  const width = options.width || 680;
  const height = options.height || 210;
  const paddingLeft = options.paddingLeft || 36;
  const paddingRight = options.paddingRight || 16;
  const paddingTop = options.paddingTop || 20;
  const paddingBottom = options.paddingBottom || 28;

  const chartW = width - paddingLeft - paddingRight;
  const chartH = height - paddingTop - paddingBottom;

  // Default curve points if empty
  const pts = (dataPoints && dataPoints.length > 1) ? dataPoints : [42, 58, 76, 91, 84, 69, 58, 88, 72, 64];
  const maxVal = 100;
  const minVal = 0;

  // Calculate normalized coordinates
  const coords = pts.map((val, idx) => {
    const x = paddingLeft + (idx / (pts.length - 1)) * chartW;
    const y = paddingTop + chartH - ((Math.min(100, Math.max(0, val)) - minVal) / (maxVal - minVal)) * chartH;
    return { x, y, val };
  });

  // Generate cubic spline path
  function createSplinePath(points) {
    if (points.length < 2) return '';
    let d = `M ${points[0].x.toFixed(1)},${points[0].y.toFixed(1)}`;
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i === 0 ? 0 : i - 1];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[i + 2] || p2;

      const cp1x = p1.x + (p2.x - p0.x) / 6;
      const cp1y = p1.y + (p2.y - p0.y) / 6;
      const cp2x = p2.x - (p3.x - p1.x) / 6;
      const cp2y = p2.y - (p3.y - p1.y) / 6;

      d += ` C ${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
    }
    return d;
  }

  const linePath = createSplinePath(coords);
  const areaPath = `${linePath} L ${(paddingLeft + chartW).toFixed(1)},${(paddingTop + chartH).toFixed(1)} L ${paddingLeft.toFixed(1)},${(paddingTop + chartH).toFixed(1)} Z`;

  // Locate apex point for rapt.ai highlight probe
  let maxPt = coords[0];
  for (const c of coords) {
    if (c.val > maxPt.val) maxPt = c;
  }

  // Gridlines
  const gridSteps = [0, 25, 50, 75, 100];
  const gridLines = gridSteps.map(step => {
    const y = paddingTop + chartH - (step / 100) * chartH;
    return `
      <g>
        <line x1="${paddingLeft}" y1="${y}" x2="${paddingLeft + chartW}" y2="${y}" stroke="var(--border-subtle)" stroke-width="1" stroke-dasharray="3 3"/>
        <text x="${paddingLeft - 8}" y="${y + 3}" fill="var(--text-muted)" font-size="9" font-family="var(--font-mono)" text-anchor="end">${step}%</text>
      </g>
    `;
  }).join('');

  // Timeline labels
  const timelineLabels = options.labels || ['00:00', '03:00', '06:00', '09:00', '12:00', '15:00', '18:00', '21:00', 'NOW'];
  const timelineTicks = timelineLabels.map((lbl, i) => {
    const x = paddingLeft + (i / (timelineLabels.length - 1)) * chartW;
    return `
      <text x="${x}" y="${height - 8}" fill="var(--text-muted)" font-size="9" font-family="var(--font-mono)" text-anchor="middle">${lbl}</text>
    `;
  }).join('');

  const strokeColor = options.strokeColor || '#7566F6';
  const gradId = options.gradId || 'splineGrad_' + Math.random().toString(36).substr(2, 6);

  return `
    <svg width="100%" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="overflow: visible;">
      <defs>
        <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${strokeColor}" stop-opacity="0.32"/>
          <stop offset="60%" stop-color="#13D9F2" stop-opacity="0.08"/>
          <stop offset="100%" stop-color="#080B12" stop-opacity="0"/>
        </linearGradient>
      </defs>

      <!-- Gridlines -->
      ${gridLines}

      <!-- Timeline Ticks -->
      ${timelineTicks}

      <!-- Area Fill -->
      <path d="${areaPath}" fill="url(#${gradId})" />

      <!-- Spline Line -->
      <path d="${linePath}" fill="none" stroke="${strokeColor}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />

      <!-- Active Apex Probe (rapt.ai indicator) -->
      <circle cx="${maxPt.x}" cy="${maxPt.y}" r="6" fill="#F06478" opacity="0.25" class="pulse-ring"/>
      <circle cx="${maxPt.x}" cy="${maxPt.y}" r="3.5" fill="#FFFFFF" stroke="#F06478" stroke-width="2"/>
    </svg>
  `;
}

/**
 * Multi-segment Donut Chart (rapt.ai Resource Mix)
 * Renders multiple color-coded arcs with center probe dot.
 */
export function renderResourceMixDonut(segments = [], options = {}) {
  const size = options.size || 180;
  const stroke = options.stroke || 22;
  const centerRadius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * centerRadius;

  const total = segments.reduce((sum, s) => sum + (s.value || 0), 0) || 100;
  let currentOffset = 0;

  const circles = segments.map(seg => {
    const segFraction = (seg.value || 0) / total;
    const segDash = segFraction * circumference;
    const segOffset = circumference - currentOffset;
    currentOffset += segDash;

    return `
      <circle
        cx="${size / 2}"
        cy="${size / 2}"
        r="${centerRadius}"
        fill="transparent"
        stroke="${seg.color}"
        stroke-width="${stroke}"
        stroke-dasharray="${segDash.toFixed(2)} ${circumference.toFixed(2)}"
        stroke-dashoffset="${segOffset.toFixed(2)}"
        stroke-linecap="butt"
        transform="rotate(-90 ${size / 2} ${size / 2})"
        style="transition: stroke-dashoffset 0.6s var(--ease-out);"
      />
    `;
  }).join('');

  return `
    <div style="position: relative; width: ${size}px; height: ${size}px; display: flex; align-items: center; justify-content: center;">
      <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
        <!-- Background Track -->
        <circle
          cx="${size / 2}"
          cy="${size / 2}"
          r="${centerRadius}"
          fill="transparent"
          stroke="var(--panel-secondary)"
          stroke-width="${stroke}"
        />
        <!-- Multi-segments -->
        ${circles}
      </svg>
      <!-- Center Probe Indicator -->
      <div style="position: absolute; width: 8px; height: 8px; border-radius: 50%; background: #F06478; box-shadow: 0 0 8px rgba(240, 100, 120, 0.6);"></div>
    </div>
  `;
}

/**
 * Single Metric Donut Gauge (CPU / RAM / GPU Util)
 * Renders circular track + foreground stroke with percentage offset.
 */
export function renderDonutGauge(percentage = 0, options = {}) {
  const size = options.size || 100;
  const stroke = options.stroke || 9;
  const color = options.color || 'var(--accent-cyan)';
  const trackColor = options.trackColor || 'var(--panel-secondary)';

  const centerRadius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * centerRadius;
  const val = Math.min(100, Math.max(0, percentage));
  const dashoffset = circumference - (val / 100) * circumference;

  return `
    <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="transform: rotate(-90deg);">
      <!-- Track -->
      <circle
        cx="${size / 2}"
        cy="${size / 2}"
        r="${centerRadius}"
        fill="none"
        stroke="${trackColor}"
        stroke-width="${stroke}"
      />
      <!-- Progress -->
      <circle
        cx="${size / 2}"
        cy="${size / 2}"
        r="${centerRadius}"
        fill="none"
        stroke="${color}"
        stroke-width="${stroke}"
        stroke-dasharray="${circumference.toFixed(2)}"
        stroke-dashoffset="${dashoffset.toFixed(2)}"
        stroke-linecap="round"
        style="transition: stroke-dashoffset 0.8s var(--ease-out);"
      />
    </svg>
  `;
}

/**
 * Stacked Horizontal Distribution Bar
 * Used in Platform Analytics for workload breakdown.
 */
export function renderDistributionBar(segments = [], options = {}) {
  const height = options.height || 14;
  const total = segments.reduce((acc, s) => acc + (s.value || 0), 0) || 1;

  if (segments.length === 0 || total === 0) {
    return `<div style="height: ${height}px; background: var(--panel-secondary); border-radius: 4px;"></div>`;
  }

  const items = segments.map(seg => {
    const pct = ((seg.value / total) * 100).toFixed(1);
    return `
      <div
        title="${seg.label}: ${seg.value} (${pct}%)"
        style="width: ${pct}%; height: 100%; background-color: ${seg.color}; transition: width 0.5s ease;"
      ></div>
    `;
  }).join('');

  return `
    <div style="width: 100%; height: ${height}px; display: flex; border-radius: var(--radius-sm); overflow: hidden; background: var(--panel-secondary); border: 1px solid var(--border-subtle);">
      ${items}
    </div>
  `;
}
