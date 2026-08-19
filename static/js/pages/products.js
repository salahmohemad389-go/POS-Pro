import { S } from '../core/state.js';
import { API } from '../core/api.js';
import { Util } from '../core/util.js';

export const productMethods = {
  async loadProductsPage() {
    try {
      const params = new URLSearchParams({ page: S.productsPage.page, limit: S.productsPage.limit });
      if (S.productsPage.q) params.set('q', S.productsPage.q);
      const data = await API.get(`/api/products?${params}`);
      data.items.forEach(p => S.productCache.set(p.id, p));
      if (!S.categoryCache.size) await this.loadCategoriesForPOS();
      this.renderProductsTable(data);
      this.renderPagination('productsPagination', data, 'products');
    } catch (e) {
      document.getElementById('productsTable').innerHTML = `<tr><td colspan="9" style="text-align:center;color:var(--err)">${Util.esc(e.message)}</td></tr>`;
    }
  },

  switchProductsTab(tab) {
    document.querySelectorAll('[data-pctab]').forEach(b => b.classList.toggle('active', b.dataset.pctab === tab));
    document.getElementById('pcTabProducts').style.display = tab === 'products' ? 'block' : 'none';
    document.getElementById('pcTabCategories').style.display = tab === 'categories' ? 'block' : 'none';
    if (tab === 'categories') this.loadCategoriesPage();
  },

  renderProductsTable(data) {
    const tbody = document.getElementById('productsTable');
    const catMap = {};
    S.categoryCache.forEach(c => catMap[c.id] = c.name);
    if (!data.items.length) { tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--g400);padding:30px">لا توجد منتجات</td></tr>'; return; }
    tbody.innerHTML = data.items.map(p => `
      <tr>
        <td style="font-family:monospace;font-size:12px">${Util.esc(p.barcode || '-')}</td>
        <td style="font-family:monospace;font-size:12px">${Util.esc(p.code || '-')}</td>
        <td><strong>${Util.esc(p.name)}</strong></td>
        <td>${Util.esc(catMap[p.category_id] || '-')}</td>
        <td>${Util.esc(p.unit || '-')}</td>
        <td>${Util.money(p.cost)}</td>
        <td><strong>${Util.money(p.price)}</strong></td>
        <td>${p.stock || 0}</td>
        <td>
          <button class="btn btn-sm btn-secondary" data-edit="${p.id}">تعديل</button>
          <button class="btn btn-sm btn-danger" data-del="${p.id}">حذف</button>
        </td>
      </tr>
    `).join('');
    tbody.querySelectorAll('[data-edit]').forEach(b => b.addEventListener('click', () => this.openProductModal(parseInt(b.dataset.edit))));
    tbody.querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', () => this.deleteProduct(parseInt(b.dataset.del))));
  },

  async openProductModal(id) {
    await this.loadCategoriesForPOS();
    const m = document.getElementById('productModal');
    const cat = document.getElementById('productCategory');
    const subCat = document.getElementById('productSubCategory');
    const sup = document.getElementById('productSupplier');
    const topLevel = S.categoryChildren.get(0) || [];
    cat.innerHTML = '<option value="">بدون قسم</option>' + topLevel.map(c => `<option value="${c.id}">${Util.esc(c.name)}</option>`).join('');
    subCat.innerHTML = '<option value="">بدون</option>';
    sup.innerHTML = '<option value="">بدون مورد</option>';

    if (id) {
      let p = S.productCache.get(id);
      if (!p) { try { p = await API.get(`/api/products/${id}`); } catch {} }
      if (!p) { this.toast('منتج غير موجود', 'error'); return; }
      document.getElementById('productModalTitle').textContent = 'تعديل منتج';
      document.getElementById('productId').value = p.id;
      document.getElementById('productBarcode').value = p.barcode || '';
      document.getElementById('productCode').value = p.code || '';
      document.getElementById('productName').value = p.name || '';
      cat.value = p.category_id || '';
      this.updateProductSubCategories();
      const catObj = S.categoryCache.get(p.category_id);
      if (catObj && catObj.parent_id) { cat.value = catObj.parent_id; this.updateProductSubCategories(); subCat.value = p.category_id; }
      document.getElementById('productUnit').value = p.unit || 'قطعة';
      document.getElementById('productCost').value = p.cost || 0;
      document.getElementById('productPrice').value = p.price || 0;
      document.getElementById('productStock').value = p.stock || 0;
      sup.value = p.supplier_id || '';
      document.getElementById('productMinStock').value = p.min_stock || 5;
    } else {
      document.getElementById('productModalTitle').textContent = 'منتج جديد';
      document.getElementById('productId').value = '';
      document.getElementById('productBarcode').value = '';
      document.getElementById('productCode').value = '';
      document.getElementById('productName').value = '';
      cat.value = ''; subCat.value = ''; sup.value = '';
      document.getElementById('productUnit').value = 'قطعة';
      document.getElementById('productCost').value = 0;
      document.getElementById('productPrice').value = 0;
      document.getElementById('productStock').value = 0;
      document.getElementById('productMinStock').value = 5;
    }
    m.classList.add('active');
    setTimeout(() => document.getElementById('productName').focus(), 50);
  },

  updateProductSubCategories() {
    const cat = document.getElementById('productCategory');
    const sub = document.getElementById('productSubCategory');
    const pid = parseInt(cat.value);
    const subs = (S.categoryChildren.get(pid) || []);
    sub.innerHTML = '<option value="">بدون</option>' + subs.map(s => `<option value="${s.id}">${Util.esc(s.name)}</option>`).join('');
  },

  async saveProduct() {
    const id = document.getElementById('productId').value;
    const name = document.getElementById('productName').value.trim();
    if (!name) { this.toast('أدخل اسم المنتج', 'error'); return; }
    const subCat = document.getElementById('productSubCategory').value;
    const mainCat = document.getElementById('productCategory').value;
    const data = {
      id: id || undefined, barcode: document.getElementById('productBarcode').value.trim(), code: document.getElementById('productCode').value.trim(), name,
      category_id: subCat || mainCat || null, unit: document.getElementById('productUnit').value,
      cost: parseFloat(document.getElementById('productCost').value) || 0, price: parseFloat(document.getElementById('productPrice').value) || 0,
      stock: parseFloat(document.getElementById('productStock').value) || 0, min_stock: parseFloat(document.getElementById('productMinStock').value) || 5,
      supplier_id: document.getElementById('productSupplier').value || null,
    };
    try { await API.post('/api/products', data); this.toast(id ? 'تم تعديل المنتج' : 'تم إضافة المنتج'); this.closeModal('productModal'); await this.loadProductsPage(); }
    catch (e) { this.toast(e.message, 'error'); }
  },

  async deleteProduct(id) {
    const p = S.productCache.get(id);
    if (!await this.confirm('حذف منتج', `حذف "${p?.name || ''}"؟`)) return;
    try { await API.delete(`/api/products/${id}`); this.toast('تم الحذف'); await this.loadProductsPage(); }
    catch (e) { this.toast(e.message, 'error'); }
  },

  async importExcel(input) {
    const file = input.files[0]; if (!file) return;
    const fd = new FormData(); fd.append('file', file);
    try {
      const resp = await fetch('/api/products/import', { method: 'POST', credentials: 'same-origin', body: fd });
      if (!resp.ok) { const err = await resp.json().catch(() => ({})); throw new Error(err.detail || 'فشل'); }
      const r = await resp.json();
      if (r.errors && r.errors.length) {
        const errSample = r.errors.slice(0, 3).map(e => `صف ${e.row}: ${e.error}`).join('\n');
        const more = r.total_errors > r.errors.length ? ` (+${r.total_errors - r.errors.length} أخطاء أخرى)` : '';
        this.toast(`تم استيراد ${r.added} منتج، تم تخطي ${r.skipped_duplicates || 0} مكرر${more}: ${errSample}`, r.added > 0 ? 'success' : 'error');
      } else this.toast(`تم استيراد ${r.added} منتج (تم تخطي ${r.skipped_duplicates || 0} مكرر)`);
      await this.loadProductsPage();
    } catch (e) { this.toast(e.message, 'error'); } finally { input.value = ''; }
  },

  async updatePrices(input) {
    const file = input.files[0]; if (!file) return;
    const fd = new FormData(); fd.append('file', file);
    try {
      const resp = await fetch('/api/products/import-prices', { method: 'POST', credentials: 'same-origin', body: fd });
      if (!resp.ok) { const err = await resp.json().catch(() => ({})); throw new Error(err.detail || 'فشل تحديث الأسعار'); }
      const r = await resp.json(); const missing = r.not_found || 0; const unchanged = r.unchanged || 0;
      this.toast(`تم تحديث أسعار ${r.updated || 0} منتج • بدون تغيير ${unchanged} • غير موجود ${missing}`, missing ? 'warning' : 'success');
      if (r.errors?.length) console.warn('Price update import errors', r.errors);
      await this.loadProductsPage(); if (S.currentPage === 'pos') await this.loadPOSProducts();
    } catch (e) { this.toast(e.message, 'error'); } finally { input.value = ''; }
  },

  bindDownloadLinks() {
    document.querySelectorAll('a[href*="/export"], a[href*="/pdf"]').forEach(a => {
      if (a.dataset.bound === '1') return; a.dataset.bound = '1';
      a.addEventListener('click', async (ev) => {
        ev.preventDefault();
        try {
          const resp = await fetch(a.href, { credentials: 'same-origin' });
          if (!resp.ok) { const err = await resp.json().catch(() => ({})); throw new Error(err.detail || `HTTP ${resp.status}`); }
          const blob = await resp.blob(); const cd = resp.headers.get('Content-Disposition') || ''; const m = cd.match(/filename="?([^";]+)"?/);
          const filename = m ? m[1] : (a.href.split('/').pop() || 'download'); const url = URL.createObjectURL(blob); const link = document.createElement('a');
          link.href = url; link.download = filename; document.body.appendChild(link); link.click(); document.body.removeChild(link); setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (e) { this.toast(e.message || 'فشل التحميل', 'error'); }
      });
    });
  },

  async loadCategoriesPage() {
    try { const cats = await API.get('/api/categories'); S.categoryCache.clear(); cats.forEach(c => S.categoryCache.set(c.id, c)); this.buildCategoryChildren(); this.renderCategoriesGrid(); }
    catch (e) { this.toast(e.message, 'error'); }
  },
};
