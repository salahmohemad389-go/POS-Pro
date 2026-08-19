import { S } from '../core/state.js';
import { API } from '../core/api.js';
import { Util } from '../core/util.js';

function hasPermission(name) { return !!(S.user && Array.isArray(S.user.permissions) && S.user.permissions.includes(name)); }

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
    const s = S.settings || {}; const name = s.store_name || 'POS'; const tagline = s.tagline || 'نظام نقاط البيع'; const logo = s.logo || '';
    document.title = name;
    [['storeName', name], ['loginStoreName', name], ['loginTagline', tagline], ['sidebarTagline', tagline]].forEach(([id, value]) => { const el = document.getElementById(id); if (el) el.textContent = value; });
    [['loginLogoImg', 'loginLogoFallback'], ['sidebarLogoImg', 'sidebarLogoFallback']].forEach(([imgId, fallbackId]) => {
      const img = document.getElementById(imgId); const fallback = document.getElementById(fallbackId); if (!img || !fallback) return;
      if (logo) { img.src = logo; img.hidden = false; fallback.hidden = true; } else { img.removeAttribute('src'); img.hidden = true; fallback.hidden = false; }
    });
  },
  nav(page) {
    if (!page) return; const navEl = document.querySelector(`.nav-item[data-page="${page}"]`); if (navEl && !navEl.classList.contains('show')) return;
    S.currentPage = page; document.querySelectorAll('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.page === page));
    document.querySelectorAll('.page').forEach(el => el.classList.toggle('active', el.id === `page-${page}`));
    const titles = { pos:'نقطة البيع', products:'المنتجات', categories:'الأقسام', customers:'العملاء', invoices:'الفواتير', suppliers:'الموردون', reports:'التقارير', users:'المستخدمون', settings:'الإعدادات', audit:'سجل العمليات' };
    const title = document.getElementById('pageTitle'); if (title) title.textContent = titles[page] || page; this.renderPage(page); document.getElementById('sidebar')?.classList.remove('open');
  },
  renderPage(p) {
    switch (p) { case 'pos': this.renderPOS(); break; case 'products': this.loadProductsPage(); break; case 'categories': this.loadCategoriesPage(); break; case 'customers': this.renderCustomers(); break; case 'invoices': this.loadInvoicesPage(); break; case 'suppliers': this.loadSuppliersPage(); break; case 'reports': this.loadReport(); break; case 'users': this.loadUsersPage(); break; case 'settings': this.renderSettings(); break; case 'audit': this.loadAuditPage(); break; }
  },
  renderPagination(containerId, data, pageType) {
    const el = document.getElementById(containerId); if (!el) return; const total = data.total || 0; const limit = data.limit || 50; const page = data.page || 1; const pages = Math.ceil(total / limit);
    if (total === 0) { el.innerHTML = ''; return; } if (pages <= 1) { el.innerHTML = `<small style="color:var(--g500)">${total} سجل</small>`; return; }
    let html = `<button data-page="1" ${page === 1 ? 'disabled' : ''}>« الأولى</button><button data-page="${page - 1}" ${page === 1 ? 'disabled' : ''}>‹ السابق</button>`;
    const start = Math.max(1, page - 2); const end = Math.min(pages, start + 4); for (let i = start; i <= end; i++) html += `<button data-page="${i}" class="${i === page ? 'active' : ''}">${i}</button>`;
    html += `<button data-page="${page + 1}" ${page === pages ? 'disabled' : ''}>التالي ›</button><button data-page="${pages}" ${page === pages ? 'disabled' : ''}>الأخيرة »</button><small style="margin-right:10px;color:var(--g500)">صفحة ${page}/${pages} • ${total} سجل</small>`;
    el.innerHTML = html; el.querySelectorAll('button[data-page]').forEach(b => b.addEventListener('click', () => { const newPage = parseInt(b.dataset.page); if (pageType === 'products') { S.productsPage.page = newPage; this.loadProductsPage(); } else if (pageType === 'customers') { S.customersPage.page = newPage; this.loadCustomersPage(); } else if (pageType === 'suppliers') { S.suppliersPage.page = newPage; this.loadSuppliersPage(); } else if (pageType === 'invoices') { S.invoices.page = newPage; this.clearInvoicesSelection(); this.loadInvoicesPage(); } else if (pageType === 'audit') { S.audit.page = newPage; this.loadAuditPage(); } }));
  },
  toast(msg, type = 'success') { const c = document.getElementById('toastContainer'); if (!c) return; const t = document.createElement('div'); t.className = `toast toast-${type}`; t.textContent = msg; c.appendChild(t); setTimeout(() => { t.style.opacity = '0'; t.style.transform = 'translateX(-100%)'; setTimeout(() => t.remove(), 300); }, 2500); },
  confirm(title, msg) { return new Promise(res => { const m = document.getElementById('confirmModal'); document.getElementById('confirmTitle').textContent = title; document.getElementById('confirmMsg').textContent = msg; m.classList.add('active'); const yes = document.getElementById('confirmYes'); const no = document.getElementById('confirmNo'); const cleanup = () => { m.classList.remove('active'); yes.onclick = null; no.onclick = null; }; yes.onclick = () => { cleanup(); res(true); }; no.onclick = () => { cleanup(); res(false); }; }); },
  closeModal(id) { document.getElementById(id)?.classList.remove('active'); if (id === 'pdfPreviewModal' && S._pdfPreviewUrl) { const frame = document.getElementById('pdfPreviewFrame'); if (frame) frame.src = 'about:blank'; URL.revokeObjectURL(S._pdfPreviewUrl); S._pdfPreviewUrl = null; } },
  renderSettings() {
    const s = S.settings || {}; const setValue = (id, value) => { const el = document.getElementById(id); if (el) el.value = value ?? ''; };
    [['setStoreName', s.store_name || ''], ['setTagline', s.tagline || ''], ['setSlogan', s.slogan || ''], ['setBranch', s.branch || ''], ['setPhone', s.phone || ''], ['setAddress', s.address || ''], ['setCurrency', s.currency || 'ج.م'], ['setTaxRate', s.tax_rate || 0], ['setCopies', s.copies || 1], ['setFooter', s.footer || ''], ['setQuickQty', s.quick_qty || '1,5,10,20,30,50,100'], ['setPrinterType', s.printer_type || 'browser'], ['setInvoiceFormat', s.invoice_format || 'a4'], ['setCustomLines', s.custom_lines || ''], ['setHeaderNote', s.header_note || ''], ['setWarrantyText', s.warranty_text || ''], ['setTermsConditions', s.terms_conditions || ''], ['setMaxItemsPerPage', s.max_items_per_page || 15], ['settingsCurrentLogin', S.user?.login || '']].forEach(([id,v]) => setValue(id,v));
    const checked = (id, value) => { const el = document.getElementById(id); if (el) el.checked = !!value; }; checked('setVatEnabled', s.vat_enabled); checked('setAutoPrint', s.auto_print_after_sale); checked('setFeatureReports', s.feature_reports_enabled !== false); checked('setFeatureSuppliers', s.feature_suppliers_enabled !== false);
    const preview = document.getElementById('logoPreview'); if (preview) preview.innerHTML = s.logo ? `<img src="${s.logo}" alt="شعار المتجر">` : ''; if (hasPermission('backup_create')) this.loadBackupsList();
  },
  previewLogo(input) { const f = input.files[0]; if (!f) return; const r = new FileReader(); r.onload = e => { document.getElementById('logoPreview').innerHTML = `<img src="${e.target.result}" alt="شعار المتجر">`; S.settings.logo = e.target.result; this.applyBranding(); }; r.readAsDataURL(f); },
  async saveSettings() {
    try {
      const payload = { store_name: document.getElementById('setStoreName').value.trim(), tagline: document.getElementById('setTagline').value.trim(), slogan: document.getElementById('setSlogan').value.trim(), branch: document.getElementById('setBranch').value.trim(), phone: document.getElementById('setPhone').value.trim(), address: document.getElementById('setAddress').value.trim(), currency: document.getElementById('setCurrency').value.trim() || 'ج.م', tax_rate: parseFloat(document.getElementById('setTaxRate').value) || 0, vat_enabled: document.getElementById('setVatEnabled').checked, copies: parseInt(document.getElementById('setCopies').value) || 1, footer: document.getElementById('setFooter').value.trim(), quick_qty: document.getElementById('setQuickQty').value.trim() || '1,5,10,20,30,50,100', printer_type: document.getElementById('setPrinterType').value, invoice_format: document.getElementById('setInvoiceFormat').value, auto_print_after_sale: document.getElementById('setAutoPrint').checked, custom_lines: document.getElementById('setCustomLines').value, header_note: document.getElementById('setHeaderNote').value.trim(), warranty_text: document.getElementById('setWarrantyText').value.trim(), terms_conditions: document.getElementById('setTermsConditions').value, max_items_per_page: parseInt(document.getElementById('setMaxItemsPerPage').value) || 15, logo: S.settings.logo || '', feature_reports_enabled: document.getElementById('setFeatureReports').checked, feature_suppliers_enabled: document.getElementById('setFeatureSuppliers').checked };
      await API.post('/api/settings', payload); await this.loadSettings(); this.applyPermissions(); this.renderQuickQty(); this.recalcCart(); this.toast('تم حفظ الإعدادات');
    } catch (e) { this.toast(e.message, 'error'); }
  },
  async changeCredentialsFromSettings() {
    const login = document.getElementById('settingsNewLogin').value.trim(); const password = document.getElementById('settingsNewPass').value; const currentPassword = document.getElementById('settingsCurrentPass').value;
    if (!login && !password) { this.toast('أدخل اسم دخول أو كلمة مرور جديدة', 'warning'); return; }
    try { const r = await API.post('/api/auth/change-credentials', { login: login || undefined, password: password || undefined, current_password: currentPassword || undefined }); S.user = r.user; ['settingsNewLogin', 'settingsNewPass', 'settingsCurrentPass'].forEach(id => { document.getElementById(id).value = ''; }); document.getElementById('settingsCurrentLogin').value = r.user.login; const legacy = document.getElementById('curLogin'); if (legacy) legacy.value = r.user.login; this.toast('تم تحديث بيانات الدخول وإلغاء الجلسات القديمة'); }
    catch (e) { this.toast(e.message, 'error'); }
  },
  async loadBackupsList() {
    if (!hasPermission('backup_create')) return;
    try { const list = await API.get('/api/backup/list', { dedupe: false }); const el = document.getElementById('backupsList'); if (!el) return; if (!list.length) { el.innerHTML = '<div style="color:var(--g500);font-size:12px;margin-top:8px">لا توجد نسخ احتياطية</div>'; return; } el.innerHTML = list.map(b => `<div class="backup-item"><div><strong>${Util.esc(b.name)}</strong><br><small style="color:var(--g500)">${Util.shortDate(b.created_at)} • ${(b.size / 1024).toFixed(1)} KB</small></div><div class="backup-item-actions"><a class="btn btn-sm" href="/api/backup/download/${encodeURIComponent(b.name)}" download>تنزيل</a>${hasPermission('backup_restore') ? `<button class="btn btn-sm btn-warning" data-restore="${Util.esc(b.name)}">استعادة</button>` : ''}</div></div>`).join(''); el.querySelectorAll('[data-restore]').forEach(b => b.addEventListener('click', () => this.restoreBackup(b.dataset.restore))); } catch (e) {}
  },
  async backup() { if (!hasPermission('backup_create')) { this.toast('لا تملك صلاحية النسخ الاحتياطي', 'error'); return; } try { await API.post('/api/backup', {}); this.toast('تم إنشاء نسخة احتياطية'); await this.loadBackupsList(); } catch (e) { this.toast(e.message, 'error'); } },
  async restoreBackup(name) { if (!hasPermission('backup_restore')) { this.toast('لا تملك صلاحية الاستعادة', 'error'); return; } if (!await this.confirm('استعادة نسخة احتياطية', `سيتم استبدال كل البيانات الحالية بـ "${name}". هل أنت متأكد؟`)) return; try { await API.post('/api/backup/restore', { name }); this.toast('تمت الاستعادة. سيتم تحديث البيانات.', 'success'); setTimeout(() => location.reload(), 1500); } catch (e) { this.toast(e.message, 'error'); } },
};
