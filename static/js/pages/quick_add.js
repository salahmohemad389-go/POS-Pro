import { S } from '../core/state.js';
import { API } from '../core/api.js';
import { Util } from '../core/util.js';

export const quickAddMethods = {
  async openQuickAdd(query = '') {
    await this.loadCategoriesForPOS();
    const sel = document.getElementById('qaCategory');
    const topLevel = S.categoryChildren.get(0) || [];
    sel.innerHTML = '<option value="">بدون قسم</option>' + topLevel.map(c => `<option value="${c.id}">${Util.esc(c.name)}</option>`).join('');
    const raw = String(query || '').trim();
    const looksLikeCode = !!raw && /^[A-Za-z0-9._\/-]+$/.test(raw);
    document.getElementById('qaBarcode').value = looksLikeCode ? raw : '';
    document.getElementById('qaName').value = looksLikeCode ? '' : raw;
    document.getElementById('qaPrice').value = 0;
    document.getElementById('qaQty').value = 1;
    document.getElementById('quickAddModal').classList.add('active');
    setTimeout(() => document.getElementById(looksLikeCode ? 'qaName' : 'qaPrice').focus(), 50);
  },

  async saveQuickAdd() {
    const barcode = document.getElementById('qaBarcode').value.trim();
    const name = document.getElementById('qaName').value.trim();
    const price = parseFloat(document.getElementById('qaPrice').value) || 0;
    const qty = Util.r3(parseFloat(document.getElementById('qaQty').value) || 1);
    const cat = document.getElementById('qaCategory').value || null;
    if (!name) { this.toast('أدخل الاسم', 'error'); return; }
    if (qty < 0.001) { this.toast('الكمية يجب أن تكون 0.001 على الأقل', 'error'); return; }
    if (price < 0) { this.toast('السعر غير صالح', 'error'); return; }
    try {
      const r = await API.post('/api/products', {
        barcode, code: '', name, category_id: cat,
        unit: 'قطعة', cost: 0, price, stock: qty,
      });
      const p = await API.get(`/api/products/${r.id}`);
      if (p) S.productCache.set(p.id, p);
      S.cart.push({
        product_id: r.id, product_name: name, barcode,
        quantity: qty, unit_price: price, cost: 0,
        total: Util.r2(price * qty),
      });
      this.renderCart();
      this.closeModal('quickAddModal');
      this.toast(`تمت إضافة ${name}`);
    } catch (e) { this.toast(e.message, 'error'); }
  },
};
