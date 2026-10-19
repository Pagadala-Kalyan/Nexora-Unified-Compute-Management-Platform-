/**
 * NEXORA UCMP — TOKEN PURCHASE & DEMO TOP-UP MODAL
 */

import { apiRequest } from '../api.js';
import { state, refreshAll, refreshTransactions } from '../state.js';
import { showToast } from './toast.js';
import { formatNumber } from '../utils/formatters.js';

export function openPurchaseModal() {
  let modalWrap = document.getElementById('purchase-modal-wrap');
  if (!modalWrap) {
    modalWrap = document.createElement('div');
    modalWrap.id = 'purchase-modal-wrap';
    document.body.appendChild(modalWrap);
  }

  const packages = state.billing?.packages || [
    { id: 'starter', price: 10, tokens: 100 },
    { id: 'standard', price: 25, tokens: 300 },
    { id: 'compute', price: 50, tokens: 700 }
  ];

  modalWrap.innerHTML = `
    <div class="modal-backdrop active" id="purchase-backdrop">
      <div class="modal-box" style="max-width: 560px;">
        <div class="modal-header">
          <div>
            <div class="modal-title">Compute Token Management</div>
            <div style="font-size: var(--text-2xs); color: var(--text-muted); font-family: var(--font-mono); margin-top: 2px;">
              CURRENT BALANCE: <span style="color: var(--accent-cyan);">${formatNumber(state.dashboard?.token_balance ?? 0)} TOKENS</span>
            </div>
          </div>
          <button class="modal-close-btn" id="purchase-close-btn">&times;</button>
        </div>

        <div class="modal-body">
          <div class="tab-list">
            <button class="tab-btn active" id="tab-packages-btn">Token Packages</button>
            <button class="tab-btn" id="tab-card-btn">Simulated Card Checkout</button>
          </div>

          <!-- TAB 1: Instant Packages -->
          <div id="panel-packages">
            <div style="font-size: var(--text-xs); color: var(--text-secondary); margin-bottom: var(--space-3);">
              Select a compute credit package for instant settlement:
            </div>
            <div class="packages-grid" style="margin-top: 0;">
              ${packages.map(pkg => `
                <div class="package-card" data-pkg-id="${pkg.id}">
                  <div class="package-title">${pkg.id} Tier</div>
                  <div class="package-tokens">${formatNumber(pkg.tokens)}</div>
                  <div class="package-price">$${pkg.price}.00 USD</div>
                  <button class="btn btn-outline btn-sm" style="margin-top: var(--space-3); width: 100%;">
                    Select Package
                  </button>
                </div>
              `).join('')}
            </div>
          </div>

          <!-- TAB 2: Demo Card Top-up -->
          <div id="panel-card" style="display: none;">
            <div style="font-size: var(--text-xs); color: var(--text-muted); margin-bottom: var(--space-3); padding: 8px 12px; background: var(--bg-secondary); border-radius: 6px; border: 1px solid var(--border-subtle);">
              ℹ️ <strong>Demo Environment:</strong> Test credit card numbers are validated for format only and are never transmitted or stored.
            </div>

            <form id="demo-topup-form">
              <div class="form-group">
                <label class="form-label" for="topup-amount">Select Top-Up Value</label>
                <select id="topup-amount" class="select">
                  <option value="10">$10.00 USD — 100 Tokens</option>
                  <option value="25" selected>$25.00 USD — 300 Tokens</option>
                  <option value="50">$50.00 USD — 700 Tokens</option>
                </select>
              </div>

              <div class="form-group">
                <label class="form-label" for="topup-cardholder">Cardholder Name</label>
                <input type="text" id="topup-cardholder" class="input" placeholder="Alex Morgan" required value="Nexora Test User" />
              </div>

              <div class="form-group">
                <label class="form-label" for="topup-cardnumber">Demo Card Number</label>
                <input type="text" id="topup-cardnumber" class="input input-mono" placeholder="4242 •••• •••• 4242" required value="4242 4242 4242 4242" maxlength="23" />
              </div>

              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3);">
                <div class="form-group">
                  <label class="form-label" for="topup-expiry">Expiry (MM/YY)</label>
                  <input type="text" id="topup-expiry" class="input input-mono" placeholder="12/28" required value="12/28" maxlength="7" />
                </div>
                <div class="form-group">
                  <label class="form-label" for="topup-cvc">Security Code</label>
                  <input type="text" id="topup-cvc" class="input input-mono" placeholder="999" required value="999" maxlength="4" />
                </div>
              </div>

              <button type="submit" class="btn btn-primary" id="btn-submit-topup" style="width: 100%; margin-top: var(--space-2);">
                Simulate Payment & Credit Tokens
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  `;

  const closeBtn = document.getElementById('purchase-close-btn');
  const tabPkgs = document.getElementById('tab-packages-btn');
  const tabCard = document.getElementById('tab-card-btn');
  const panelPkgs = document.getElementById('panel-packages');
  const panelCard = document.getElementById('panel-card');

  closeBtn.addEventListener('click', () => { modalWrap.innerHTML = ''; });

  tabPkgs.addEventListener('click', () => {
    tabPkgs.classList.add('active');
    tabCard.classList.remove('active');
    panelPkgs.style.display = 'block';
    panelCard.style.display = 'none';
  });

  tabCard.addEventListener('click', () => {
    tabCard.classList.add('active');
    tabPkgs.classList.remove('active');
    panelPkgs.style.display = 'none';
    panelCard.style.display = 'block';
  });

  // Package purchase click
  modalWrap.querySelectorAll('.package-card').forEach(card => {
    card.addEventListener('click', async () => {
      const pkgId = card.getAttribute('data-pkg-id');
      const btn = card.querySelector('button');
      btn.disabled = true;
      btn.textContent = 'Processing...';

      try {
        const res = await apiRequest('/billing/purchase', {
          method: 'POST',
          body: JSON.stringify({ package_id: pkgId })
        });
        showToast(`Purchased ${res.tokens_added} tokens! New balance: ${formatNumber(res.new_balance)}`, 'success');
        await refreshAll();
        await refreshTransactions();
        modalWrap.innerHTML = '';
      } catch (err) {
        showToast(err.message || 'Purchase failed', 'error');
        btn.disabled = false;
        btn.textContent = 'Select Package';
      }
    });
  });

  // Demo Top-Up Form submit
  const form = document.getElementById('demo-topup-form');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-submit-topup');
    btn.disabled = true;
    btn.textContent = 'Settling Demo Payment...';

    const amount = Number(document.getElementById('topup-amount').value);
    const cardholder = document.getElementById('topup-cardholder').value.trim();
    const cardNumber = document.getElementById('topup-cardnumber').value.trim();
    const expiry = document.getElementById('topup-expiry').value.trim();
    const cvc = document.getElementById('topup-cvc').value.trim();

    try {
      const res = await apiRequest('/billing/demo-topup', {
        method: 'POST',
        body: JSON.stringify({
          amount,
          cardholder,
          card_number: cardNumber,
          expiry,
          cvc
        })
      });
      showToast(`Demo top-up successful! +${res.tokens_added} tokens credited. Balance: ${formatNumber(res.wallet_balance)}`, 'success');
      await refreshAll();
      await refreshTransactions();
      modalWrap.innerHTML = '';
    } catch (err) {
      showToast(err.message || 'Demo top-up failed', 'error');
      btn.disabled = false;
      btn.textContent = 'Simulate Payment & Credit Tokens';
    }
  });
}
