/* Final pre-market UI/accounting overrides. Composed after upgradeMethods. */
import { S } from './core/state.js';
import { API } from './core/api.js';
import { Util } from './core/util.js';
import { upgradeMethods } from './upgrade_methods.js';
import './barcode_ux.js';

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

function ensureMobilePdfPreviewUi() {
  if (!document.getElementById('marketPdfMobileStyle')) {
    const style = document.createElement('style');
    style.id = 'marketPdfMobileStyle';
    style.textContent = `
      #pdfPreviewModal .modal-content{width:min(1080px,96vw);height:min(92vh,980px);display:flex;flex-direction:column}
      #pdfPreviewModal .modal-body{display:flex;flex:1;min-height:0;flex-direction:column}
      #pdfPreviewFrame{display:block;width:100%;height:100%;min-height:62vh;border:0;background:#fff;border-radius:8px}
      .pdf-mobile-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
      .pdf-mobile-tip{display:none;font-size:12px;color:var(--g500);padding:7px 2px 0;text-align:center}
      .invoice-share-btn{white-space:nowrap}
      @media(max-width:700px){
        #pdfPreviewModal{padding:0!important}
        #pdfPreviewModal .modal-content{width:100vw!important;max-width:none!important;height:100dvh!important;max-height:none!important;border-radius:0!important;margin:0!important}
        #pdfPreviewModal .modal-header{flex:0 0 auto;padding:10px 12px}
        #pdfPreviewModal .modal-body{padding:8px!important;min-height:0}
        #pdfPreviewFrame{flex:1;min-height:0;height:calc(100dvh - 150px);border-radius:4px}
        #pdfPreviewModal .modal-footer{flex:0 0 auto;padding:9px 10px;gap:7px;overflow-x:auto}
        .pdf-mobile-tip{display:block}
      }
    `;
    document.head.appendChild(style);
  }

  const modal = document.getElementById('pdfPreviewModal');
  if (!modal) return;
  const footer = modal.querySelector('.modal-footer') || modal.querySelector('.modal-content');
  if (!footer) return;

  let actions = document.getElementById('pdfMobileActions');
  if (!actions) {
    actions = document.createElement('div');
    actions.id = 'pdfMobileActions';
    actions.className = 'pdf-mobile-actions';
    actions.innerHTML = `
      <a class="btn btn-secondary" id="pdfPreviewOpenBtn" target="_blank" rel="noopener">فتح PDF</a>
      <button class="btn btn-primary" type="button" id="pdfPreviewShareBtn">مشاركة PDF</button>
    `;
    footer.appendChild(actions);
  }

  const body = modal.querySelector('.modal-body');
  if (body && !body.querySelector('.pdf-mobile-tip')) {
    const tip = document.createElement('div');
    tip.className = 'pdf-mobile-tip';
    tip.textContent = 'لو معاينة PDF لم تظهر داخل الصفحة على موبايلك، اضغط «فتح PDF».';
    body.appendChild(tip);
  }
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename || 'invoice.pdf';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    setTimeout(cleanOptionalInvoiceFields, 0);
    setTimeout(ensureMobilePdfPreviewUi, 0);
  }, { once: true });
} else {
  setTimeout(cleanOptionalInvoiceFields, 0);
  setTimeout(ensureMobilePdfPreviewUi, 0);
}

export const marketMethods = {
  setQtyToActive(delta) {
    if (!S.cart.length) return;
    const last = S.cart[S.cart.length - 1];
    const inc = Util.r3(delta);
    if (inc <= 0) return;

    const current = Util.r3(parseFloat(last.quantity) || 0);
    let target = Util.r3(current + inc);
    const product = S.productCache.get(last.product_id);
    const stock = product ? (parseFloat(product.stock) || 0) : Infinity;

    if (S.invoiceType === 'sale' && target > stock + 0.0000001) {
      if (stock <= current + 0.0000001) {
        this.toast(`وصلت للكمية المتاحة في المخزون (${Util.r3(stock)})`, 'warning');
        return;
      }
      target = Util.r3(stock);
      this.toast(`المتاح فقط ${target} وتمت الزيادة حتى حد المخزون`, 'warning');
    }

    last.quantity = target;
    last.total = Util.r2(last.quantity * last.unit_price);
    this.renderCart();
  },

  renderInvoicesTable(data) {
    upgradeMethods.renderInvoicesTable.call(this, data);
    document.querySelectorAll('#invoicesTable tr').forEach(row => {
      const view = row.querySelector('[data-view-inv]');
      if (!view || row.querySelector('[data-share-inv]')) return;
      const invoiceId = parseInt(view.dataset.viewInv);
      if (!invoiceId) return;
      const cell = row.lastElementChild;
      if (!cell) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn-sm btn-secondary invoice-share-btn';
      button.dataset.shareInv = String(invoiceId);
      button.textContent = 'مشاركة';
      button.title = 'مشاركة الفاتورة كملف PDF';
      button.addEventListener('click', () => this.shareInvoicePdf(invoiceId));
      cell.appendChild(button);
    });
  },

  async _prepareInvoicePdf(invoiceId) {
    const id = parseInt(invoiceId);
    if (!id) throw new Error('رقم الفاتورة غير صحيح');
    if (S._pdfPreviewInvoiceId === id && S._pdfPreviewBlob && S._pdfPreviewUrl) {
      return { blob: S._pdfPreviewBlob, url: S._pdfPreviewUrl, filename: S._pdfPreviewFilename || `invoice_${id}.pdf` };
    }

    const resp = await fetch(`/api/invoices/${id}/pdf`, { credentials: 'same-origin', cache: 'no-store' });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    const blob = await resp.blob();
    const cd = resp.headers.get('Content-Disposition') || '';
    const match = cd.match(/filename="?([^";]+)"?/i);
    const filename = match ? match[1] : `invoice_${id}.pdf`;

    if (S._pdfPreviewUrl) URL.revokeObjectURL(S._pdfPreviewUrl);
    const url = URL.createObjectURL(blob);
    S._pdfPreviewInvoiceId = id;
    S._pdfPreviewBlob = blob;
    S._pdfPreviewFilename = filename;
    S._pdfPreviewUrl = url;
    return { blob, url, filename };
  },

  async previewAndMaybePrintInvoicePdf(invoiceId, autoPrint) {
    try {
      ensureMobilePdfPreviewUi();
      const prepared = await this._prepareInvoicePdf(invoiceId);
      const frame = document.getElementById('pdfPreviewFrame');
      const download = document.getElementById('pdfPreviewDownload');
      const open = document.getElementById('pdfPreviewOpenBtn');
      const share = document.getElementById('pdfPreviewShareBtn');

      if (frame) frame.src = prepared.url;
      if (download) { download.href = prepared.url; download.download = prepared.filename; }
      if (open) { open.href = prepared.url; open.removeAttribute('download'); }
      if (share) share.onclick = () => this.shareInvoicePdf(invoiceId);

      document.getElementById('pdfPreviewModal')?.classList.add('active');

      if (autoPrint && frame) {
        frame.onload = () => {
          frame.onload = null;
          try {
            frame.contentWindow?.focus();
            frame.contentWindow?.print();
          } catch {
            this.toast('تعذر فتح نافذة الطباعة؛ الفاتورة ظاهرة ويمكن فتحها أو تنزيلها', 'warning');
          }
        };
      }
    } catch (e) {
      this.toast(e.message || 'تعذّر فتح معاينة الفاتورة', 'error');
    }
  },

  async shareInvoicePdf(invoiceId = S._printingId) {
    try {
      const prepared = await this._prepareInvoicePdf(invoiceId);
      const storeName = String(S.settings?.store_name || 'POS').trim() || 'POS';
      const title = `فاتورة - ${storeName}`;
      const canUseFileShare = typeof File !== 'undefined' && typeof navigator.share === 'function';

      if (canUseFileShare) {
        const file = new File([prepared.blob], prepared.filename, { type: 'application/pdf' });
        const shareData = { title, text: 'فاتورة PDF', files: [file] };
        const supported = typeof navigator.canShare !== 'function' || navigator.canShare({ files: [file] });
        if (supported) {
          try {
            await navigator.share(shareData);
            return;
          } catch (err) {
            if (err?.name === 'AbortError') return;
          }
        }
      }

      downloadBlob(prepared.blob, prepared.filename);
      this.toast('المشاركة المباشرة للملفات غير متاحة في هذا المتصفح؛ تم تنزيل PDF ويمكنك إرساله من الجهاز', 'warning');
    } catch (e) {
      this.toast(e.message || 'تعذر تجهيز الفاتورة للمشاركة', 'error');
    }
  },

  printPdfPreview() {
    const frame = document.getElementById('pdfPreviewFrame');
    if (!frame?.src) {
      this.toast('لا توجد فاتورة مفتوحة للطباعة', 'warning');
      return;
    }
    try {
      frame.contentWindow?.focus();
      frame.contentWindow?.print();
    } catch {
      this.toast('الطباعة غير متاحة حالياً؛ استخدم فتح PDF أو تنزيله', 'warning');
    }
  },

  async viewCustomer(id) {
    await upgradeMethods.viewCustomer.call(this, id);

    // Invoice.to_dict() already sends returns as negative values. Never apply
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
