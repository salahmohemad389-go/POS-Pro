/* Cross-cutting frontend overrides composed last by static/app.js. */
import { S } from './core/state.js';
import { Util } from './core/util.js';
import { invoiceMethods } from './pages/invoices.js';

function ui() {
  return { feature_products_enabled:true, feature_customers_enabled:true, feature_invoices_enabled:true, feature_suppliers_enabled:true, feature_reports_enabled:true, feature_audit_enabled:true, quick_qty_enabled:true, ...(S.settings?.ui_config || {}) };
}

export const upgradeMethods = {
  applyPermissions() {
    const perms = new Set(S.user?.permissions || []); const can = p => perms.has(p); const cfg = ui();
    const navPerms = {
      pos: can('pos_view'),
      products: cfg.feature_products_enabled !== false && can('product_view'),
      customers: cfg.feature_customers_enabled !== false && can('customer_view'),
      invoices: cfg.feature_invoices_enabled !== false && (can('invoice_view') || can('invoice_view_own')),
      suppliers: cfg.feature_suppliers_enabled !== false && can('supplier_view'),
      reports: cfg.feature_reports_enabled !== false && (can('report_dashboard') || can('report_low_stock') || can('report_profit') || can('report_customer_debts')),
      users: can('user_view'),
      settings: can('settings_save'),
      audit: cfg.feature_audit_enabled !== false && can('audit_view'),
    };
    Object.entries(navPerms).forEach(([page, visible]) => { const el = document.querySelector(`.nav-item[data-page="${page}"]`); if (el) el.classList.toggle('show', !!visible); });
    document.querySelectorAll('.admin-only,.owner-only').forEach(el => { el.style.display = S.user?.is_owner ? '' : 'none'; });
    const backup = document.getElementById('backupBtn'); if (backup) backup.style.display = can('backup_create') ? '' : 'none';
    const addUser = document.getElementById('addUserBtn'); if (addUser) addUser.style.display = can('user_save') ? '' : 'none';
    const createBackup = document.getElementById('createBackupBtn'); if (createBackup) createBackup.style.display = can('backup_create') ? '' : 'none';
    const clearAudit = document.getElementById('clearAuditBtn'); if (clearAudit) clearAudit.style.display = can('audit_clear') ? '' : 'none';
    document.querySelector('.quick-qty')?.classList.toggle('feature-hidden', cfg.quick_qty_enabled === false);
    if (!navPerms[S.currentPage]) { const next = Object.entries(navPerms).find(([,v]) => v)?.[0]; if (next) S.currentPage = next; }
  },
  renderQuickQty() {
    const wrap = document.querySelector('.quick-qty'); const cfg = ui();
    if (wrap) wrap.classList.toggle('feature-hidden', cfg.quick_qty_enabled === false);
    const target = document.getElementById('quickQtyBtns'); if (!target) return;
    if (cfg.quick_qty_enabled === false) { target.innerHTML = ''; return; }
    const list = (S.settings?.quick_qty || '1,5,10,20,30,50,100').split(',').map(s => s.trim()).filter(Boolean);
    target.innerHTML = list.map(q => `<button class="quick-qty-btn" data-qty="${Util.esc(q)}">${Util.esc(q)}</button>`).join('');
    target.querySelectorAll('.quick-qty-btn').forEach(b => b.addEventListener('click', () => this.setQtyToActive(parseFloat(b.dataset.qty))));
  },
  renderPOSProducts(data) {
    const el = document.getElementById('posProducts'); const items = data.items || [];
    if (!items.length) {
      const canAdd = !!(S.user && (S.user.permissions || []).includes('product_save')); const q = (S.pos.q || '').trim();
      el.innerHTML = `<div class="empty-cart">لا توجد منتجات${q ? ` مطابقة لـ «${Util.esc(q)}»` : ''}</div>` + (canAdd && q ? `<button class="btn btn-primary pos-quick-add-empty" type="button">إضافة المنتج الآن</button>` : '');
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
  openReturnFromPOS() {
    const invoiceNav = document.querySelector('.nav-item[data-page="invoices"]');
    if (!invoiceNav?.classList.contains('show')) { this.toast('قسم الفواتير مخفي من الإعدادات أو غير مسموح لهذا المستخدم', 'warning'); return; }
    this.nav('invoices'); this.toast('اختر الفاتورة الأصلية واضغط «مرتجع» لبدء المرتجع', 'info'); const search = document.getElementById('invoicesSearch'); if (search) setTimeout(() => search.focus(), 80);
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
  async openInvoice(id) { await invoiceMethods.openInvoice.call(this, id); if (S.currentInvoice?.payment_method === 'mixed') { const body = document.getElementById('invoiceModalBody'); const cells = body ? Array.from(body.querySelectorAll('div')) : []; const payment = cells.find(el => el.textContent?.includes('طريقة الدفع:')); if (payment) payment.innerHTML = '<strong>طريقة الدفع:</strong> مختلط'; } },
};
