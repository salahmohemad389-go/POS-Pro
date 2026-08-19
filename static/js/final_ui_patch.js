/* Final POS UI adjustments layered after upgrade_dom.js. No external assets. */
(() => {
  const byId = id => document.getElementById(id);

  const style = document.createElement('style');
  style.textContent = `
    #loginDynamicLogo{display:none;align-items:center;justify-content:center;margin:0 auto 12px;width:auto;height:auto;min-height:0;background:transparent!important;box-shadow:none!important}
    #loginDynamicLogo.has-logo{display:flex}
    #loginDynamicLogo img{display:block;max-width:180px;max-height:105px;width:auto;height:auto;object-fit:contain;border-radius:12px}
    .sidebar-header>.logo{display:none!important}
  `;
  document.head.appendChild(style);

  // The settings logo is the only visual logo. Remove the hard-coded POS mark.
  const oldLoginLogo = document.querySelector('.login-box .login-logo');
  if (oldLoginLogo) {
    oldLoginLogo.id = 'loginDynamicLogo';
    oldLoginLogo.classList.remove('login-logo');
    oldLoginLogo.textContent = '';
  }
  document.querySelector('.sidebar-header>.logo')?.remove();

  async function refreshPublicBranding() {
    try {
      const response = await fetch('/api/branding', { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) return;
      const branding = await response.json();
      const host = byId('loginDynamicLogo');
      if (host) {
        host.replaceChildren();
        const logo = String(branding.logo || '');
        if (logo.startsWith('data:image/')) {
          const img = document.createElement('img');
          img.src = logo; img.alt = 'شعار المتجر';
          host.appendChild(img); host.classList.add('has-logo');
        } else {
          host.classList.remove('has-logo');
        }
      }
      const name = String(branding.store_name || 'POS').trim() || 'POS';
      const tagline = String(branding.tagline || '').trim();
      const loginName = byId('loginStoreName'); if (loginName) loginName.textContent = name;
      const loginTagline = byId('loginTagline'); if (loginTagline) { loginTagline.textContent = tagline; loginTagline.style.display = tagline ? '' : 'none'; }
    } catch (_) {}
  }

  function ensureExtraFeatureToggles() {
    const box = document.querySelector('#page-settings .settings-feature-box');
    if (!box) return;
    const anchor = box.querySelector('small');
    if (!byId('setFeatureProducts')) {
      const label = document.createElement('label'); label.className = 'toggle-label';
      label.innerHTML = '<input type="checkbox" id="setFeatureProducts" checked> المنتجات والأقسام';
      box.insertBefore(label, anchor || null);
    }
    if (!byId('setFeatureAudit')) {
      const label = document.createElement('label'); label.className = 'toggle-label';
      label.innerHTML = '<input type="checkbox" id="setFeatureAudit" checked> سجل العمليات';
      box.insertBefore(label, anchor || null);
    }
  }

  async function refreshAdvancedFeatures() {
    ensureExtraFeatureToggles();
    try {
      const response = await fetch('/api/settings', { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) return;
      const settings = await response.json();
      const productsOn = settings.feature_products_enabled !== false;
      const auditOn = settings.feature_audit_enabled !== false;
      const p = byId('setFeatureProducts'); if (p) p.checked = productsOn;
      const a = byId('setFeatureAudit'); if (a) a.checked = auditOn;
      const productNav = document.querySelector('.nav-item[data-page="products"]');
      const auditNav = document.querySelector('.nav-item[data-page="audit"]');
      if (productNav) productNav.style.display = productsOn ? '' : 'none';
      if (auditNav) auditNav.style.display = auditOn ? '' : 'none';
    } catch (_) {}
  }

  async function saveAdvancedFeatures() {
    ensureExtraFeatureToggles();
    const products = byId('setFeatureProducts');
    const audit = byId('setFeatureAudit');
    if (!products || !audit) return;
    try {
      await fetch('/api/settings/ui', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feature_products_enabled: products.checked, feature_audit_enabled: audit.checked }),
      });
      setTimeout(refreshAdvancedFeatures, 150);
    } catch (_) {}
  }

  ensureExtraFeatureToggles();
  refreshPublicBranding();

  // Registered before app.js handlers: the server merges this small UI payload,
  // so it is safe alongside the normal settings save request.
  byId('saveSettingsBtn')?.addEventListener('click', () => {
    saveAdvancedFeatures();
    setTimeout(refreshPublicBranding, 700);
    setTimeout(refreshAdvancedFeatures, 700);
  });

  byId('setLogoInput')?.addEventListener('change', event => {
    const file = event.target.files?.[0]; if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const host = byId('loginDynamicLogo'); if (!host) return;
      host.replaceChildren(); const img = document.createElement('img'); img.src = String(reader.result || ''); img.alt = 'شعار المتجر'; host.appendChild(img); host.classList.add('has-logo');
    };
    reader.readAsDataURL(file);
  });

  const app = byId('app');
  if (app) new MutationObserver(() => { if (app.style.display !== 'none') refreshAdvancedFeatures(); }).observe(app, { attributes: true, attributeFilter: ['style'] });
  const login = byId('loginScreen');
  if (login) new MutationObserver(() => { if (login.style.display !== 'none') refreshPublicBranding(); }).observe(login, { attributes: true, attributeFilter: ['style'] });
})();
