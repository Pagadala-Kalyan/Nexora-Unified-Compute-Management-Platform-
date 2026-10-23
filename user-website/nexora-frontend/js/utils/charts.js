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

  const maxVal = 100;
  const minVal = 0;
  let raw = (dataPoints || []).map(value => {
    const number = value == null || value === '' ? null : Number(value);
    return Number.isFinite(number) ? Math.max(minVal, Math.min(maxVal, number)) : null;
  });
  let labels = options.labels || [];
  let timestamps = options.timestamps || labels;
  const parsedTimestamps = raw.map((_, index) => new Date(timestamps[index]).getTime());
  if (raw.length > 1 && parsedTimestamps.every(Number.isFinite)) {
    // Keep each value attached to its own timestamp. Duplicate instants are
    // one sample; retaining both would create a zero-width vertical segment.
    const ordered = raw.map((value, index) => ({
      value,
      label: labels[index] || '',
      timestamp: timestamps[index],
      epoch: parsedTimestamps[index],
      index
    })).sort((a, b) => a.epoch - b.epoch || a.index - b.index);
    const unique = [];
    for (const sample of ordered) {
      if (unique.length && unique[unique.length - 1].epoch === sample.epoch) unique[unique.length - 1] = sample;
      else unique.push(sample);
    }
    raw = unique.map(sample => sample.value);
    labels = unique.map(sample => sample.label);
    timestamps = unique.map(sample => sample.timestamp);
  }
  const epochTimes = timestamps.map(value => {
    const epoch = value ? new Date(value).getTime() : NaN;
    return Number.isFinite(epoch) ? epoch : null;
  });
  const validEpochs = epochTimes.filter(value => value != null);
  const useTimeScale = validEpochs.length === raw.length && validEpochs.length > 1 && validEpochs.at(-1) > validEpochs[0];
  const points = raw.map((value, idx) => ({
    x: paddingLeft + (raw.length <= 1
      ? chartW
      : useTimeScale
        ? ((epochTimes[idx] - validEpochs[0]) / (validEpochs.at(-1) - validEpochs[0])) * chartW
        : (idx / (raw.length - 1)) * chartW),
    y: value == null ? null : paddingTop + chartH - ((value - minVal) / (maxVal - minVal)) * chartH,
    val: value,
    label: timestamps[idx]
      ? new Date(timestamps[idx]).toLocaleString([], { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
      : (labels[idx] || '')
  }));

  // Fritsch-Carlson monotone cubic interpolation. Its control points remain
  // inside each adjacent sample interval, so the curve cannot invent peaks.
  function monotonePath(segment) {
    if (!segment.length) return '';
    let d = `M ${segment[0].x.toFixed(2)},${segment[0].y.toFixed(2)}`;
    if (segment.length === 1) return d;
    const widths = segment.slice(0, -1).map((point, i) => segment[i + 1].x - point.x);
    const slopes = segment.slice(0, -1).map((point, i) => (segment[i + 1].y - point.y) / widths[i]);
    const tangents = new Array(segment.length);
    tangents[0] = slopes[0];
    tangents[tangents.length - 1] = slopes[slopes.length - 1];
    for (let i = 1; i < segment.length - 1; i++) {
      const before = slopes[i - 1];
      const after = slopes[i];
      if (before * after <= 0) tangents[i] = 0;
      else {
        const beforeWidth = widths[i - 1];
        const afterWidth = widths[i];
        const w1 = 2 * afterWidth + beforeWidth;
        const w2 = afterWidth + 2 * beforeWidth;
        tangents[i] = (w1 + w2) / (w1 / before + w2 / after);
      }
    }
    for (let i = 0; i < slopes.length; i++) {
      const slope = slopes[i];
      if (slope === 0) {
        tangents[i] = 0;
        tangents[i + 1] = 0;
        continue;
      }
      const alpha = tangents[i] / slope;
      const beta = tangents[i + 1] / slope;
      const magnitude = alpha * alpha + beta * beta;
      if (magnitude > 9) {
        const scale = 3 / Math.sqrt(magnitude);
        tangents[i] = scale * alpha * slope;
        tangents[i + 1] = scale * beta * slope;
      }
    }
    for (let i = 0; i < segment.length - 1; i++) {
      const p = segment[i];
      const q = segment[i + 1];
      const dx = q.x - p.x;
      const cp1y = p.y + tangents[i] * dx / 3;
      const cp2y = q.y - tangents[i + 1] * dx / 3;
      d += ` C ${(p.x + dx / 3).toFixed(2)},${cp1y.toFixed(2)} ${(q.x - dx / 3).toFixed(2)},${cp2y.toFixed(2)} ${q.x.toFixed(2)},${q.y.toFixed(2)}`;
    }
    return d;
  }

  const segments = [];
  let segment = [];
  points.forEach(point => {
    if (point.val == null) {
      if (segment.length) segments.push(segment);
      segment = [];
    } else segment.push(point);
  });
  if (segment.length) segments.push(segment);
  const linePath = segments.map(monotonePath).join(' ');
  const baselineY = paddingTop + chartH;
  const areaPaths = segments.map(group => {
    if (group.length < 2) return '';
    return `${monotonePath(group)} L ${group[group.length - 1].x.toFixed(2)},${baselineY.toFixed(2)} L ${group[0].x.toFixed(2)},${baselineY.toFixed(2)} Z`;
  }).join(' ');

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
  const tickIndexes = [];
  if (raw.length) {
    const minimumTickSpacing = 48;
    for (const fraction of [0, 0.25, 0.5, 0.75, 1]) {
      const targetX = paddingLeft + chartW * fraction;
      let nearestIndex = 0;
      for (let index = 1; index < points.length; index++) {
        if (Math.abs(points[index].x - targetX) < Math.abs(points[nearestIndex].x - targetX)) nearestIndex = index;
      }
      if (tickIndexes.every(index => Math.abs(points[index].x - points[nearestIndex].x) >= minimumTickSpacing)) {
        tickIndexes.push(nearestIndex);
      }
    }
  }
  const timelineTicks = tickIndexes.map(i => {
    const lbl = labels[i] || '';
    const x = points[i].x;
    return `
      <text class="telemetry-axis-tick" x="${x}" y="${height - 8}" fill="var(--text-muted)" font-size="9" font-family="var(--font-mono)" text-anchor="middle">${escapeChartText(lbl)}</text>
    `;
  }).join('');

  const strokeColor = options.strokeColor || '#8B64FF';
  const gradId = options.gradId || 'splineGrad_telemetry';
  const pointMarkup = points.filter(point => point.val != null).map(point => `
    <g class="telemetry-chart-point" tabindex="0" role="img" aria-label="${escapeChartText(point.label)}: ${point.val.toFixed(1)} percent">
      <title>${escapeChartText(point.label)} · ${point.val.toFixed(1)}%</title>
      <circle class="telemetry-chart-hit" cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="8" />
      <circle class="telemetry-chart-highlight" cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="3.2" />
    </g>`).join('');
  const hasData = points.some(point => point.val != null);

  return `
    <svg xmlns="http://www.w3.org/2000/svg" class="telemetry-chart-svg" width="100%" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Telemetry history chart">
      <defs>
        <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${strokeColor}" stop-opacity="0.32"/>
          <stop offset="60%" stop-color="#6652D9" stop-opacity="0.10"/>
          <stop offset="100%" stop-color="#090810" stop-opacity="0"/>
        </linearGradient>
      </defs>

      <!-- Gridlines -->
      ${gridLines}

      <!-- Timeline Ticks -->
      ${timelineTicks}

      <!-- Area Fill -->
      <path class="telemetry-chart-area" d="${areaPaths}" fill="url(#${gradId})" />

      <path class="telemetry-chart-line" d="${linePath}" fill="none" stroke="${strokeColor}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />

      <g class="telemetry-chart-points">${pointMarkup}</g>
      ${hasData ? '' : `<text class="telemetry-chart-empty" x="${width / 2}" y="${height / 2}" text-anchor="middle" fill="var(--text-muted)" font-size="12">Waiting for provider telemetry…</text>`}
    </svg>
  `;
}

function escapeChartText(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
}

/** Patch the existing SVG when a live sample arrives, keeping its axes and DOM stable. */
export function updateSplineAreaChart(container, dataPoints = [], options = {}) {
  if (!container) return;
  const markup = renderSplineAreaChart(dataPoints, options);
  const charts = [...container.querySelectorAll('.telemetry-chart-svg')];
  const current = charts[0];
  if (!current) {
    container.innerHTML = markup;
    return;
  }
  charts.slice(1).forEach(chart => chart.remove());
  const next = new DOMParser().parseFromString(markup, 'image/svg+xml').documentElement;
  for (const selector of ['.telemetry-chart-area', '.telemetry-chart-line', '.telemetry-chart-points', '.telemetry-chart-empty']) {
    const oldNode = current.querySelector(selector);
    const newNode = next.querySelector(selector);
    if (oldNode && newNode) {
      if (selector === '.telemetry-chart-points') {
        const oldPoints = [...oldNode.children];
        const newPoints = [...newNode.children];
        newPoints.forEach((point, index) => {
          const existing = oldPoints[index];
          if (existing) {
            existing.setAttribute('aria-label', point.getAttribute('aria-label'));
            existing.querySelector('title').textContent = point.querySelector('title').textContent;
            existing.querySelector('.telemetry-chart-hit').setAttribute('cx', point.querySelector('.telemetry-chart-hit').getAttribute('cx'));
            existing.querySelector('.telemetry-chart-hit').setAttribute('cy', point.querySelector('.telemetry-chart-hit').getAttribute('cy'));
            existing.querySelector('.telemetry-chart-highlight').setAttribute('cx', point.querySelector('.telemetry-chart-highlight').getAttribute('cx'));
            existing.querySelector('.telemetry-chart-highlight').setAttribute('cy', point.querySelector('.telemetry-chart-highlight').getAttribute('cy'));
          } else oldNode.append(point.cloneNode(true));
        });
        while (oldNode.children.length > newPoints.length) oldNode.lastElementChild.remove();
      } else oldNode.setAttribute('d', newNode.getAttribute('d') || '');
    } else if (!oldNode && newNode) current.append(newNode.cloneNode(true));
    else if (oldNode && !newNode) oldNode.remove();
  }
  const oldTicks = [...current.querySelectorAll('.telemetry-axis-tick')];
  const newTicks = [...next.querySelectorAll('.telemetry-axis-tick')];
  newTicks.forEach((tick, index) => {
    if (oldTicks[index]) {
      oldTicks[index].textContent = tick.textContent;
      oldTicks[index].setAttribute('x', tick.getAttribute('x'));
    } else current.append(tick.cloneNode(true));
  });
  while (oldTicks.length > newTicks.length) oldTicks.pop().remove();
  container.classList.remove('telemetry-updating');
  requestAnimationFrame(() => {
    container.classList.add('telemetry-updating');
    setTimeout(() => container.classList.remove('telemetry-updating'), 180);
  });
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
