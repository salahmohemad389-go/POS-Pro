/* Cross-cutting UX overrides composed last by static/app.js. */
import { S } from './core/state.js';
import { API } from './core/api.js';
import { Util } from './core/util.js';
import { invoiceMethods } from './pages/invoices.js';
import { customerMethods } from './pages/customers.js';

const svg = name => `<svg class="ui-icon" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
const has = permission => !!(S.user?.permissions || []).includes(permission);

function normalizedShortcutFromEvent(e) {
  const mods = [];
  if (e.ctrlKey) mods.push('Ctrl');
  if (e.altKey) mods.push('Alt');
  if (e.shiftKey) mods.push('Shift');
  let key = e.key;
  if (!key) return '';
  if (key.length === 1) key = key.toUpperCase(); else key = key.toUpperCase();
  if (['CONTROL', 'ALT', 'SHIFT', 'META'].includes(key)) return '';
  if (!/^(F([1-9]|1[0-2])|[A-Z0-9])$/.test(key)) return '';
  return [...mods, key].join('+');
}

function shortcutMap() {
  const s = S.settings || {};
  return {
    new_sale: s.shortcut_new_sale || '', search: s.shortcut_search || '', return: s.shortcut_return || '',
    cash: s.shortcut_cash || '', credit: s.shortcut_credit || '', partial: s.shortcut_partial || '',
    clear_cart: s.shortcut_clear_cart || '', sidebar: s.shortcut_sidebar || '', invoices: s.shortcut_invoices || '',
  };
}

export const upgradeMethods = {
  applyBranding() {
    const s = S.settings || {};
    const name = String(s.store_name || 'POS').trim() || 'POS';
    const tagline = String(s.tagline || '').trim();
    document.title = name;
    [['storeName', name], ['loginStoreName', name], ['loginTagline', tagline], ['sidebarTagline', tagline]].forEach(([id, value]) => {
      const el = document.getElementById(id); if (!el) return; el.textContent = value; el.style.display = value ? '' : 'none';
    });
    const color = (value, fallback) => /^#[0-9a-fA-F]{6}$/.test(String(value || '')) ? String(value) : fallback;
    document.documentElement.style.setProperty('--p', color(s.primary_color, '#2563eb'));
    document.documentElement.style.setProperty('--info', color(s.accent_color, '#0891b2'));
    document.documentElement.style.setProperty('--brand-primary', color(s.primary_color, '#2563eb'));
    document.documentElement.style.setProperty('--brand-accent', color(s.accent_color, '#0891b2'));
    this.installUIEnhancements();
  },

  applyPermissions() {
    const perms = new Set(S.user?.permissions || []);
    const can = p => perms.has(p);
    const featureReports = S.settings?.feature_reports_enabled !== false;
    const featureSuppliers = S.settings?.feature_suppliers_enabled !== false;
    const featureInvoices = S.settings?.feature_invoices_enabled !== false;
    const featureCustomers = S.settings?.feature_customers_enabled !== false;
    const navPerms = {
      pos: can('pos_view'),
      products: can('product_view'),
      customers: featureCustomers && can('customer_view'),
      invoices: featureInvoices && (can('invoice_view') || can('invoice_view_own')),
      suppliers: featureSuppliers && can('supplier_view'),
      reports: featureReports && (can('report_dashboard') || can('report_low_stock') || can('report_profit') || can('report_customer_debts')),
      users: can('user_view'),
      settings: can('settings_save'),
      audit: can('audit_view'),
    };
    Object.entries(navPerms).forEach(([page, visible]) => {
      const el = document.querySelector(`.nav-item[data-page="${page}"]`); if (el) el.classList.toggle('show', !!visible);
    });
    document.querySelectorAll('.admin-only').forEach(el => { el.style.display = S.user?.is_owner ? '' : 'none'; });
    document.querySelectorAll('.owner-only').forEach(el => { el.style.display = S.user?.is_owner ? '' : 'none'; });
    const backup = document.getElementById('backupBtn'); if (backup) backup.style.display = can('backup_create') ? '' : 'none';
    const addUser = document.getElementById('addUserBtn'); if (addUser) addUser.style.display = can('user_save') ? '' : 'none';
    const createBackup = document.getElementById('createBackupBtn'); if (createBackup) createBackup.style.display = can('backup_create') ? '' : 'none';
    const clearAudit = document.getElementById('clearAuditBtn'); if (clearAudit) clearAudit.style.display = can('audit_clear') ? '' : 'none';
    const returnBtn = document.getElementById('posReturnBtn'); if (returnBtn) returnBtn.style.display = can('invoice_edit') ? '' : 'none';
    if (!navPerms[S.currentPage]) S.currentPage = Object.entries(navPerms).find(([, visible]) => visible)?.[0] || 'pos';
  },

  installUIEnhancements() {
    if (!document.body.dataset.posUpgradeBound) {
      document.body.dataset.posUpgradeBound = '1';
      const collapse = document.getElementById('sidebarCollapseBtn');
      if (localStorage.getItem('pos_sidebar_collapsed') === '1') document.body.classList.add('sidebar-collapsed');
      collapse?.addEventListener('click', () => this.toggleSidebarCollapsed());

      const eye = document.getElementById('toggleLoginPass');
      eye?.addEventListener('click', e => {
        e.preventDefault(); e.stopImmediatePropagation();
        const input = document.getElementById('loginPass'); if (!input) return;
        const show = input.type === 'password'; input.type = show ? 'text' : 'password';
        eye.innerHTML = svg(show ? 'eye-off' : 'eye'); eye.setAttribute('aria-label', show ? 'إخفاء كلمة المرور' : 'إظهار كلمة المرور');
      }, true);

      document.addEventListener('keydown', e => {
        if (e.defaultPrevented || e.metaKey) return;
        if (e.target?.classList?.contains('shortcut-input')) return;
        if (document.querySelector('.modal.active')) return;
        const shortcut = normalizedShortcutFromEvent(e); if (!shortcut) return;
        const matches = Object.entries(shortcutMap()).find(([, value]) => value && value.toLowerCase() === shortcut.toLowerCase());
        if (!matches) return;
        e.preventDefault();
        const action = matches[0];
        if (action === 'sidebar') return this.toggleSidebarCollapsed();
        if (action === 'new_sale') { this.nav('pos'); this.setInvoiceType('sale'); document.getElementById('posSearch')?.focus(); return; }
        if (action === 'search') { this.nav('pos'); setTimeout(() => document.getElementById('posSearch')?.focus(), 0); return; }
        if (action === 'return') return this.openReturnFromPOS();
        if (action === 'invoices') { const nav = document.querySelector('.nav-item[data-page="invoices"].show'); if (nav) this.nav('invoices'); else this.toast('قسم الفواتير مخفي أو غير مسموح لك', 'warning'); return; }
        this.nav('pos');
        if (action === 'cash') document.querySelector('.cart-actions [data-method="cash"]')?.click();
        else if (action === 'credit') document.querySelector('.cart-actions [data-method="credit"]')?.click();
        else if (action === 'partial') document.getElementById('partialBtn')?.click();
        else if (action === 'clear_cart') document.getElementById('clearCartBtn')?.click();
      });
    }
    this.ensureReturnPickerModal();
  },

  toggleSidebarCollapsed() {
    const collapsed = document.body.classList.toggle('sidebar-collapsed');
    localStorage.setItem('pos_sidebar_collapsed', collapsed ? '1' : '0');
  },

  ensureReturnPickerModal() {
    if (document.getElementById('returnPickerModal')) return;
    const modal = document.createElement('div'); modal.className = 'modal'; modal.id = 'returnPickerModal';
    modal.innerHTML = `<div class="modal-content modal-lg"><div class="modal-header"><h3>${svg('return')} اختيار الفاتورة الأصلية للمرتجع</h3><button class="modal-close" data-close="returnPickerModal">×</button></div><div class="modal-body"><div class="return-picker-search"><input type="text" id="returnPickerSearch" class="search-input" placeholder="ابحث برقم الفاتورة أو اسم العميل..."></div><div class="table-container"><table><thead><tr><th>رقم الفاتورة</th><th>العميل</th><th>الإجمالي</th><th>التاريخ</th><th></th></tr></thead><tbody id="returnPickerRows"></tbody></table></div></div><div class="modal-footer"><button class="btn btn-secondary" data-close="returnPickerModal">إغلاق</button></div></div>`;
    document.body.appendChild(modal);
    const input = document.getElementById('returnPickerSearch');
    let timer = null;
    input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => this.loadReturnPicker(input.value.trim()), 220); });
  },

  async openReturnFromPOS() {
    if (!has('invoice_edit')) { this.toast('لا تملك صلاحية تنفيذ المرتجعات', 'error'); return; }
    this.ensureReturnPickerModal();
    document.getElementById('returnPickerModal').classList.add('active');
    const input = document.getElementById('returnPickerSearch'); input.value = '';
    await this.loadReturnPicker('');
    setTimeout(() => input.focus(), 40);
  },

  async loadReturnPicker(query = '') {
    const tbody = document.getElementById('returnPickerRows'); if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="5" class="return-picker-loading">جاري تحميل الفواتير...</td></tr>';
    try {
      const params = new URLSearchParams({ page: '1', limit: '50', filter: 'all' }); if (query) params.set('q', query);
      const data = await API.get(`/api/invoices?${params}`, { dedupe: false });
      const rows = (data.items || []).filter(inv => inv.type === 'sale' && inv.customer_id);
      if (!rows.length) { tbody.innerHTML = '<tr><td colspan="5" class="return-picker-loading">لا توجد فواتير بيع مرتبطة بعملاء</td></tr>'; return; }
      tbody.innerHTML = rows.map(inv => `<tr><td><strong>${Util.esc(inv.invoice_number || ('#' + inv.number))}</strong></td><td>${Util.esc(inv.customer_name || '-')}</td><td>${Util.money(inv.total)}</td><td>${Util.date(inv.created_at)}</td><td><button class="btn btn-sm btn-warning return-pick-btn" data-return-id="${inv.id}">${svg('return')}<span>مرتجع</span></button></td></tr>`).join('');
      tbody.querySelectorAll('[data-return-id]').forEach(btn => btn.addEventListener('click', async () => {
        const id = parseInt(btn.dataset.returnId); S._printingId = id; this.closeModal('returnPickerModal'); await this.openReturnInvoice();
      }));
    } catch (e) { tbody.innerHTML = `<tr><td colspan="5" class="return-picker-loading">${Util.esc(e.message || 'فشل تحميل الفواتير')}</td></tr>`; }
  },

  renderQuickQty() {
    const wrap = document.querySelector('#page-pos .quick-qty'); if (!wrap) return;
    const enabled = S.settings?.quick_qty_enabled !== false; wrap.style.display = enabled ? '' : 'none'; if (!enabled) return;
    const list = (S.settings.quick_qty || '1,5,10,20,30,50,100').split(',').map(s => s.trim()).filter(Boolean);
    const host = document.getElementById('quickQtyBtns'); if (!host) return;
    host.innerHTML = list.map(q => `<button class="quick-qty-btn" data-qty="${Util.esc(q)}">${Util.esc(q)}</button>`).join('');
    host.querySelectorAll('.quick-qty-btn').forEach(b => b.addEventListener('click', () => this.setQtyToActive(parseFloat(b.dataset.qty))));
  },

  renderPOSProducts(data) {
    const el = document.getElementById('posProducts'); const items = data.items || [];
    if (!items.length) {
      const canAdd = !!(S.user && (S.user.permissions || []).includes('product_save')); const q = (S.pos.q || '').trim();
      el.innerHTML = `<div class="empty-cart">لا توجد منتجات${q ? ` مطابقة لـ «${Util.esc(q)}»` : ''}</div>` + (canAdd && q ? `<button class="btn btn-primary pos-quick-add-empty" type="button">+ إضافة المنتج الآن</button>` : '');
      const quick = el.querySelector('.pos-quick-add-empty'); if (quick) quick.addEventListener('click', () => this.openQuickAdd(q)); return;
    }
    el.innerHTML = items.map(p => { const stock = parseFloat(p.stock) || 0; const barcode = p.barcode ? `<span class="pr-barcode">${Util.esc(p.barcode)}</span>` : ''; return `<div class="product-row ${stock <= 0 ? 'dimmed' : ''}" data-id="${p.id}" role="button" tabindex="${stock > 0 ? '0' : '-1'}" aria-label="إضافة ${Util.esc(p.name)} للسلة"><div><div class="pr-name">${Util.esc(p.name)}</div>${barcode}</div><div class="pr-stock">${Util.r3(stock)}</div><div class="pr-price">${Util.money(p.price)}</div></div>`; }).join('');
    el.querySelectorAll('.product-row').forEach(row => { const add = () => { if (row.classList.contains('dimmed')) { this.toast('المنتج غير متوفر في المخزون', 'warning'); return; } this.addToCart(parseInt(row.dataset.id)); }; row.addEventListener('click', add); row.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); add(); } }); });
  },

  setQtyToActive(qty) {
    if (!S.cart.length) return; const last = S.cart[S.cart.length - 1]; const q = Util.r3(qty); if (q <= 0) return; const product = S.productCache.get(last.product_id); const stock = product ? (parseFloat(product.stock) || 0) : Infinity; let finalQty = q;
    if (S.invoiceType === 'sale' && q > stock + 0.0000001) { if (stock <= 0) { this.toast('المنتج غير متوفر في المخزون', 'warning'); return; } finalQty = Util.r3(stock); this.toast(`المتاح فقط ${finalQty} وتم ضبط الكمية عليه`, 'warning'); }
    last.quantity = finalQty; last.total = Util.r2(last.quantity * last.unit_price); this.renderCart();
  },

  setCartQty(idx, val) {
    const it = S.cart[idx]; if (!it) return; let q = parseFloat(val); if (isNaN(q)) q = 0; q = Util.r3(q); if (q <= 0) { S.cart.splice(idx, 1); this.renderCart(); return; }
    const product = S.productCache.get(it.product_id); const stock = product ? (parseFloat(product.stock) || 0) : Infinity;
    if (S.invoiceType === 'sale' && q > stock + 0.0001) { if (stock <= 0) { this.toast('المنتج غير متوفر في المخزون', 'warning'); this.renderCart(); return; } q = Util.r3(stock); this.toast(`المتاح فقط ${q} وتم ضبط الكمية عليه`, 'warning'); }
    it.quantity = Util.r3(q); it.total = Util.r2(it.quantity * it.unit_price); this.renderCart();
  },

  async viewCustomer(id) {
    await customerMethods.viewCustomer.call(this, id);
    if (!has('invoice_edit')) return;
    document.querySelectorAll('#cdInvoicesTable tr').forEach(row => {
      const checkbox = row.querySelector('[data-sel-inv]'); if (!checkbox) return;
      const invoiceId = parseInt(checkbox.dataset.selInv); const inv = S._customerInvoiceMap?.get(invoiceId);
      if (!inv || inv.type !== 'sale' || !inv.customer_id || row.querySelector('[data-direct-return]')) return;
      const cell = row.lastElementChild; if (!cell) return;
      const btn = document.createElement('button'); btn.className = 'btn btn-sm btn-warning'; btn.dataset.directReturn = String(invoiceId); btn.innerHTML = `${svg('return')}<span>مرتجع</span>`;
      btn.addEventListener('click', async () => { S._printingId = invoiceId; await this.openReturnInvoice(); }); cell.appendChild(btn);
    });
  },

  renderInvoicesTable(data) {
    invoiceMethods.renderInvoicesTable.call(this, data);
    document.querySelectorAll('#invoicesTable [data-print-inv]').forEach(btn => { btn.innerHTML = svg('file'); btn.title = 'طباعة / PDF'; });
  },

  async previewAndMaybePrintInvoicePdf(invoiceId, autoPrint) {
    try {
      const resp = await fetch(`/api/invoices/${invoiceId}/pdf`, { credentials: 'same-origin' }); if (!resp.ok) { const err = await resp.json().catch(() => ({})); throw new Error(err.detail || `HTTP ${resp.status}`); }
      const blob = await resp.blob(); const cd = resp.headers.get('Content-Disposition') || ''; const m = cd.match(/filename="?([^";]+)"?/); const filename = m ? m[1] : `invoice_${invoiceId}.pdf`;
      if (S._pdfPreviewUrl) URL.revokeObjectURL(S._pdfPreviewUrl); const url = URL.createObjectURL(blob); S._pdfPreviewUrl = url; const frame = document.getElementById('pdfPreviewFrame'); const download = document.getElementById('pdfPreviewDownload'); frame.src = url; download.href = url; download.download = filename; document.getElementById('pdfPreviewModal').classList.add('active');
      if (autoPrint) frame.onload = () => { frame.onload = null; try { frame.contentWindow?.focus(); frame.contentWindow?.print(); } catch { this.toast('تعذر فتح نافذة الطباعة، لكن ملف PDF ظاهر ويمكن تنزيله', 'warning'); } };
    } catch (e) { this.toast(e.message || 'تعذّر فتح معاينة الفاتورة', 'error'); }
  },
  printPdfPreview() { const frame = document.getElementById('pdfPreviewFrame'); if (!frame?.src) { this.toast('لا توجد فاتورة مفتوحة للطباعة', 'warning'); return; } try { frame.contentWindow?.focus(); frame.contentWindow?.print(); } catch { this.toast('الطباعة غير متاحة حالياً؛ يمكنك تنزيل PDF مباشرة', 'warning'); } },
  async openInvoice(id) { await invoiceMethods.openInvoice.call(this, id); },
};
