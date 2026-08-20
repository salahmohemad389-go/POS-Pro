/* Final pre-market UI/accounting overrides. Composed after upgradeMethods. */
import { S } from './core/state.js';
import { API } from './core/api.js';
import { Util } from './core/util.js';
import { upgradeMethods } from './upgrade_methods.js';

const has = permission => !!(S.user?.permissions || []).includes(permission);

function cleanOptionalInvoiceFields() {
  const phone = document.getElementById('invoicePrintPhone');
  const address = document.getElementById('invoicePrintAddress');
  const note = document.querySelector('.invoice-meta-note');
  if (note) note.remove();
  if (phone) {
    phone.placeholder = '';
    phone.setAttribute('aria-label', 'رقم تليفون اختياري للفاتورة');
    phone.title = 'رقم تليفون اختياري';
  }
  if (address) {
    address.placeholder = '';
    address.setAttribute('aria-label', 'عنوان اختياري للفاتورة');
    address.title = 'عنوان اختياري';
  }
  const box = document.querySelector('.invoice-optional-meta');
  if (box && !box.dataset.marketLabels) {
    box.dataset.marketLabels = '1';
    phone?.classList.add('invoice-optional-input');
    address?.classList.add('invoice-optional-input');
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => setTimeout(cleanOptionalInvoiceFields, 0), { once: true });
} else {
  setTimeout(cleanOptionalInvoiceFields, 0);
}

export const marketMethods = {
  async viewCustomer(id) {
    await upgradeMethods.viewCustomer.call(this, id);

    // Invoice.to_dict() already sends returns as negative values.  Never apply
    // another negative sign here, otherwise returns are incorrectly added.
    const invoices = Array.from(S._customerInvoiceMap?.values?.() || []);
    const financial = invoices.filter(inv => inv.type !== 'combined');
    const total = financial.reduce((sum, inv) => sum + (parseFloat(inv.total) || 0), 0);
    const paid = financial.reduce((sum, inv) => sum + (parseFloat(inv.paid) || 0), 0);
    const customer = S.customerCache.get(id);
    document.getElementById('cdInvCount').textContent = String(financial.length);
    document.getElementById('cdTotal').textContent = Util.money(total);
    document.getElementById('cdPaid').textContent = Util.money(paid);
    document.getElementById('cdDebt').textContent = Util.money(parseFloat(customer?.balance) || 0);

    if (!has('invoice_delete')) return;
    document.querySelectorAll('#cdInvoicesTable tr').forEach(row => {
      const selector = row.querySelector('[data-sel-inv]');
      if (!selector || row.querySelector('[data-del-inv]')) return;
      const invoiceId = parseInt(selector.dataset.selInv);
      if (!invoiceId) return;
      const cell = row.lastElementChild;
      if (!cell) return;
      const button = document.createElement('button');
      button.className = 'btn btn-sm btn-danger';
      button.dataset.delInv = String(invoiceId);
      button.textContent = 'حذف';
      button.title = 'حذف مع عكس التأثير المالي والمخزني';
      button.addEventListener('click', () => this.deleteInvoice(invoiceId));
      cell.appendChild(button);
    });
  },

  calcSelected() {
    if (!S.selectedInvoices || !S.selectedInvoices.size) {
      this.toast('حدد الفواتير أولاً', 'warning');
      return;
    }
    let total = 0, paid = 0, remaining = 0, count = 0;
    for (const id of S.selectedInvoices) {
      const inv = S._customerInvoiceMap?.get(id);
      if (!inv || inv.type === 'combined') continue;
      // Values are already signed by the API (returns are negative).
      total += parseFloat(inv.total) || 0;
      paid += parseFloat(inv.paid) || 0;
      remaining += parseFloat(inv.remaining) || 0;
      count += 1;
    }
    document.getElementById('calcCount').textContent = String(count);
    document.getElementById('calcTotal').textContent = Util.money(total);
    document.getElementById('calcPaid').textContent = Util.money(paid);
    document.getElementById('calcRemaining').textContent = Util.money(remaining);
    document.getElementById('calcResult').style.display = 'block';
    this.toast(`تم تجميع ${count} فاتورة مالية`);
  },

  async deleteProduct(id) {
    const product = S.productCache.get(id);
    const name = product?.name || `#${id}`;
    const ok = await this.confirm(
      'حذف المنتج',
      `سيتم حذف «${name}» من قوائم المنتجات ونقطة البيع حتى لو له فواتير سابقة. الفواتير والحركات القديمة ستظل محفوظة ولن يضيع التاريخ المالي. هل تريد المتابعة؟`,
    );
    if (!ok) return;
    try {
      await API.delete(`/api/products/${id}`);
      S.productCache.delete(id);
      this.toast('تم حذف المنتج مع الاحتفاظ بتاريخه السابق');
      if (S.currentPage === 'products') await this.loadProductsPage();
      if (S.currentPage === 'pos') await this.loadPOSProducts();
    } catch (e) {
      this.toast(e.message || 'تعذر حذف المنتج', 'error');
    }
  },

  async deleteCustomer(id) {
    const customer = S.customerCache.get(id);
    const name = customer?.name || `#${id}`;
    const ok = await this.confirm(
      'حذف العميل',
      `سيتم حذف «${name}» من قائمة العملاء حتى لو له فواتير أو رصيد. الفواتير وكشف الحساب والرصيد التاريخي سيظلون محفوظين للمراجعة. هل تريد المتابعة؟`,
    );
    if (!ok) return;
    try {
      await API.delete(`/api/customers/${id}`);
      S.customerCache.delete(id);
      if (S.cartCustomer === id) this.clearCustomer();
      this.toast('تم حذف العميل مع الاحتفاظ بتاريخه المالي');
      if (S.currentPage === 'customers') await this.loadCustomersPage();
    } catch (e) {
      this.toast(e.message || 'تعذر حذف العميل', 'error');
    }
  },

  async deleteInvoice(id, silent = false) {
    if (!silent) {
      const ok = await this.confirm(
        'حذف الفاتورة نهائياً',
        'سيتم حذف الفاتورة وعكس تأثيرها على المخزون ورصيد العميل. إذا كانت فاتورة بيع ولها مرتجعات فسيتم حذف المرتجعات المرتبطة بها وعكسها أيضاً. سيتم الاحتفاظ بنسخة في سجل العمليات. هل تريد المتابعة؟',
      );
      if (!ok) return;
    }
    try {
      await API.delete(`/api/invoices/${id}`);
      S.invoices?.selected?.delete?.(id);
      S.selectedInvoices?.delete?.(id);
      if (!silent) this.toast('تم حذف الفاتورة وعكس تأثيرها الحسابي');
      if (S.currentPage === 'invoices') await this.loadInvoicesPage();
      if (S.currentPage === 'customers' && S._currentCustomerId) await this.viewCustomer(S._currentCustomerId);
      if (S.currentPage === 'pos') await this.loadPOSProducts();
    } catch (e) {
      this.toast(e.message || 'تعذر حذف الفاتورة', 'error');
    }
  },
};
