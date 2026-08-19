import { S } from '../core/state.js';
import { API } from '../core/api.js';
import { Util } from '../core/util.js';

export const settingsMethods = {
  async loadSettings() {
    try {
      S.settings = await API.get('/api/settings');
    } catch (e) {
      console.error('Settings load failed:', e);
    }
  },

  /* ─── NAVIGATION ─── */
  nav(page) {
    if (!page) return;
    S.currentPage = page;
    document.querySelectorAll('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.page === page));
    document.querySelectorAll('.page').forEach(el => el.classList.toggle('active', el.id === `page-${page}`));
    const titles = { pos:'نقطة البيع', products:'المنتجات', categories:'الأقسام', customers:'العملاء', invoices:'الفواتير', suppliers:'الموردون', reports:'التقارير', users:'المستخدمون', settings:'الإعدادات', audit:'سجل العمليات' };
    document.getElementById('pageTitle').textContent = titles[page] || page;
    this.renderPage(page);
    document.getElementById('sidebar').classList.remove('open');
  },

  renderPage(p) {
    switch (p) {
      case 'pos': this.renderPOS(); break;
      case 'products': this.loadProductsPage(); break;
      case 'categories': this.loadCategoriesPage(); break;
      case 'customers': this.renderCustomers(); break;
      case 'invoices': this.loadInvoicesPage(); break;
      case 'suppliers': this.loadSuppliersPage(); break;
      case 'reports': this.loadReport(); break;
      case 'users': this.loadUsersPage(); break;
      case 'settings': this.renderSettings(); break;
      case 'audit': this.loadAuditPage(); break;
    }
  },

  // Pagination renderer (called by all list pages)
  renderPagination(containerId, data, pageType) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const total = data.total || 0;
    const limit = data.limit || 50;
    const page = data.page || 1;
    const pages = Math.ceil(total / limit);
    if (total === 0) { el.innerHTML = ''; return; }
    if (pages <= 1) {
      el.innerHTML = `<small style="color:var(--g500)">${total} سجل</small>`;
      return;
    }
    let html = `<button data-page="1" ${page === 1 ? 'disabled' : ''}>« الأولى</button>`;
    html += `<button data-page="${page - 1}" ${page === 1 ? 'disabled' : ''}>‹ السابق</button>`;
    // Show up to 5 page buttons around current
    const start = Math.max(1, page - 2);
    const end = Math.min(pages, start + 4);
    for (let i = start; i <= end; i++) {
      html += `<button data-page="${i}" class="${i === page ? 'active' : ''}">${i}</button>`;
    }
    html += `<button data-page="${page + 1}" ${page === pages ? 'disabled' : ''}>التالي ›</button>`;
    html += `<button data-page="${pages}" ${page === pages ? 'disabled' : ''}>الأخيرة »</button>`;
    html += `<small style="margin-right:10px;color:var(--g500)">صفحة ${page}/${pages} • ${total} سجل</small>`;
    el.innerHTML = html;
    // Bind click handlers
    el.querySelectorAll('button[data-page]').forEach(b => {
      b.addEventListener('click', () => {
        const newPage = parseInt(b.dataset.page);
        if (pageType === 'products') { S.productsPage.page = newPage; this.loadProductsPage(); }
        else if (pageType === 'customers') { S.customersPage.page = newPage; this.loadCustomersPage(); }
        else if (pageType === 'suppliers') { S.suppliersPage.page = newPage; this.loadSuppliersPage(); }
        else if (pageType === 'invoices') { S.invoices.page = newPage; this.clearInvoicesSelection(); this.loadInvoicesPage(); }
        else if (pageType === 'audit') { S.audit.page = newPage; this.loadAuditPage(); }
      });
    });
  },

  /* ─── TOAST / CONFIRM ─── */
  toast(msg, type = 'success') {
    const c = document.getElementById('toastContainer');
    const t = document.createElement('div');
    t.className = `toast toast-${type}`;
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; t.style.transform = 'translateX(-100%)'; setTimeout(() => t.remove(), 300); }, 2500);
  },

  confirm(title, msg) {
    return new Promise(res => {
      const m = document.getElementById('confirmModal');
      document.getElementById('confirmTitle').textContent = title;
      document.getElementById('confirmMsg').textContent = msg;
      m.classList.add('active');
      const yes = document.getElementById('confirmYes');
      const no = document.getElementById('confirmNo');
      const cleanup = () => { m.classList.remove('active'); yes.onclick = null; no.onclick = null; };
      yes.onclick = () => { cleanup(); res(true); };
      no.onclick = () => { cleanup(); res(false); };
    });
  },

  closeModal(id) { document.getElementById(id).classList.remove('active'); },

  /* ─── SETTINGS ─── */
  renderSettings() {
    const s = S.settings;
    document.getElementById('setStoreName').value = s.store_name || '';
    document.getElementById('setTagline').value = s.tagline || '';
    document.getElementById('setSlogan').value = s.slogan || '';
    document.getElementById('setBranch').value = s.branch || '';
    document.getElementById('setPhone').value = s.phone || '';
    document.getElementById('setAddress').value = s.address || '';
    document.getElementById('setCurrency').value = s.currency || 'ج.م';
    document.getElementById('setTaxRate').value = s.tax_rate || 0;
    document.getElementById('setVatEnabled').checked = !!s.vat_enabled;
    document.getElementById('setCopies').value = s.copies || 1;
    document.getElementById('setFooter').value = s.footer || '';
    document.getElementById('setQuickQty').value = s.quick_qty || '1,5,10,20,30,50,100';
    document.getElementById('setPrinterType').value = s.printer_type || 'browser';
    document.getElementById('setInvoiceFormat').value = s.invoice_format || 'a4';
    document.getElementById('setAutoPrint').checked = !!s.auto_print_after_sale;
    document.getElementById('setCustomLines').value = s.custom_lines || '';
    document.getElementById('setHeaderNote').value = s.header_note || '';
    document.getElementById('setWarrantyText').value = s.warranty_text || '';
    document.getElementById('setTermsConditions').value = s.terms_conditions || '';
    document.getElementById('setMaxItemsPerPage').value = s.max_items_per_page || 15;
    document.getElementById('logoPreview').innerHTML = s.logo ? `<img src="${s.logo}">` : '';
    if (S.user.role === 'admin') this.loadBackupsList();
  },

  previewLogo(input) {
    const f = input.files[0]; if (!f) return;
    const r = new FileReader();
    r.onload = e => {
      document.getElementById('logoPreview').innerHTML = `<img src="${e.target.result}">`;
      S.settings.logo = e.target.result;
    };
    r.readAsDataURL(f);
  },

  async saveSettings() {
    try {
      const payload = {
        store_name: document.getElementById('setStoreName').value.trim(),
        tagline: document.getElementById('setTagline').value.trim(),
        slogan: document.getElementById('setSlogan').value.trim(),
        branch: document.getElementById('setBranch').value.trim(),
        phone: document.getElementById('setPhone').value.trim(),
        address: document.getElementById('setAddress').value.trim(),
        currency: document.getElementById('setCurrency').value.trim() || 'ج.م',
        tax_rate: parseFloat(document.getElementById('setTaxRate').value) || 0,
        vat_enabled: document.getElementById('setVatEnabled').checked,
        copies: parseInt(document.getElementById('setCopies').value) || 1,
        footer: document.getElementById('setFooter').value.trim(),
        quick_qty: document.getElementById('setQuickQty').value.trim() || '1,5,10,20,30,50,100',
        printer_type: document.getElementById('setPrinterType').value,
        invoice_format: document.getElementById('setInvoiceFormat').value,
        auto_print_after_sale: document.getElementById('setAutoPrint').checked,
        custom_lines: document.getElementById('setCustomLines').value,
        header_note: document.getElementById('setHeaderNote').value.trim(),
        warranty_text: document.getElementById('setWarrantyText').value.trim(),
        terms_conditions: document.getElementById('setTermsConditions').value.trim(),
        max_items_per_page: parseInt(document.getElementById('setMaxItemsPerPage').value) || 15,
        logo: S.settings.logo || '',
      };
      await API.post('/api/settings', payload);
      await this.loadSettings();
      document.getElementById('storeName').textContent = S.settings.store_name || 'POS';
      this.renderQuickQty();
      this.recalcCart();
      this.toast('تم حفظ الإعدادات');
    } catch (e) { this.toast(e.message, 'error'); }
  },

  async loadBackupsList() {
    try {
      const list = await API.get('/api/backup/list');
      const el = document.getElementById('backupsList');
      if (!list.length) { el.innerHTML = '<div style="color:var(--g500);font-size:12px;margin-top:8px">لا توجد نسخ احتياطية</div>'; return; }
      el.innerHTML = list.map(b => `
        <div class="backup-item">
          <div>
            <strong>${Util.esc(b.name)}</strong><br>
            <small style="color:var(--g500)">${Util.shortDate(b.created_at)} • ${(b.size / 1024).toFixed(1)} KB</small>
          </div>
          <div class="backup-item-actions">
            <a class="btn btn-sm" href="/api/backup/download/${encodeURIComponent(b.name)}" download>تنزيل</a>
            <button class="btn btn-sm btn-warning" data-restore="${b.name}">استعادة</button>
          </div>
        </div>
      `).join('');
      el.querySelectorAll('[data-restore]').forEach(b => b.addEventListener('click', () => this.restoreBackup(b.dataset.restore)));
    } catch (e) { /* ignore */ }
  },

  async backup() {
    if (S.user.role !== 'admin') { this.toast('صلاحية المدير مطلوبة', 'error'); return; }
    try {
      await API.post('/api/backup', {});
      this.toast('تم إنشاء نسخة احتياطية');
      await this.loadBackupsList();
    } catch (e) { this.toast(e.message, 'error'); }
  },

  async restoreBackup(name) {
    if (!await this.confirm('استعادة نسخة احتياطية', `سيتم استبدال كل البيانات الحالية بـ "${name}". هل أنت متأكد؟`)) return;
    try {
      await API.post('/api/backup/restore', { name });
      this.toast('تمت الاستعادة. سيتم تحديث البيانات.', 'success');
      setTimeout(() => location.reload(), 1500);
    } catch (e) { this.toast(e.message, 'error'); }
  },


};
