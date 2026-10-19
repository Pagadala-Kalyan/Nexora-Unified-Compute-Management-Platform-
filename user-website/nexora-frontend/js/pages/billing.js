/**
 * NEXORA UCMP — WALLET & BILLING MANAGEMENT PAGE
 */

import { state, refreshTransactions } from '../state.js';
import { getIcon } from '../utils/icons.js';
import { formatNumber, formatDate, timeAgo } from '../utils/formatters.js';
import { openPurchaseModal } from '../components/purchase-modal.js';

export function renderBillingPage() {
  const billing = state.billing || {};
  const balance = billing.token_balance ?? state.user?.token_balance ?? 0;
  const reserved = billing.reserved_tokens ?? 0;
  const actualUsage = billing.actual_usage ?? 0;
  const txs = state.transactions || [];

  return `
    <div class="view-enter">
      <!-- Header -->
      <div class="overview-header">
        <div>
          <h2>Wallet & Token Ledger</h2>
          <p style="font-size: var(--text-xs); color: var(--text-muted);">
            Deterministic two-phase compute token settlement and transparent transaction logs.
          </p>
        </div>

        <button class="btn btn-primary" id="billing-topup-btn">
          ${getIcon('bolt')}
          Add Tokens / Buy Package
        </button>
      </div>

      <!-- Wallet Overview Hero -->
      <div class="wallet-hero-grid">
        <!-- Balance Card -->
        <div class="wallet-balance-card">
          <div>
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
              <span style="font-size: var(--text-xs); font-weight: 700; color: var(--text-muted); text-transform: uppercase;">
                Available Compute Balance
              </span>
              <div style="width: 32px; height: 32px; border-radius: var(--radius-md); background: var(--accent-cyan-soft); display: flex; align-items: center; justify-content: center; color: var(--accent-cyan);">
                ${getIcon('wallet')}
              </div>
            </div>
            <div class="token-balance-big" style="margin-top: var(--space-4);">
              ${formatNumber(balance)}
              <span style="font-size: var(--text-sm); font-weight: 500; color: var(--text-secondary); letter-spacing: normal;">TOKENS</span>
            </div>
          </div>

          <div style="display: flex; gap: var(--space-4); margin-top: var(--space-6); padding-top: var(--space-4); border-top: 1px solid var(--border-color);">
            <div>
              <div style="font-size: var(--text-2xs); color: var(--text-muted); text-transform: uppercase;">In-Flight Reserved</div>
              <div style="font-size: var(--text-md); font-family: var(--font-mono); font-weight: 600; color: var(--accent-cyan);">${formatNumber(reserved)} Tokens</div>
            </div>
            <div>
              <div style="font-size: var(--text-2xs); color: var(--text-muted); text-transform: uppercase;">Total Historical Spend</div>
              <div style="font-size: var(--text-md); font-family: var(--font-mono); font-weight: 600; color: var(--status-success);">${formatNumber(actualUsage)} Tokens</div>
            </div>
          </div>
        </div>

        <!-- Token Packages Card -->
        <div class="card" style="display: flex; flex-direction: column; justify-content: space-between;">
          <div class="card-header" style="margin-bottom: var(--space-2);">
            <div>
              <div class="card-title">${getIcon('bolt')} Available Compute Packages</div>
              <div class="card-subtitle">Instant token credit directly to your persistent wallet</div>
            </div>
          </div>

          <div class="packages-grid">
            <div class="package-card" data-pkg-id="starter">
              <div class="package-title">Starter</div>
              <div class="package-tokens">100</div>
              <div class="package-price">$10.00 USD</div>
            </div>

            <div class="package-card" data-pkg-id="standard" style="border-color: var(--accent-cyan); box-shadow: 0 0 10px var(--accent-cyan-soft);">
              <div class="package-title" style="color: var(--accent-cyan-bright);">Standard (Popular)</div>
              <div class="package-tokens">300</div>
              <div class="package-price">$25.00 USD</div>
            </div>

            <div class="package-card" data-pkg-id="compute">
              <div class="package-title">Compute Pro</div>
              <div class="package-tokens">700</div>
              <div class="package-price">$50.00 USD</div>
            </div>
          </div>

          <div style="margin-top: var(--space-4); font-size: var(--text-2xs); color: var(--text-muted); text-align: center;">
            Tokens are non-expiring and reserved dynamically during compute scheduling.
          </div>
        </div>
      </div>

      <!-- Transaction Ledger Table -->
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">${getIcon('chart')} Token Audit Ledger</div>
            <div class="card-subtitle">Complete chronological history of purchases, reservations, usage charges, and refunds</div>
          </div>
          <button class="btn btn-ghost btn-sm" id="btn-refresh-ledger">
            ${getIcon('refresh')}
            Refresh Ledger
          </button>
        </div>

        ${txs.length > 0 ? `
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Transaction ID</th>
                  <th>Type</th>
                  <th>Delta Amount</th>
                  <th>Balance Before</th>
                  <th>Balance After</th>
                  <th>Description</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                ${txs.map(tx => {
                  const isPositive = tx.amount > 0;
                  let typeColor = 'var(--text-secondary)';
                  if (tx.type === 'PURCHASE') typeColor = 'var(--accent-cyan)';
                  if (tx.type === 'JOB_RESERVATION') typeColor = 'var(--status-warning)';
                  if (tx.type === 'JOB_REFUND') typeColor = 'var(--status-success)';
                  if (tx.type === 'JOB_USAGE') typeColor = 'var(--status-error)';

                  return `
                    <tr>
                      <td class="cell-mono">${tx.id}</td>
                      <td>
                        <span style="font-family: var(--font-mono); font-size: 11px; padding: 2px 6px; border-radius: 4px; background: var(--surface-elevated); color: ${typeColor}; border: 1px solid var(--border-subtle);">
                          ${tx.type}
                        </span>
                      </td>
                      <td class="cell-mono" style="font-weight: 700; color: ${isPositive ? 'var(--status-success)' : 'var(--status-warning)'};">
                        ${isPositive ? `+${tx.amount}` : tx.amount} Tokens
                      </td>
                      <td class="cell-mono">${formatNumber(tx.balance_before)}</td>
                      <td class="cell-mono">${formatNumber(tx.balance_after)}</td>
                      <td class="cell-primary" style="font-size: var(--text-xs);">${tx.description || '—'}</td>
                      <td class="cell-mono" title="${formatDate(tx.created_at)}">${timeAgo(tx.created_at)}</td>
                    </tr>
                  `;
                }).join('')}
              </tbody>
            </table>
          </div>
        ` : `
          <div class="empty-state">
            <div class="empty-state-icon">${getIcon('wallet')}</div>
            <div class="empty-state-title">No Transactions Recorded</div>
            <div class="empty-state-desc">Transactions appear here when you submit jobs or purchase compute tokens.</div>
          </div>
        `}
      </div>
    </div>
  `;
}

export function initBillingEvents() {
  const topupBtn = document.getElementById('billing-topup-btn');
  if (topupBtn) topupBtn.addEventListener('click', openPurchaseModal);

  document.querySelectorAll('.package-card').forEach(card => {
    card.addEventListener('click', openPurchaseModal);
  });

  const refreshLedger = document.getElementById('btn-refresh-ledger');
  if (refreshLedger) {
    refreshLedger.addEventListener('click', async () => {
      refreshLedger.disabled = true;
      await refreshTransactions();
      window.dispatchEvent(new CustomEvent('nexora:rerender'));
    });
  }
}
