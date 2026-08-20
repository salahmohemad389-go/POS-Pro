/* Owner UI v4: optional invoice contact lines, app identity, invoice-code toggle, safe reset. */
(() => {
  'use strict';

  const byId = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const nativeFetch = window.fetch.bind(window);

  function installDocumentIdentity() {
    if (!document.querySelector('link[rel="manifest"]')) {
      const manifest = document.createElement('link');
      manifest.rel = 'manifest'; manifest.href = '/manifest.webmanifest';
      document.head.appendChild(manifest);
    }
    let icon = document.querySelector('link[rel~="icon"]');
    if (!icon) { icon = document.createElement('link'); icon.rel = 'icon'; document.head.appendChild(icon); }
    icon.href = '/app-icon';
    let apple = document.querySelector('link[rel="apple-touch-icon"]');
    if (!apple) { apple = document.createElement('link'); apple.rel = 'apple-touch-icon'; document.head.appendChild(apple); }
    apple.href = '/app-icon';
    let theme = document.querySelector('meta[name="theme-color"]');
    if (!theme) { theme = document.createElement('meta'); theme.name = 'theme-color'; document.head.appendChild(theme); }
    theme.content = '#2563eb';
  }

  function installStyles() {
    if (byId('ownerUiV4Style')) return;
    const style = document.createElement('style');
    style.id = 'ownerUiV4Style';
    style.textContent = `
      .invoice-optional-meta{display:grid;grid-template-columns:1fr 1.35fr;gap:8px;margin-top:9px}
      .invoice-optional-meta input{width:100%;min-width:0}
      .invoice-meta-note{grid-column:1/-1;font-size:11px;color:var(--g500);margin-top:-2px}
      #loginProductBadge{display:inline-flex;align-items:center;justify-content:center;margin:0 auto 7px;padding:4px 12px;border-radius:999px;font-size:11px;font-weight:800;letter-spacing:.8px;background:var(--g100);color:var(--g600)}
      #sidebarPosLabel{display:block;text-align:center;font-size:10px;font-weight:800;letter-spacing:1px;color:var(--g500);margin-top:2px}
      .owner-v4-settings{margin-top:14px}
      .owner-v4-settings .owner-v4-row{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 0;border-bottom:1px solid var(--g200)}
      .owner-v4-settings .owner-v4-row:last-child{border-bottom:0}
      .owner-v4-settings .owner-v4-copy{display:flex;flex-direction:column;gap:3px}
      .owner-v4-settings .owner-v4-copy small{color:var(--g500)}
      .owner-v4-reset{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding-top:12px}
      @media(max-width:700px){.invoice-optional-meta{grid-template-columns:1fr}.invoice-meta-note{grid-column:1}}
    `;
    document.head.appendChild(style);
  }

  function installOptionalInvoiceFields() {
    if (byId('invoicePrintPhone')) return;
    const host = document.querySelector('.cart-customer');
    if (!host) return;
    const box = document.createElement('div');
    box.className = 'invoice-optional-meta';
    box.innerHTML = `
      <input type="text" id="invoicePrintPhone" maxlength="40" autocomplete="tel" placeholder="رقم التليفون على الفاتورة (اختياري)">
      <input type="text" id="invoicePrintAddress" maxlength="300" autocomplete="street-address" placeholder="العنوان على الفاتورة (اختياري)">
      <div class="invoice-meta-note">لو الخانة فاضية لن تظهر نهائياً في الفاتورة.</div>
    `;
    host.appendChild(box);
  }

  function installPosLabels() {
    const loginBox = document.querySelector('.login-box');
    if (loginBox && !byId('loginProductBadge')) {
      const badge = document.createElement('div');
      badge.id = 'loginProductBadge'; badge.textContent = 'POS';
      const logo = byId('loginDynamicLogo') || loginBox.firstElementChild;
      if (logo?.nextSibling) loginBox.insertBefore(badge, logo.nextSibling);
      else loginBox.prepend(badge);
    }
    const text = document.querySelector('.sidebar-header .logo-text');
    if (text && !byId('sidebarPosLabel')) {
      const existingSmall = text.querySelector('small');
      if (existingSmall) { existingSmall.id = 'sidebarPosLabel'; existingSmall.textContent = 'POS'; }
      else { const small = document.createElement('small'); small.id = 'sidebarPosLabel'; small.textContent = 'POS'; text.appendChild(small); }
    }
  }

  async function refreshBranding() {
    try {
      const response = await nativeFetch('/api/branding', { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) return;
      const branding = await response.json();
      const name = String(branding.store_name || 'POS').trim() || 'POS';
      document.title = name;
      const loginName = byId('loginStoreName');
      if (loginName) { loginName.textContent = name; loginName.style.display = ''; }
      const sideName = byId('storeName');
      if (sideName) { sideName.textContent = name; sideName.style.display = ''; }
      installPosLabels();
    } catch (_) {}
  }

  function installSettingsCard() {
    if (byId('ownerV4Settings')) return;
    const page = byId('page-settings');
    if (!page) return;
    const card = document.createElement('div');
    card.id = 'ownerV4Settings';
    card.className = 'card owner-v4-settings';
    card.innerHTML = `
      <div class="card-header"><h3>🧾 شكل الفاتورة والنظام</h3></div>
      <div style="padding:14px 16px">
        <div class="owner-v4-row">
          <div class="owner-v4-copy">
            <strong>إظهار كود الصنف في الفاتورة</strong>
            <small>عند الإخفاء يتم توسيع اسم الصنف وإعادة توزيع الأعمدة تلقائياً في A4 والحراري.</small>
          </div>
          <label class="toggle-label"><input type="checkbox" id="setInvoiceShowProductCode" checked> إظهار</label>
        </div>
        <div class="owner-v4-reset">
          <div class="owner-v4-copy">
            <strong>Reset الموقع</strong>
            <small>يرجع إعدادات الهوية والواجهة والطباعة للوضع الافتراضي فقط، ولا يمسح الفواتير أو المنتجات أو العملاء أو المستخدمين.</small>
          </div>
          <button class="btn btn-danger" type="button" id="resetWebsiteBtn">Reset</button>
        </div>
      </div>
    `;
    page.appendChild(card);
    byId('resetWebsiteBtn')?.addEventListener('click', resetSite);
    loadInvoiceLayoutSetting();
  }

  async function loadInvoiceLayoutSetting() {
    const control = byId('setInvoiceShowProductCode');
    if (!control) return;
    try {
      const r = await nativeFetch('/api/settings', { credentials: 'same-origin', cache: 'no-store' });
      if (!r.ok) return;
      const data = await r.json();
      control.checked = data.invoice_show_product_code !== false;
      const theme = document.querySelector('meta[name="theme-color"]');
      if (theme && /^#[0-9a-fA-F]{6}$/.test(String(data.primary_color || ''))) theme.content = data.primary_color;
    } catch (_) {}
  }

  async function saveInvoiceLayoutSetting() {
    const control = byId('setInvoiceShowProductCode');
    if (!control) return;
    try {
      await nativeFetch('/api/settings/invoice-layout', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ show_product_code: !!control.checked }),
      });
    } catch (_) {}
  }

  async function resetSite() {
    if (!window.confirm('سيتم إرجاع إعدادات الموقع واللوجو والطباعة والواجهة للوضع الافتراضي. الفواتير والمنتجات والعملاء لن يتم حذفهم. هل تريد المتابعة؟')) return;
    const btn = byId('resetWebsiteBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'جاري الـ Reset...'; }
    try {
      const response = await nativeFetch('/api/settings/reset-site', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }, body: '{}',
      });
      if (!response.ok) {
        let msg = 'تعذر تنفيذ Reset';
        try { const data = await response.json(); msg = data.detail || msg; } catch (_) {}
        throw new Error(msg);
      }
      localStorage.removeItem('pos_theme');
      localStorage.removeItem('theme');
      location.reload();
    } catch (err) {
      alert(err.message || 'تعذر تنفيذ Reset');
      if (btn) { btn.disabled = false; btn.textContent = 'Reset'; }
    }
  }

  function installSaveHook() {
    const save = byId('saveSettingsBtn');
    if (!save || save.dataset.ownerV4Bound === '1') return;
    save.dataset.ownerV4Bound = '1';
    save.addEventListener('click', () => {
      saveInvoiceLayoutSetting();
      setTimeout(refreshBranding, 700);
      setTimeout(loadInvoiceLayoutSetting, 700);
    });
  }

  function installInvoiceMetaFetchHook() {
    if (window.__ownerInvoiceMetaFetchV4) return;
    window.__ownerInvoiceMetaFetchV4 = true;
    window.fetch = async function(input, init) {
      const requestUrl = typeof input === 'string' ? input : (input?.url || '');
      const method = String(init?.method || (typeof input !== 'string' ? input?.method : 'GET') || 'GET').toUpperCase();
      const cleanUrl = requestUrl.split('?', 1)[0];
      if (method !== 'POST' || !/\/api\/invoices\/?$/.test(cleanUrl)) {
        return nativeFetch(input, init);
      }

      const phone = String(byId('invoicePrintPhone')?.value || '').trim().slice(0, 40);
      const address = String(byId('invoicePrintAddress')?.value || '').trim().slice(0, 300);
      let nextInit = init ? { ...init } : {};
      try {
        if (typeof nextInit.body === 'string') {
          const payload = JSON.parse(nextInit.body);
          payload.customer_phone = phone;
          nextInit.body = JSON.stringify(payload);
        }
      } catch (_) {}

      const response = await nativeFetch(input, nextInit);
      if (response.ok) {
        try {
          const result = await response.clone().json();
          if (result?.id) {
            const metaResponse = await nativeFetch(`/api/invoices/${encodeURIComponent(result.id)}/display-meta`, {
              method: 'POST', credentials: 'same-origin',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ phone, address }),
            });
            if (!metaResponse.ok) console.warn('Invoice optional metadata was not persisted');
          }
          const phoneEl = byId('invoicePrintPhone'); if (phoneEl) phoneEl.value = '';
          const addressEl = byId('invoicePrintAddress'); if (addressEl) addressEl.value = '';
        } catch (_) {}
      }
      return response;
    };
  }

  function boot() {
    installDocumentIdentity();
    installStyles();
    installOptionalInvoiceFields();
    installPosLabels();
    installSettingsCard();
    installSaveHook();
    installInvoiceMetaFetchHook();
    refreshBranding();

    document.querySelector('.nav-item[data-page="settings"]')?.addEventListener('click', () => setTimeout(() => {
      installSettingsCard(); installSaveHook(); loadInvoiceLayoutSetting();
    }, 30));

    const app = byId('app');
    if (app) new MutationObserver(() => {
      installOptionalInvoiceFields(); installSettingsCard(); installSaveHook(); installPosLabels();
    }).observe(app, { attributes: true, childList: true, subtree: false });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
