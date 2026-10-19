/**
 * NEXORA UCMP — DATA FORMATTING UTILITIES
 */

export function timeAgo(inputDate) {
  if (!inputDate) return 'N/A';
  const date = new Date(inputDate);
  if (isNaN(date.getTime())) return String(inputDate);
  
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 5) return 'Just now';
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function formatDate(inputDate) {
  if (!inputDate) return '—';
  const date = new Date(inputDate);
  if (isNaN(date.getTime())) return String(inputDate);
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function formatDuration(seconds) {
  if (seconds == null || isNaN(seconds)) return '—';
  const s = Number(seconds);
  if (s < 1) return `${(s * 1000).toFixed(0)} ms`;
  if (s < 60) return `${s.toFixed(2)} s`;
  const m = Math.floor(s / 60);
  const remSec = (s % 60).toFixed(1);
  return `${m}m ${remSec}s`;
}

export function formatNumber(val) {
  if (val == null) return '0';
  return Number(val).toLocaleString();
}

export function formatBytes(bytes) {
  if (bytes == null || isNaN(bytes)) return '0 B';
  const b = Number(bytes);
  if (b < 1024) return `${b} B`;
  const kb = b / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  const gb = mb / 1024;
  return `${gb.toFixed(2)} GB`;
}

export function getStatusBadgeHTML(status) {
  const norm = String(status || 'QUEUED').toUpperCase();
  let cls = 'badge-queued';
  
  switch (norm) {
    case 'SCHEDULED': cls = 'badge-scheduled'; break;
    case 'RUNNING': cls = 'badge-running'; break;
    case 'RECOVERING': cls = 'badge-recovering'; break;
    case 'COMPLETED': cls = 'badge-completed'; break;
    case 'FAILED': cls = 'badge-failed'; break;
    case 'CANCELLED': cls = 'badge-cancelled'; break;
    case 'ONLINE': cls = 'badge-online'; break;
    case 'BUSY': cls = 'badge-busy'; break;
    case 'OFFLINE': cls = 'badge-offline'; break;
    default: cls = 'badge-queued';
  }
  
  return `<span class="badge ${cls}"><span class="badge-dot"></span>${norm}</span>`;
}

export async function copyToClipboard(text) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.opacity = '0';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    const success = document.execCommand('copy');
    document.body.removeChild(textArea);
    return success;
  } catch (err) {
    console.error('Clipboard copy failed:', err);
    return false;
  }
}
