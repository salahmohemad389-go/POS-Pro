import { S } from '../core/state.js';
import { API } from '../core/api.js';
import { Util } from '../core/util.js';

export const invoiceMethods = {
  async loadInvoicesPage() {
    try {
      const params = new URLSearchParams({ page: S.invoices.page, limit: S.invoices.limit, filter: S.invoices.filter });
      if (S.invoices.q) params.set('q', S.invoices.q);
      const data = await API.get(`/api/invoices?${params}`);
      this.renderInvoicesTable(data);
      this.renderPagination('invoicesPagination', data, 'invoices');
    } catch (e) { this.toast(e.message, 'error'); }
  },

  renderInvoicesTable(data) {
    const tbody = document.getElementById('invoicesTable');
    if (!data.items.length) { tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--g400);padding:30px">لا توجد فواتير</td></tr>'; this.updateInvoicesCombinedBar(); return; }
    tbody.innerHTML = data.items.map(inv => `
      <tr>
        <td><input type="checkbox" data-sel-inv="${inv.id}" ${S.invoices.selected.has(inv.id) ? 'checked' : ''}></td>
        <td>${inv.number}</td>
        <td>${Util.esc(inv.customer_name || '-')}</td>
        <td><span class="badge ${Util.invBadgeClass(inv.type)}">${Util.invLabel(inv.type)}</span></td>
        <td><strong>${Util.money(inv.total)}</strong></td>
        <td><span class="badge ${inv.status === 'paid' ? 'badge-success' : inv.status === 'partial' ? 'badge-warning' : 'badge-danger'}">${inv.status === 'paid' ? 'مدفوعة' : inv.status === 'partial' ? 'جزئي' : 'آجل'}</span></td>
        <td>${Util.date(inv.created_at)}</td>
        <td>
          <button class="btn btn-sm btn-secondary" data-view-inv="${inv.id}">عرض</button>
          <button class="btn btn-sm btn-primary" data-print-inv="${inv.id}">🖨️</button>
          <button class="btn btn-sm btn-danger" data-del-inv="${inv.id}">حذف</button>
        </td>
      </tr>
    `).join('');
    tbody.querySelectorAll('[data-view-inv]').forEach(b => b.addEventListener('click', () => this.viewInvoice(parseInt(b.dataset.viewInv))));
    tbody.querySelectorAll('[data-print-inv]').forEach(b => b.addEventListener('click', () => this.printInvoiceById(parseInt(b.dataset.printInv))));
    tbody.querySelectorAll('[data-del-inv]').forEach(b => b.addEventListener('click', () => this.deleteInvoice(parseInt(b.dataset.delInv))));
    tbody.querySelectorAll('[data-sel-inv]').forEach(cb => cb.addEventListener('change', e => {
      const id = parseInt(e.target.dataset.selInv);
      if (e.target.checked) S.invoices.selected.add(id); else S.invoices.selected.delete(id);
      this.updateInvoicesCombinedBar();
    }));
    document.getElementById('invoicesSelectAll').checked = data.items.length > 0 && data.items.every(inv => S.invoices.selected.has(inv.id));
    this.updateInvoicesCombinedBar();
  },

  updateInvoicesCombinedBar() {
    const n = S.invoices.selected.size;
    const bar = document.getElementById('invoicesCombinedBar');
    bar.style.display = n > 0 ? 'flex' : 'none';
    document.getElementById('invoicesSelCount').textContent = n > 0 ? `تم تحديد ${n} فاتورة` : '';
  },

  toggleSelectAllInvoices(checked) {
    document.querySelectorAll('#invoicesTable [data-sel-inv]').forEach(cb => {
      cb.checked = checked;
      const id = parseInt(cb.dataset.selInv);
      if (checked) S.invoices.selected.add(id); else S.invoices.selected.delete(id);
    });
    this.updateInvoicesCombinedBar();
  },

  clearInvoicesSelection() {
    S.invoices.selected.clear();
    document.querySelectorAll('#invoicesTable [data-sel-inv]').forEach(cb => { cb.checked = false; });
    document.getElementById('invoicesSelectAll').checked = false;
    this.updateInvoicesCombinedBar();
  },

  // Fetch a combined (merged) PDF for multiple invoice IDs and download it.
  async downloadCombinedInvoicePDF(ids) {
    if (!ids || !ids.length) { this.toast('حدد فاتورتين على الأقل للدمج', 'warning'); return; }
    if (ids.length < 2) { this.toast('حدد فاتورتين على الأقل للدمج', 'warning'); return; }
    try {
      const resp = await fetch(`/api/combined-invoice/pdf?ids=${ids.join(',')}`, { credentials: 'same-origin' });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }
      const blob = await resp.blob();
      const cd = resp.headers.get('Content-Disposition') || '';
      const m = cd.match(/filename="?([^";]+)"?/);
      const filename = m ? m[1] : 'combined_invoice.pdf';
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      this.toast(`تم إنشاء فاتورة مجمعة من ${ids.length} فاتورة`);
    } catch (e) {
      this.toast(e.message || 'فشل إنشاء الفاتورة المجمعة', 'error');
    }
  },

  // ─── Combined invoice: options modal + create/save/preview/print flow ───
  openCombinedInvoiceOptions(ids) {
    if (!ids || ids.length < 2) { this.toast('حدد فاتورتين على الأقل للدمج', 'warning'); return; }
    S._combineIds = Array.from(new Set(ids));
    const selectedNumbers = [];
    ['#invoicesTable tr', '#cdInvoicesTable tr'].forEach(selector => {
      document.querySelectorAll(selector).forEach(row => {
        const cb = row.querySelector('[data-sel-inv]');
        if (cb && S._combineIds.includes(parseInt(cb.dataset.selInv))) {
          const no = row.children[1]?.textContent?.trim();
          if (no && !selectedNumbers.includes(`#${no}`)) selectedNumbers.push(`#${no}`);
        }
      });
    });
    document.getElementById('combinedInvoiceCount').textContent =
      `سيتم دمج ${S._combineIds.length} فاتورة فقط` + (selectedNumbers.length ? `: ${selectedNumbers.join('، ')}` : '');
    document.getElementById('opt_deduct_returns').checked = true;
    document.getElementById('opt_show_paid_remaining').checked = true;
    document.getElementById('opt_save_to_customer').checked = true;
    document.getElementById('opt_auto_print').checked = false;
    document.getElementById('combinedInvoiceOptionsModal').classList.add('active');
  },

  async executeCombinedInvoice() {
    const ids = S._combineIds || [];
    if (ids.length < 2) { this.toast('حدد فاتورتين على الأقل للدمج', 'warning'); return; }
    const options = {
      deduct_returns: document.getElementById('opt_deduct_returns').checked,
      show_paid_remaining: document.getElementById('opt_show_paid_remaining').checked,
      save_to_customer: document.getElementById('opt_save_to_customer').checked,
    };
    const autoPrint = document.getElementById('opt_auto_print').checked;
    try {
      const res = await API.post('/api/combined-invoice', { ids, options });
      const inv = res.invoice;
      this.closeModal('combinedInvoiceOptionsModal');
      this.toast(`تم إنشاء الفاتورة المجمعة ${inv.invoice_number} وحفظها`);
      // Refresh whichever list is currently visible so the new invoice shows up
      if (S._currentCustomerId) this.viewCustomer(S._currentCustomerId);
      if (document.getElementById('page-invoices').classList.contains('active')) this.loadInvoicesPage();
      this.clearInvoicesSelection();
      S.selectedInvoices = new Set();
      await this.previewAndMaybePrintInvoicePdf(inv.id, autoPrint);
    } catch (e) {
      this.toast(e.message || 'فشل إنشاء الفاتورة المجمعة', 'error');
    }
  },

  // Fetch an invoice's PDF (works for normal AND combined invoices - the
  // backend regenerates combined ones fresh from their source invoices every
  // time) and open it for preview, optionally triggering print immediately.
  async previewAndMaybePrintInvoicePdf(invoiceId, autoPrint) {
    try {
      const resp = await fetch(`/api/invoices/${invoiceId}/pdf`, { credentials: 'same-origin' });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      if (autoPrint) {
        const iframe = document.createElement('iframe');
        iframe.style.display = 'none';
        iframe.src = url;
        document.body.appendChild(iframe);
        iframe.onload = () => {
          try { iframe.contentWindow.focus(); iframe.contentWindow.print(); } catch (e) {}
        };
      } else {
        window.open(url, '_blank');
        setTimeout(() => URL.revokeObjectURL(url), 60000);
      }
    } catch (e) {
      this.toast(e.message || 'تعذّر فتح معاينة الفاتورة', 'error');
    }
  },

  // ─── Customer account statement (كشف حساب العميل) ───
  async openCustomerStatement(customerId) {
    if (!customerId) { this.toast('افتح صفحة عميل أولاً', 'warning'); return; }
    try {
      const data = await API.get(`/api/customers/${customerId}/statement`);
      S._statementData = data;
      document.getElementById('stmtCustomerName').textContent = data.customer.name + (data.truncated ? ' — عرض أحدث الحركات فقط' : '');
      if (data.truncated) this.toast(`الملخص يشمل كامل التاريخ، والجدول يعرض أحدث الحركات فقط`, 'warning');
      document.getElementById('stmtTotalSales').textContent = Util.money(data.summary.total_sales);
      document.getElementById('stmtTotalReturns').textContent = Util.money(data.summary.total_returns);
      document.getElementById('stmtNetSales').textContent = Util.money(data.summary.net_sales);
      document.getElementById('stmtTotalPaid').textContent = Util.money(data.summary.total_paid);
      document.getElementById('stmtTotalRemaining').textContent = Util.money(data.summary.total_remaining);
      const tbody = document.getElementById('stmtTable');
      if (!data.events.length) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--g400);padding:30px">لا توجد حركات</td></tr>';
      } else {
        tbody.innerHTML = data.events.map(ev => `
          <tr>
            <td>${Util.date(ev.date)}</td>
            <td>${Util.esc(ev.description || '-')}</td>
            <td>${Util.esc(ev.invoice_number || '-')}</td>
            <td style="color:var(--ok)">${ev.sale ? Util.money(ev.sale) : '-'}</td>
            <td style="color:var(--err)">${ev.return ? Util.money(ev.return) : '-'}</td>
            <td>${ev.paid ? Util.money(ev.paid) : '-'}</td>
            <td><strong>${Util.money(ev.balance)}</strong></td>
          </tr>
        `).join('');
      }
      document.getElementById('customerStatementModal').classList.add('active');
    } catch (e) {
      this.toast(e.message || 'فشل تحميل كشف الحساب', 'error');
    }
  },

  printCustomerStatement() {
    const data = S._statementData;
    if (!data) return;
    const rows = data.events.map(ev => `
      <tr>
        <td>${Util.date(ev.date)}</td>
        <td>${Util.esc(ev.description || '-')}</td>
        <td>${Util.esc(ev.invoice_number || '-')}</td>
        <td>${ev.sale ? Util.money(ev.sale) : '-'}</td>
        <td>${ev.return ? Util.money(ev.return) : '-'}</td>
        <td>${ev.paid ? Util.money(ev.paid) : '-'}</td>
        <td>${Util.money(ev.balance)}</td>
      </tr>
    `).join('');
    const html = `<!DOCTYPE html><html><head><meta charset="UTF-8"><title>كشف حساب ${Util.esc(data.customer.name)}</title>
      <style>
        body{font-family:Tahoma,Arial,sans-serif;direction:rtl;padding:20px}
        h2{text-align:center}
        table{width:100%;border-collapse:collapse;margin-top:16px}
        th,td{border:1px solid #ccc;padding:6px;text-align:center;font-size:13px}
        th{background:#1e3a5f;color:#fff}
        .summary{display:flex;justify-content:space-around;margin-top:14px;font-weight:700}
      </style></head><body>
      <h2>كشف حساب العميل: ${Util.esc(data.customer.name)}</h2>
      ${data.truncated ? `<p style="text-align:center;color:#a15c00">الملخص يشمل كامل التاريخ، والجدول يعرض أحدث الحركات فقط.</p>` : ''}
      <div class="summary">
        <div>إجمالي المبيعات: ${Util.money(data.summary.total_sales)}</div>
        <div>إجمالي المرتجعات: ${Util.money(data.summary.total_returns)}</div>
        <div>صافي المبيعات: ${Util.money(data.summary.net_sales)}</div>
        <div>إجمالي المدفوع: ${Util.money(data.summary.total_paid)}</div>
        <div>المتبقي: ${Util.money(data.summary.total_remaining)}</div>
      </div>
      <table>
        <thead><tr><th>التاريخ</th><th>البيان</th><th>رقم الفاتورة</th><th>بيع</th><th>مرتجع</th><th>مدفوع</th><th>الرصيد</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </body></html>`;
    const win = window.open('', '_blank', 'width=900,height=1100');
    win.document.write(html);
    win.document.close();
    setTimeout(() => win.print(), 300);
  },

  filterInvoices(f) {
    S.invoices.filter = f;
    S.invoices.page = 1;
    this.clearInvoicesSelection();
    document.querySelectorAll('.filter-tab').forEach(b => b.classList.toggle('active', b.dataset.filter === f));
    this.loadInvoicesPage();
  },

  async viewInvoice(id) {
    try {
      const inv = await API.get(`/api/invoices/${id}`);
      const body = document.getElementById('invoiceModalBody');
      const taxRate = parseFloat(inv.tax_rate) || 0;
      // Auto-fix: if invoice has customer_id but name/phone empty, try to fill from cache
      let custName = inv.customer_name || '';
      let custPhone = inv.customer_phone || '';
      const custMissing = (!custName || custName === 'عميل نقدي' || !custPhone);
      if (inv.customer_id && S.customerCache.has(inv.customer_id)) {
        const c = S.customerCache.get(inv.customer_id);
        if (!custName || custName === 'عميل نقدي') custName = c.name || custName;
        if (!custPhone) custPhone = c.phone || '';
      }
      body.innerHTML = `
        <div style="margin-bottom:12px">
          <div><strong>رقم:</strong> ${inv.number}</div>
          <div><strong>العميل:</strong> ${Util.esc(custName || '-')}</div>
          <div><strong>الهاتف:</strong> ${Util.esc(custPhone || '-')}${custMissing ? ' <small style="color:var(--err);font-weight:700">⚠ ناقص</small>' : ''}</div>
          <div><strong>النوع:</strong> ${Util.invLabel(inv.type)}</div>
          <div><strong>التاريخ:</strong> ${Util.date(inv.created_at)}</div>
          <div><strong>طريقة الدفع:</strong> ${inv.payment_method === 'cash' ? 'نقدي' : inv.payment_method === 'credit' ? 'آجل' : 'جزئي'}</div>
        </div>
        <div class="table-container" style="margin-bottom:12px">
          <table>
            <thead><tr><th>المنتج</th><th>الكمية</th><th>السعر</th><th>الإجمالي</th></tr></thead>
            <tbody>
              ${(inv.items || []).map(it => `
                <tr>
                  <td>${Util.esc(it.product_name)}${it.barcode ? `<br><small style="color:var(--g500);font-family:monospace">${Util.esc(it.barcode)}</small>` : ''}</td>
                  <td>${it.quantity}</td>
                  <td>${Util.money(it.unit_price)}</td>
                  <td><strong>${Util.money(it.total)}</strong></td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
        <div style="text-align:left;background:var(--g50);padding:10px;border-radius:6px">
          <div>المجموع: ${Util.money(inv.subtotal)}</div>
          ${inv.discount > 0 ? `<div>الخصم (${inv.discount_pct || 0}%): ${Util.money(inv.discount)}</div>` : ''}
          ${taxRate > 0 ? `<div>الضريبة (${taxRate}%): ${Util.money(inv.tax)}</div>` : ''}
          <div style="font-size:18px;font-weight:800;color:var(--p);border-top:1px solid var(--g300);padding-top:6px;margin-top:6px">الإجمالي: ${Util.money(inv.total)}</div>
          <div>المدفوع: ${Util.money(inv.paid)}</div>
          ${inv.remaining > 0 ? `<div style="color:var(--err);font-weight:700">المتبقي: ${Util.money(inv.remaining)}</div>` : ''}
        </div>`;
      S._printingId = id;
      // Show/hide collect button based on status
      const collectBtn = document.getElementById('collectInvoiceBtn');
      const effectiveRemaining = parseFloat(inv.effective_remaining ?? inv.remaining) || 0;
      if (effectiveRemaining > 0.001 && inv.type === 'sale') {
        collectBtn.style.display = 'inline-flex';
      } else {
        collectBtn.style.display = 'none';
      }
      const returnBtn = document.getElementById('returnInvoiceBtn');
      returnBtn.style.display = (inv.type === 'sale' && inv.customer_id) ? 'inline-flex' : 'none';
      // Set PDF download link - rebind because href changed dynamically
      const pdfBtn = document.getElementById('pdfInvoiceBtn');
      if (pdfBtn) {
        pdfBtn.href = `/api/invoices/${id}/pdf`;
        pdfBtn.style.display = 'inline-flex';
        // Force re-bind for this dynamically-updated anchor
        delete pdfBtn.dataset.bound;
        pdfBtn.replaceWith(pdfBtn.cloneNode(true));
        this.bindDownloadLinks();
      }
      document.getElementById('invoiceModal').classList.add('active');
    } catch (e) { this.toast(e.message, 'error'); }
  },

  async openReturnInvoice() {
    if (!S._printingId) return;
    try {
      const data = await API.get(`/api/invoices/return-original-items/${S._printingId}`);
      const inv = data.invoice || {};
      if (!inv.customer_id) { this.toast('المرتجع يتطلب فاتورة مرتبطة بعميل مسجل', 'warning'); return; }
      const rows = (data.items || []).filter(it => (parseFloat(it.quantity_returnable) || 0) > 0.0001);
      if (!rows.length) { this.toast('لا توجد كميات متاحة للإرجاع في هذه الفاتورة', 'warning'); return; }
      S._returnInvoiceData = data;
      document.getElementById('returnInvoiceMeta').innerHTML = `
        <strong>الفاتورة:</strong> ${Util.esc(inv.invoice_number || ('#' + inv.number))}
        &nbsp;—&nbsp; <strong>العميل:</strong> ${Util.esc(inv.customer_name || '-')}
        &nbsp;—&nbsp; <strong>أقصى كاش متاح للرد:</strong> ${Util.money(data.cash_refundable || 0)}
      `;
      document.getElementById('returnInvoiceItems').innerHTML = rows.map(it => `
        <tr>
          <td><input type="checkbox" class="return-item-check" data-pid="${it.product_id}"></td>
          <td>${Util.esc(it.product_name || '')}</td>
          <td>${Util.r3(it.quantity_sold)}</td>
          <td>${Util.r3(it.already_returned)}</td>
          <td><strong>${Util.r3(it.quantity_returnable)}</strong></td>
          <td>${Util.money(it.unit_price)}</td>
          <td><input type="number" class="return-item-qty" data-pid="${it.product_id}" min="0.001" max="${Util.r3(it.quantity_returnable)}" step="0.001" value="${Util.r3(it.quantity_returnable)}" style="width:100px" disabled></td>
        </tr>`).join('');
      document.querySelectorAll('#returnInvoiceItems .return-item-check').forEach(cb => cb.addEventListener('change', e => {
        const input = document.querySelector(`#returnInvoiceItems .return-item-qty[data-pid="${e.target.dataset.pid}"]`);
        if (input) input.disabled = !e.target.checked;
      }));
      document.getElementById('returnPaymentMethod').value = 'credit';
      document.getElementById('returnPaid').value = '';
      document.getElementById('returnNotes').value = '';
      this.updateReturnPaymentUI();
      this.closeModal('invoiceModal');
      document.getElementById('returnInvoiceModal').classList.add('active');
    } catch (e) { this.toast(e.message || 'تعذر تحميل بيانات المرتجع', 'error'); }
  },

  updateReturnPaymentUI() {
    const method = document.getElementById('returnPaymentMethod').value;
    document.getElementById('returnPartialGroup').style.display = method === 'partial' ? '' : 'none';
    const data = S._returnInvoiceData;
    const maxCash = parseFloat(data?.cash_refundable) || 0;
    const hint = document.getElementById('returnCashHint');
    if (method === 'credit') hint.textContent = 'لن يتم إخراج نقدية؛ قيمة المرتجع ستخفض رصيد العميل.';
    else if (method === 'cash') hint.textContent = `الرد النقدي الكامل مسموح فقط إذا كانت المدفوعات الأصلية المتاحة تكفي. المتاح حاليًا: ${Util.money(maxCash)}.`;
    else hint.textContent = `أدخل الجزء النقدي فقط، والباقي سيخفض حساب العميل. أقصى نقدي متاح: ${Util.money(maxCash)}.`;
  },

  async confirmReturnInvoice() {
    const data = S._returnInvoiceData;
    if (!data?.invoice) return;
    const items = [];
    document.querySelectorAll('#returnInvoiceItems .return-item-check:checked').forEach(cb => {
      const pid = parseInt(cb.dataset.pid);
      const input = document.querySelector(`#returnInvoiceItems .return-item-qty[data-pid="${pid}"]`);
      const qty = Util.r3(input?.value || 0);
      const source = (data.items || []).find(x => parseInt(x.product_id) === pid);
      const maxQty = Util.r3(source?.quantity_returnable || 0);
      if (qty > 0 && qty <= maxQty + 0.0001) items.push({ product_id: pid, quantity: qty });
    });
    if (!items.length) { this.toast('اختر صنفًا واحدًا على الأقل وحدد كمية صحيحة', 'warning'); return; }
    const method = document.getElementById('returnPaymentMethod').value;
    let paid = null;
    if (method === 'partial') {
      paid = Util.r2(document.getElementById('returnPaid').value || 0);
      if (paid <= 0) { this.toast('أدخل مبلغ الرد النقدي الجزئي', 'warning'); return; }
      const maxCash = parseFloat(data.cash_refundable) || 0;
      if (paid > maxCash + 0.001) { this.toast(`أقصى مبلغ نقدي متاح للرد ${Util.money(maxCash)}`, 'warning'); return; }
    }
    try {
      const result = await API.post('/api/invoices/return', {
        customer_id: data.invoice.customer_id,
        original_invoice_id: data.invoice.id,
        items,
        payment_method: method,
        paid,
        notes: document.getElementById('returnNotes').value.trim(),
      });
      this.toast(`تم إنشاء المرتجع ${result.invoice_number || ('#' + result.number)} بقيمة ${Util.money(result.total)}`);
      this.closeModal('returnInvoiceModal');
      S._returnInvoiceData = null;
      if (S.currentPage === 'invoices') await this.loadInvoicesPage();
      if (S.currentPage === 'customers' && S._currentCustomerId) await this.viewCustomer(S._currentCustomerId);
      if (S.currentPage === 'pos') await this.loadPOSProducts();
      await this.viewInvoice(result.id);
    } catch (e) { this.toast(e.message || 'فشل تنفيذ المرتجع', 'error'); }
  },

  async deleteInvoice(id, silent) {
    if (!silent && !await this.confirm('حذف فاتورة', 'حذف هذه الفاتورة؟')) return;
    try {
      await API.delete(`/api/invoices/${id}`);
      if (!silent) this.toast('تم الحذف');
      if (S.currentPage === 'invoices') await this.loadInvoicesPage();
      if (S.currentPage === 'customers' && S._currentCustomerId) await this.viewCustomer(S._currentCustomerId);
      if (S.currentPage === 'pos') await this.loadPOSProducts();
    } catch (e) { this.toast(e.message, 'error'); }
  },

  printCurrent() {
    if (!S._printingId) return;
    // Preview and browser print deliberately share the exact same PDF source.
    this.printInvoiceById(S._printingId);
  },

  async previewInvoice() {
    if (!S._printingId) return;
    await this.previewAndMaybePrintInvoicePdf(S._printingId, false);
  },

  async openCollect() {
    if (!S._printingId) return;
    try {
      const inv = await API.get(`/api/invoices/${S._printingId}`);
      if (inv.status === 'paid') { this.toast('الفاتورة مدفوعة بالفعل', 'warning'); return; }
      document.getElementById('colInvNum').value = `#${inv.number}`;
      document.getElementById('colCustName').value = inv.customer_name || '-';
      const due = parseFloat(inv.effective_remaining ?? inv.remaining) || 0;
      if (due <= 0.001) { this.toast('الفاتورة مسددة بالكامل بعد احتساب المرتجعات', 'warning'); return; }
      document.getElementById('colRemaining').value = due.toFixed(2);
      document.getElementById('colAmount').value = due.toFixed(2);
      document.getElementById('colAmount').max = due;
      document.getElementById('collectModal').classList.add('active');
      setTimeout(() => document.getElementById('colAmount').focus(), 50);
    } catch (e) { this.toast(e.message, 'error'); }
  },

  async confirmCollect() {
    if (!S._printingId) return;
    const amount = parseFloat(document.getElementById('colAmount').value) || 0;
    if (amount <= 0) { this.toast('أدخل مبلغ صحيح', 'error'); return; }
    try {
      const r = await API.post(`/api/invoices/${S._printingId}/collect`, {
        amount,
        method: document.getElementById('colMethod').value,
      });
      this.toast(`تم تحصيل ${Util.money(amount)} - باقي: ${Util.money(r.remaining)}`);
      this.closeModal('collectModal');
      await this.viewInvoice(S._printingId);
      if (S.currentPage === 'customers' && S._currentCustomerId) {
        await this.viewCustomer(S._currentCustomerId);
      }
    } catch (e) { this.toast(e.message, 'error'); }
  },

  async printInvoiceById(id) {
    await this.previewAndMaybePrintInvoicePdf(id, true);
  },
};
