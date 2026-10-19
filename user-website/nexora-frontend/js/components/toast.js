/**
 * NEXORA UCMP — ACCESSIBLE TOAST SYSTEM
 */

import { getIcon } from '../utils/icons.js';

let container = null;

function ensureContainer() {
  if (!container || !document.body.contains(container)) {
    container = document.createElement('div');
    container.className = 'toast-container';
    container.setAttribute('aria-live', 'polite');
    container.setAttribute('aria-atomic', 'true');
    document.body.appendChild(container);
  }
  return container;
}

export function showToast(message, type = 'info', duration = 3800) {
  const c = ensureContainer();
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.setAttribute('role', 'alert');

  let iconName = 'activity';
  if (type === 'success') iconName = 'check';
  if (type === 'error') iconName = 'alert';
  if (type === 'warning') iconName = 'alert';

  toast.innerHTML = `
    <div style="color: ${type === 'success' ? 'var(--status-success)' : type === 'error' ? 'var(--status-error)' : type === 'warning' ? 'var(--status-warning)' : 'var(--accent-cyan)'}; display: flex; align-items: center;">
      ${getIcon(iconName)}
    </div>
    <div style="flex: 1; min-width: 0; line-height: 1.35;">${message}</div>
    <button style="background: transparent; border: none; color: var(--text-muted); cursor: pointer; padding: 2px;" aria-label="Dismiss">
      ${getIcon('close')}
    </button>
  `;

  const closeBtn = toast.querySelector('button');
  closeBtn.addEventListener('click', () => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(() => toast.remove(), 200);
  });

  c.appendChild(toast);

  if (duration > 0) {
    setTimeout(() => {
      if (toast.parentElement) {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        setTimeout(() => toast.remove(), 200);
      }
    }, duration);
  }

  return toast;
}
