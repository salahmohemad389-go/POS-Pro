import { S } from '../core/state.js';
import { API } from '../core/api.js';
import { Util } from '../core/util.js';

export const customerMethods = {
  renderCustomers() {
    document.getElementById('customersView').style.display = 'block';
    document.getElementById('customerDetail').style.display = 'none';
    document.getElementById('custPageTitle').textContent = 'العملاء';
    document.getElementById('backToCustomersBtn').style.display = 'none';
    this.loadCustomersPage();
  },

  async loadCustomersPage() {
    try {
      const params = new URLSearchParams({ page: S.customersPage.page, limit: S.customersPage.limit });
      if (S.customersPage.q) params.set('q', S.customersPage.q);
      const data = await API.get(`/api/customers?${params}`);
      data.items.forEach(c => S.customerCache.set(c.id, c));
      this.renderCustomersTable(data);
      this.renderPagination('customersPagination', data, 'customers');
    } catch (e) { this.toast(e.message, 'error'); }
  },

  renderCustomersTable(data) {
    const tbody = document.getElementById('customersTable');
    if (!data.items.length) { tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--g400);padding:30px">لا يوجد عملاء</td></tr>'; return; }
    tbody.innerHTML = data.items.map(c => `
      <tr>
        <td><a href="#" data-view="${c.id}"><strong>${Util.esc(c.name)}</strong></a></td>
        <td>${Util.esc(c.phone || '-')}</td>
        <td style="color:${(parseFloat(c.balance) || 0) > 0 ? 'var(--err)' : 'var(--ok)'};font-weight:700">${Util.money(c.balance)}</td>
        <td>
          <button class="btn btn-sm btn-primary" data-view="${c.id}">📄 الفواتير</button>
          <button class="btn btn-sm btn-secondary" data-edit="${c.id}">تعديل</button>
          <button class="btn btn-sm btn-danger" data-del="${c.id}">حذف</button>
        </td>
      </tr>
    `).join('');
    tbody.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', e => { e.preventDefault(); this.viewCustomer(parseInt(b.dataset.view)); }));
    tbody.querySelectorAll('[data-edit]').forEach(b => b.addEventListener('click', () => this.openCustomerModal(parseInt(b.dataset.edit))));
    tbody.querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', () => this.deleteCustomer(parseInt(b.dataset.del))));
  },

  backToCustomers() { this.renderCustomers(); },

  async viewCustomer(id) {
    try {
      const data = await API.get(`/api/invoices?customer_id=${id}&limit=500`);
      const c = S.customerCache.get(id);
      if (!c) { this.toast('العميل غير موجود', 'error'); return; }
      document.getElementById('customersView').style.display = 'none';
      document.getElementById('customerDetail').style.display = 'block';
      document.getElementById('custPageTitle').textContent = 'صفحة العميل';
      document.getElementById('backToCustomersBtn').style.display = 'inline-flex';
      document.getElementById('cdName').textContent = c.name;
      document.getElementById('cdPhone').textContent = c.phone || '';
      const invs = data.items;
      const financialInvs = invs.filter(i => i.type !== 'combined');
      S._customerInvoiceMap = new Map(invs.map(i => [i.id, i]));
      let total = 0, paid = 0, debt = 0;
      financialInvs.forEach(i => {
        const sign = i.type === 'return' ? -1 : 1;
        total += sign * (parseFloat(i.total) || 0);
        paid += sign * (parseFloat(i.paid) || 0);
      });
      debt = parseFloat(c.balance) || 0;
      document.getElementById('cdInvCount').textContent = financialInvs.length;
      document.getElementById('cdTotal').textContent = Util.money(total);
      document.getElementById('cdPaid').textContent = Util.money(paid);
      document.getElementById('cdDebt').textContent = Util.money(debt);

      S._currentCustomerId = id;
      S.selectedInvoices = new Set();
      document.getElementById('calcResult').style.display = 'none';

      const tbody = document.getElementById('cdInvoicesTable');
      if (!invs.length) { tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--g400);padding:30px">لا توجد فواتير</td></tr>'; return; }
      tbody.innerHTML = invs.map(inv => `
        <tr>
          <td><input type="checkbox" data-sel-inv="${inv.id}"></td>
          <td>${inv.number}</td>
          <td><span class="badge ${Util.invBadgeClass(inv.type)}">${Util.invLabel(inv.type)}</span></td>
          <td><strong>${Util.money(inv.total)}</strong></td>
          <td>${Util.money(inv.paid)}</td>
          <td style="color:${(parseFloat(inv.remaining) || 0) > 0 ? 'var(--err)' : 'var(--ok)'};font-weight:700">${Util.money(inv.remaining)}</td>
          <td><span class="badge ${inv.status === 'paid' ? 'badge-success' : inv.status === 'partial' ? 'badge-warning' : 'badge-danger'}">${inv.status === 'paid' ? 'مدفوعة' : inv.status === 'partial' ? 'جزئي' : 'آجل'}</span></td>
          <td>${Util.date(inv.created_at)}</td>
          <td>
            <button class="btn btn-sm btn-secondary" data-view-inv="${inv.id}">عرض</button>
            ${inv.type === 'combined' && S.user?.role === 'admin' ? `<button class="btn btn-sm btn-danger" data-del-inv="${inv.id}">حذف</button>` : ''}
          </td>
        </tr>
      `).join('');
      tbody.querySelectorAll('[data-sel-inv]').forEach(c => c.addEventListener('change', e => {
        const id = parseInt(e.target.dataset.selInv);
        if (e.target.checked) S.selectedInvoices.add(id); else S.selectedInvoices.delete(id);
      }));
      tbody.querySelectorAll('[data-view-inv]').forEach(b => b.addEventListener('click', () => this.viewInvoice(parseInt(b.dataset.viewInv))));
      tbody.querySelectorAll('[data-del-inv]').forEach(b => b.addEventListener('click', () => this.deleteInvoice(parseInt(b.dataset.delInv))));
    } catch (e) { this.toast(e.message, 'error'); }
  },

  calcSelected() {
    if (!S.selectedInvoices || !S.selectedInvoices.size) { this.toast('حدد الفواتير أولاً', 'warning'); return; }
    let total = 0, paid = 0, rem = 0;
    for (const id of S.selectedInvoices) {
      const inv = S._customerInvoiceMap?.get(id);
      if (!inv) continue;
      const sign = inv.type === 'return' ? -1 : 1;
      if (inv.type === 'combined') continue;
      total += sign * (parseFloat(inv.total) || 0);
      paid += sign * (parseFloat(inv.paid) || 0);
      rem += sign * (parseFloat(inv.remaining) || 0);
    }
    document.getElementById('calcCount').textContent = S.selectedInvoices.size;
    document.getElementById('calcTotal').textContent = Util.money(total);
    document.getElementById('calcPaid').textContent = Util.money(paid);
    document.getElementById('calcRemaining').textContent = Util.money(rem);
    document.getElementById('calcResult').style.display = 'block';
    this.toast(`تم تجميع ${S.selectedInvoices.size} فاتورة`);
  },


  openCustomerModal(id) {
    const m = document.getElementById('customerModal');
    if (id) {
      const c = S.customerCache.get(id); if (!c) return;
      document.getElementById('customerModalTitle').textContent = 'تعديل عميل';
      document.getElementById('customerId').value = c.id;
      document.getElementById('customerName').value = c.name || '';
      document.getElementById('customerPhone').value = c.phone || '';
      document.getElementById('customerNotes').value = c.notes || '';
    } else {
      document.getElementById('customerModalTitle').textContent = 'عميل جديد';
      document.getElementById('customerId').value = '';
      document.getElementById('customerName').value = '';
      document.getElementById('customerPhone').value = '';
      document.getElementById('customerNotes').value = '';
    }
    m.classList.add('active');
    setTimeout(() => document.getElementById('customerName').focus(), 50);
  },

  async saveCustomer() {
    const id = document.getElementById('customerId').value;
    const name = document.getElementById('customerName').value.trim();
    if (!name) { this.toast('أدخل اسم العميل', 'error'); return; }
    try {
      const r = await API.post('/api/customers', {
        id: id || undefined,
        name,
        phone: document.getElementById('customerPhone').value.trim(),
        notes: document.getElementById('customerNotes').value.trim(),
      });
      this.toast(id ? 'تم تعديل العميل' : 'تم إضافة العميل');
      this.closeModal('customerModal');
      if (S.currentPage === 'customers') await this.loadCustomersPage();
      else if (S.currentPage === 'pos') {
        const c = { id: r.id, name, phone: document.getElementById('customerPhone').value.trim() };
        S.customerCache.set(c.id, c);
        this.selectCustomer(c.id);
      }
    } catch (e) { this.toast(e.message, 'error'); }
  },

  async deleteCustomer(id) {
    const c = S.customerCache.get(id);
    if (!await this.confirm('حذف عميل', `حذف "${c?.name || ''}"؟ لن يسمح النظام بالحذف إذا كان له تاريخ مالي.`)) return;
    try {
      await API.delete(`/api/customers/${id}`);
      S.customerCache.delete(id);
      this.toast('تم الحذف');
      if (S.currentPage === 'customers') await this.loadCustomersPage();
    } catch (e) { this.toast(e.message, 'error'); }
  },
};
