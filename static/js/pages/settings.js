import { S } from '../core/state.js';
import { API } from '../core/api.js';
import { Util } from '../core/util.js';

function hasPermission(name) { return !!(S.user && Array.isArray(S.user.permissions) && S.user.permissions.includes(name)); }
const get = id => document.getElementById(id);
const setValue = (id, value) => { const el = get(id); if (el) el.value = value ?? ''; };
const setChecked = (id, value) => { const el = get(id); if (el) el.checked = !!value; };

const SHORTCUT_FIELDS = {
  shortcutNewSale: 'shortcut_new_sale',
  shortcutSearch: 'shortcut_search',
  shortcutReturn: 'shortcut_return',
  shortcutCash: 'shortcut_cash',
  shortcutCredit: 'shortcut_credit',
  shortcutPartial: 'shortcut_partial',
  shortcutClearCart: 'shortcut_clear_cart',
  shortcutSidebar: 'shortcut_sidebar',
  shortcutInvoices: 'shortcut_invoices',
};

function safeColor(value, fallback) {
  const v = String(value || '').trim();
  return /^#[0-9a-fA-F]{6}$/.test(v) ? v.toLowerCase() : fallback;
}

export const settingsMethods = {
  async loadPublicBranding() {
    try { const branding = await API.get('/api/branding', { dedupe: false }); S.settings = { ...S.settings, ...branding }; this.applyBranding(); }
    catch (e) { console.warn('Branding load failed:', e); }
  },
  async loadSettings() {
    try { S.settings = await API.get('/api/settings', { dedupe: false }); this.applyBranding(); }
    catch (e) { console.error('Settings load failed:', e); throw e; }
  },
  applyBranding() {
    const s = S.settings || {};
    const name = (s.store_name || 'POS').trim() || 'POS';
    const tagline = (s.tagline || '').trim();
    document.title = name;
    [['storeName', name], ['loginStoreName', name], ['loginTagline', tagline], ['sidebarTagline', tagline]].forEach(([id, value]) => {
      const el = get(id); if (!el) return; el.textContent = value; el.style.display = value ? '' : 'none';
    });
    const primary = safeColor(s.primary_color, '#2563eb');
    const accent = safeColor(s.accent_color, '#0891b2');
    document.documentElement.style.setProperty('--p', primary);
    document.documentElement.style.setProperty('--info', accent);
    document.documentElement.style.setProperty('--brand-primary', primary);
    document.documentElement.style.setProperty('--brand-accent', accent);
    if (typeof this.installUIEnhancements === 'function') this.installUIEnhancements();
  },
  nav(page) {
    if (!page) return; const navEl = document.querySelector(`.nav-item[data-page="${page}"]`); if (navEl && !navEl.classList.contains('show')) return;
    S.currentPage = page; document.querySelectorAll('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.page === page));
    document.querySelectorAll('.page').forEach(el => el.classList.toggle('active', el.id === `page-${page}`));
    const titles = { pos:'نقطة البيع', products:'المنتجات', categories:'الأقسام', customers:'العملاء', invoices:'الفواتير', suppliers:'الموردون', reports:'التقارير', users:'المستخدمون', settings:'الإعدادات', audit:'سجل العمليات' };
    const title = get('pageTitle'); if (title) title.textContent = titles[page] || page; this.renderPage(page); get('sidebar')?.classList.remove('open');
  },
  renderPage(p) {
    switch (p) { case 'pos': this.renderPOS(); break; case 'products': this.loadProductsPage(); break; case 'categories': this.loadCategoriesPage(); break; case 'customers': this.renderCustomers(); break; case 'invoices': this.loadInvoicesPage(); break; case 'suppliers': this.loadSuppliersPage(); break; case 'reports': this.loadReport(); break; case 'users': this.loadUsersPage(); break; case 'settings': this.renderSettings(); break; case 'audit': this.loadAuditPage(); break; }
  },
  renderPagination(containerId, data, pageType) {
    const el = get(containerId); if (!el) return; const total = data.total || 0; const limit = data.limit || 50; const page = data.page || 1; const pages = Math.ceil(total / limit);
    if (total === 0) { el.innerHTML = ''; return; } if (pages <= 1) { el.innerHTML = `<small style="color:var(--g500)">${total} سجل</small>`; return; }
    let html = `<button data-page="1" ${page === 1 ? 'disabled' : ''}>« الأولى</button><button data-page="${page - 1}" ${page === 1 ? 'disabled' : ''}>‹ السابق</button>`;
    const start = Math.max(1, page - 2); const end = Math.min(pages, start + 4); for (let i = start; i <= end; i++) html += `<button data-page="${i}" class="${i === page ? 'active' : ''}">${i}</button>`;
    html += `<button data-page="${page + 1}" ${page === pages ? 'disabled' : ''}>التالي ›</button><button data-page="${pages}" ${page === pages ? 'disabled' : ''}>الأخيرة »</button><small style="margin-right:10px;color:var(--g500)">صفحة ${page}/${pages} • ${total} سجل</small>`;
    el.innerHTML = html; el.querySelectorAll('button[data-page]').forEach(b => b.addEventListener('click', () => { const newPage = parseInt(b.dataset.page); if (pageType === 'products') { S.productsPage.page = newPage; this.loadProductsPage(); } else if (pageType === 'customers') { S.customersPage.page = newPage; this.loadCustomersPage(); } else if (pageType === 'suppliers') { S.suppliersPage.page = newPage; this.loadSuppliersPage(); } else if (pageType === 'invoices') { S.invoices.page = newPage; this.clearInvoicesSelection(); this.loadInvoicesPage(); } else if (pageType === 'audit') { S.audit.page = newPage; this.loadAuditPage(); } }));
  },
  toast(msg, type = 'success') { const c = get('toastContainer'); if (!c) return; const t = document.createElement('div'); t.className = `toast toast-${type}`; t.textContent = msg; c.appendChild(t); setTimeout(() => { t.style.opacity = '0'; t.style.transform = 'translateX(-100%)'; setTimeout(() => t.remove(), 300); }, 2500); },
  confirm(title, msg) { return new Promise(res => { const m = get('confirmModal'); get('confirmTitle').textContent = title; get('confirmMsg').textContent = msg; m.classList.add('active'); const yes = get('confirmYes'); const no = get('confirmNo'); const cleanup = () => { m.classList.remove('active'); yes.onclick = null; no.onclick = null; }; yes.onclick = () => { cleanup(); res(true); }; no.onclick = () => { cleanup(); res(false); }; }); },
  closeModal(id) { get(id)?.classList.remove('active'); if (id === 'pdfPreviewModal' && S._pdfPreviewUrl) { const frame = get('pdfPreviewFrame'); if (frame) frame.src = 'about:blank'; URL.revokeObjectURL(S._pdfPreviewUrl); S._pdfPreviewUrl = null; } },
  renderSettings() {
    const s = S.settings || {};
    [
      ['setStoreName', s.store_name || 'POS'], ['setTagline', s.tagline || ''], ['setSlogan', s.slogan || ''], ['setBranch', s.branch || ''], ['setPhone', s.phone || ''], ['setAddress', s.address || ''],
      ['setCurrency', s.currency || 'ج.م'], ['setTaxRate', s.tax_rate || 0], ['setCopies', s.copies || 1], ['setFooter', s.footer || ''], ['setQuickQty', s.quick_qty || '1,5,10,20,30,50,100'],
      ['setPrinterType', s.printer_type || 'browser'], ['setInvoiceFormat', s.invoice_format || 'a4'], ['setCustomLines', s.custom_lines || ''], ['setHeaderNote', s.header_note || ''],
      ['setWarrantyText', s.warranty_text || ''], ['setTermsConditions', s.terms_conditions || ''], ['setMaxItemsPerPage', s.max_items_per_page || 15], ['settingsCurrentLogin', S.user?.login || ''],
      ['setPrimaryColor', safeColor(s.primary_color, '#2563eb')], ['setPrimaryColorText', safeColor(s.primary_color, '#2563eb')], ['setAccentColor', safeColor(s.accent_color, '#0891b2')], ['setAccentColorText', safeColor(s.accent_color, '#0891b2')],
    ].forEach(([id, v]) => setValue(id, v));
    setChecked('setVatEnabled', s.vat_enabled); setChecked('setAutoPrint', s.auto_print_after_sale);
    setChecked('setFeatureReports', s.feature_reports_enabled !== false); setChecked('setFeatureSuppliers', s.feature_suppliers_enabled !== false);
    setChecked('setFeatureInvoices', s.feature_invoices_enabled !== false); setChecked('setFeatureCustomers', s.feature_customers_enabled !== false); setChecked('setQuickQtyEnabled', s.quick_qty_enabled !== false);
    Object.entries(SHORTCUT_FIELDS).forEach(([id, key]) => setValue(id, s[key] || ''));
    const preview = get('logoPreview'); if (preview) preview.innerHTML = s.logo ? `<img src="${s.logo}" alt="شعار الفاتورة">` : '<small>لا يوجد شعار للفاتورة</small>';
    this.bindAppearanceInputs();
    if (hasPermission('backup_create')) this.loadBackupsList();
  },
  bindAppearanceInputs() {
    const pairs = [['setPrimaryColor', 'setPrimaryColorText', '--p'], ['setAccentColor', 'setAccentColorText', '--info']];
    pairs.forEach(([pickerId, textId, cssVar]) => {
      const picker = get(pickerId), text = get(textId); if (!picker || !text || picker.dataset.bound === '1') return;
      picker.dataset.bound = '1';
      picker.addEventListener('input', () => { text.value = picker.value; document.documentElement.style.setProperty(cssVar, picker.value); });
      text.addEventListener('input', () => { if (/^#[0-9a-fA-F]{6}$/.test(text.value)) { picker.value = text.value; document.documentElement.style.setProperty(cssVar, text.value); } });
    });
    document.querySelectorAll('.shortcut-input').forEach(input => {
      if (input.dataset.captureBound === '1') return; input.dataset.captureBound = '1';
      input.addEventListener('keydown', e => {
        if (e.key === 'Tab') return;
        e.preventDefault();
        if (e.key === 'Backspace' || e.key === 'Delete' || e.key === 'Escape') { input.value = ''; return; }
        const mods = []; if (e.ctrlKey) mods.push('Ctrl'); if (e.altKey) mods.push('Alt'); if (e.shiftKey) mods.push('Shift');
        let key = e.key.length === 1 ? e.key.toUpperCase() : e.key.toUpperCase();
        if (!/^(F([1-9]|1[0-2])|[A-Z0-9])$/.test(key)) return;
        input.value = [...mods, key].join('+');
      });
    });
  },
  previewLogo(input) {
    const f = input.files[0]; if (!f) return;
    const r = new FileReader(); r.onload = e => { const preview = get('logoPreview'); if (preview) preview.innerHTML = `<img src="${e.target.result}" alt="شعار الفاتورة">`; S.settings.logo = e.target.result; }; r.readAsDataURL(f);
  },
  async saveSettings() {
    try {
      const corePayload = {
        store_name: get('setStoreName').value.trim() || 'POS', tagline: get('setTagline').value.trim(), slogan: get('setSlogan').value.trim(), branch: get('setBranch').value.trim(), phone: get('setPhone').value.trim(), address: get('setAddress').value.trim(),
        currency: get('setCurrency').value.trim() || 'ج.م', tax_rate: parseFloat(get('setTaxRate').value) || 0, vat_enabled: get('setVatEnabled').checked, copies: parseInt(get('setCopies').value) || 1,
        footer: get('setFooter').value.trim(), quick_qty: get('setQuickQty').value.trim() || '1,5,10,20,30,50,100', printer_type: get('setPrinterType').value, invoice_format: get('setInvoiceFormat').value,
        auto_print_after_sale: get('setAutoPrint').checked, custom_lines: get('setCustomLines').value, header_note: get('setHeaderNote').value.trim(), warranty_text: get('setWarrantyText').value.trim(), terms_conditions: get('setTermsConditions').value,
        max_items_per_page: parseInt(get('setMaxItemsPerPage').value) || 15, logo: S.settings.logo || '', feature_reports_enabled: get('setFeatureReports')?.checked !== false, feature_suppliers_enabled: get('setFeatureSuppliers')?.checked !== false,
      };
      const uiPayload = {
        feature_invoices_enabled: get('setFeatureInvoices')?.checked !== false,
        feature_customers_enabled: get('setFeatureCustomers')?.checked !== false,
        quick_qty_enabled: get('setQuickQtyEnabled')?.checked !== false,
        primary_color: safeColor(get('setPrimaryColorText')?.value || get('setPrimaryColor')?.value, '#2563eb'),
        accent_color: safeColor(get('setAccentColorText')?.value || get('setAccentColor')?.value, '#0891b2'),
      };
      Object.entries(SHORTCUT_FIELDS).forEach(([id, key]) => { uiPayload[key] = get(id)?.value.trim() || ''; });
      await API.post('/api/settings', corePayload);
      await API.post('/api/settings/ui', uiPayload);
      await this.loadSettings(); this.applyPermissions(); this.renderQuickQty(); this.recalcCart(); this.toast('تم حفظ إعدادات النظام والواجهة');
    } catch (e) { this.toast(e.message, 'error'); }
  },
  async changeCredentialsFromSettings() {
    const login = get('settingsNewLogin').value.trim(); const password = get('settingsNewPass').value; const currentPassword = get('settingsCurrentPass').value;
    if (!login && !password) { this.toast('أدخل اسم دخول أو كلمة مرور جديدة', 'warning'); return; }
    try { const r = await API.post('/api/auth/change-credentials', { login: login || undefined, password: password || undefined, current_password: currentPassword || undefined }); S.user = r.user; ['settingsNewLogin', 'settingsNewPass', 'settingsCurrentPass'].forEach(id => { get(id).value = ''; }); get('settingsCurrentLogin').value = r.user.login; const legacy = get('curLogin'); if (legacy) legacy.value = r.user.login; this.toast('تم تحديث بيانات الدخول وإلغاء الجلسات القديمة'); }
    catch (e) { this.toast(e.message, 'error'); }
  },
  async loadBackupsList() {
    if (!hasPermission('backup_create')) return;
    try { const list = await API.get('/api/backup/list', { dedupe: false }); const el = get('backupsList'); if (!el) return; if (!list.length) { el.innerHTML = '<div style="color:var(--g500);font-size:12px;margin-top:8px">لا توجد نسخ احتياطية</div>'; return; } el.innerHTML = list.map(b => `<div class="backup-item"><div><strong>${Util.esc(b.name)}</strong><br><small style="color:var(--g500)">${Util.shortDate(b.created_at)} • ${(b.size / 1024).toFixed(1)} KB</small></div><div class="backup-item-actions"><a class="btn btn-sm" href="/api/backup/download/${encodeURIComponent(b.name)}" download>تنزيل</a>${hasPermission('backup_restore') ? `<button class="btn btn-sm btn-warning" data-restore="${Util.esc(b.name)}">استعادة</button>` : ''}</div></div>`).join(''); el.querySelectorAll('[data-restore]').forEach(b => b.addEventListener('click', () => this.restoreBackup(b.dataset.restore))); } catch (e) {}
  },
  async backup() { if (!hasPermission('backup_create')) { this.toast('لا تملك صلاحية النسخ الاحتياطي', 'error'); return; } try { await API.post('/api/backup', {}); this.toast('تم إنشاء نسخة احتياطية'); await this.loadBackupsList(); } catch (e) { this.toast(e.message, 'error'); } },
  async restoreBackup(name) { if (!hasPermission('backup_restore')) { this.toast('لا تملك صلاحية الاستعادة', 'error'); return; } if (!await this.confirm('استعادة نسخة احتياطية', `سيتم استبدال كل البيانات الحالية بـ "${name}". هل أنت متأكد؟`)) return; try { await API.post('/api/backup/restore', { name }); this.toast('تمت الاستعادة. سيتم تحديث البيانات.', 'success'); setTimeout(() => location.reload(), 1500); } catch (e) { this.toast(e.message, 'error'); } },
};
