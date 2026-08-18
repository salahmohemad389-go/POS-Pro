import { S } from '../core/state.js';
import { API } from '../core/api.js';
import { Util } from '../core/util.js';

export const supplierMethods = {
  async loadSuppliersPage() {
    try {
      const params = new URLSearchParams({ page: S.suppliersPage.page, limit: S.suppliersPage.limit });
      if (S.suppliersPage.q) params.set('q', S.suppliersPage.q);
      const data = await API.get(`/api/suppliers?${params}`);
      data.items.forEach(s => S.supplierCache.set(s.id, s));
      this.renderSuppliersTable(data);
      this.renderPagination('suppliersPagination', data, 'suppliers');
    } catch (e) { this.toast(e.message, 'error'); }
  },

  renderSuppliersTable(data) {
    const tbody = document.getElementById('suppliersTable');
    if (!data.items.length) { tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--g400);padding:30px">لا يوجد موردون</td></tr>'; return; }
    // Use createElement for safer rendering
    tbody.innerHTML = '';
    data.items.forEach(s => {
      const tr = Util.el('tr', {}, [
        Util.el('td', {}, [Util.el('strong', {}, s.name)]),
        Util.el('td', {}, [s.phone || '-']),
        Util.el('td', {}, [s.email || '-']),
        Util.el('td', { style: `color:${(parseFloat(s.balance)||0)>0?'var(--err)':'var(--ok)'};font-weight:700`, text: Util.money(s.balance) }),
        Util.el('td', {}, [
          Util.el('button', { class: 'btn btn-sm btn-secondary', 'data-edit-sup': s.id, onclick: () => this.openSupplierModal(s.id) }, ['تعديل']),
          ' ',
          Util.el('button', { class: 'btn btn-sm btn-danger', 'data-del-sup': s.id, onclick: () => this.deleteSupplier(s.id) }, ['حذف']),
        ]),
      ]);
      tbody.appendChild(tr);
    });
  },

  openSupplierModal(id) {
    const m = document.getElementById('supplierModal');
    if (id) {
      const s = S.supplierCache.get(id); if (!s) return;
      document.getElementById('supplierModalTitle').textContent = 'تعديل مورد';
      document.getElementById('supplierId').value = s.id;
      document.getElementById('supplierName').value = s.name || '';
      document.getElementById('supplierPhone').value = s.phone || '';
      document.getElementById('supplierEmail').value = s.email || '';
      document.getElementById('supplierAddress').value = s.address || '';
      document.getElementById('supplierNotes').value = s.notes || '';
    } else {
      document.getElementById('supplierModalTitle').textContent = 'مورد جديد';
      document.getElementById('supplierId').value = '';
      document.getElementById('supplierName').value = '';
      document.getElementById('supplierPhone').value = '';
      document.getElementById('supplierEmail').value = '';
      document.getElementById('supplierAddress').value = '';
      document.getElementById('supplierNotes').value = '';
    }
    m.classList.add('active');
    setTimeout(() => document.getElementById('supplierName').focus(), 50);
  },

  async saveSupplier() {
    const id = document.getElementById('supplierId').value;
    const name = document.getElementById('supplierName').value.trim();
    if (!name) { this.toast('أدخل اسم المورد', 'error'); return; }
    try {
      await API.post('/api/suppliers', {
        id: id || undefined,
        name,
        phone: document.getElementById('supplierPhone').value.trim(),
        email: document.getElementById('supplierEmail').value.trim(),
        address: document.getElementById('supplierAddress').value.trim(),
        notes: document.getElementById('supplierNotes').value.trim(),
      });
      this.toast(id ? 'تم تعديل المورد' : 'تم إضافة المورد');
      this.closeModal('supplierModal');
      await this.loadSuppliersPage();
    } catch (e) { this.toast(e.message, 'error'); }
  },

  async deleteSupplier(id) {
    const s = S.supplierCache.get(id);
    if (!await this.confirm('حذف مورد', `حذف "${s?.name || ''}"؟`)) return;
    try {
      await API.delete(`/api/suppliers/${id}`);
      S.supplierCache.delete(id);
      this.toast('تم الحذف');
      await this.loadSuppliersPage();
    } catch (e) { this.toast(e.message, 'error'); }
  },

  async loadSuppliersForSelect() {
    if (S.supplierCache.size) return;
    try {
      const data = await API.get('/api/suppliers?limit=500');
      data.items.forEach(s => S.supplierCache.set(s.id, s));
    } catch (e) { /* ignore */ }
  },

  renderCategoriesGrid() {
    const el = document.getElementById('categoriesGrid');
    const topLevel = S.categoryChildren.get(0) || [];
    if (!topLevel.length) { el.innerHTML = '<div class="empty-cart">لا توجد أقسام</div>'; return; }
    el.innerHTML = topLevel.map(c => {
      const subs = S.categoryChildren.get(c.id) || [];
      const prodCount = Array.from(S.productCache.values()).filter(p => p.category_id === c.id || subs.some(s => s.id === p.category_id)).length;
      const subHtml = subs.length ? `<div class="subcat-list">${subs.map(s => `
        <div class="subcat-item">
          <span>${Util.esc(s.name)}</span>
          <span>
            <button class="btn btn-sm btn-secondary" data-edit-cat="${s.id}">✎</button>
            <button class="btn btn-sm btn-danger" data-del-cat="${s.id}">✕</button>
          </span>
        </div>
      `).join('')}</div>` : '';
      return `<div class="category-card">
        <div class="ci">📁</div>
        <div class="cn">${Util.esc(c.name)}</div>
        <div class="cc">${prodCount} منتج • ${subs.length} فرعي</div>
        <div class="ca">
          <button class="btn btn-sm btn-secondary" data-edit-cat="${c.id}">تعديل</button>
          <button class="btn btn-sm btn-primary" data-sub-cat="${c.id}">+ فرعي</button>
          <button class="btn btn-sm btn-danger" data-del-cat="${c.id}">حذف</button>
        </div>
        ${subHtml}
      </div>`;
    }).join('');
    el.querySelectorAll('[data-edit-cat]').forEach(b => b.addEventListener('click', () => this.openCategoryModal(parseInt(b.dataset.editCat))));
    el.querySelectorAll('[data-del-cat]').forEach(b => b.addEventListener('click', () => this.deleteCategory(parseInt(b.dataset.delCat))));
    el.querySelectorAll('[data-sub-cat]').forEach(b => b.addEventListener('click', () => this.openCategoryModal(null, parseInt(b.dataset.subCat))));
  },

  openCategoryModal(id, parentId) {
    const m = document.getElementById('categoryModal');
    const sel = document.getElementById('categoryParent');
    const topLevel = (S.categoryChildren.get(0) || []).filter(c => c.id !== id);
    sel.innerHTML = '<option value="">رئيسي</option>' + topLevel.map(c => `<option value="${c.id}">${Util.esc(c.name)}</option>`).join('');
    if (id) {
      const c = S.categoryCache.get(id); if (!c) return;
      document.getElementById('categoryModalTitle').textContent = 'تعديل قسم';
      document.getElementById('categoryId').value = c.id;
      document.getElementById('categoryName').value = c.name;
      sel.value = c.parent_id || '';
    } else {
      document.getElementById('categoryModalTitle').textContent = 'قسم جديد';
      document.getElementById('categoryId').value = '';
      document.getElementById('categoryName').value = '';
      sel.value = parentId || '';
    }
    m.classList.add('active');
    setTimeout(() => document.getElementById('categoryName').focus(), 50);
  },

  async saveCategory() {
    const id = document.getElementById('categoryId').value;
    const name = document.getElementById('categoryName').value.trim();
    if (!name) { this.toast('أدخل اسم القسم', 'error'); return; }
    try {
      await API.post('/api/categories', {
        id: id || undefined,
        name,
        parent_id: document.getElementById('categoryParent').value || null,
      });
      this.toast(id ? 'تم تعديل القسم' : 'تم إضافة القسم');
      this.closeModal('categoryModal');
      await this.loadCategoriesPage();
    } catch (e) { this.toast(e.message, 'error'); }
  },

  async deleteCategory(id) {
    const c = S.categoryCache.get(id);
    if (!await this.confirm('حذف قسم', `حذف "${c?.name || ''}" وكل الأقسام الفرعية؟`)) return;
    try {
      await API.delete(`/api/categories/${id}`);
      this.toast('تم الحذف');
      await this.loadCategoriesPage();
    } catch (e) { this.toast(e.message, 'error'); }
  },
};
