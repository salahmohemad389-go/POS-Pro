import { S } from '../core/state.js';
import { API } from '../core/api.js';
import { Util } from '../core/util.js';

export const auditMethods = {
  async loadAuditPage() {
    try {
      // Load action list for filter dropdown
      if (!S.auditActions) {
        try {
          S.auditActions = await API.get('/api/audit/actions');
          const sel = document.getElementById('auditActionFilter');
          sel.innerHTML = '<option value="">كل العمليات</option>' +
            S.auditActions.map(a => `<option value="${a}">${Util.esc(a)}</option>`).join('');
        } catch {}
      }
      const params = new URLSearchParams({ page: S.audit.page || 1, limit: 100 });
      const q = document.getElementById('auditSearch').value.trim();
      const action = document.getElementById('auditActionFilter').value;
      const from = document.getElementById('auditDateFrom').value;
      const to = document.getElementById('auditDateTo').value;
      if (q) params.set('q', q);
      if (action) params.set('action', action);
      if (from) params.set('date_from', from);
      if (to) params.set('date_to', to);
      const data = await API.get(`/api/audit?${params}`);
      const tbody = document.getElementById('auditTable');
      if (!data.items.length) { tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--g400);padding:30px">لا توجد سجلات</td></tr>'; return; }
      tbody.innerHTML = '';
      data.items.forEach(a => {
        const tr = Util.el('tr', {}, [
          Util.el('td', {}, [Util.date(a.created_at)]),
          Util.el('td', {}, [a.user_name || '-']),
          Util.el('td', {}, [Util.el('span', { class: 'badge badge-info' }, [a.action])]),
          Util.el('td', {}, [a.details || '']),
          Util.el('td', {}, [a.ip || '']),
        ]);
        tbody.appendChild(tr);
      });
    } catch (e) { this.toast(e.message, 'error'); }
  },

  resetAuditSearch() {
    document.getElementById('auditSearch').value = '';
    document.getElementById('auditActionFilter').value = '';
    document.getElementById('auditDateFrom').value = '';
    document.getElementById('auditDateTo').value = '';
    this.loadAuditPage();
  },

  async clearAudit() {
    if (!await this.confirm('مسح السجل', 'مسح كل سجلات العمليات؟')) return;
    try {
      await API.delete('/api/audit');
      this.toast('تم المسح');
      await this.loadAuditPage();
    } catch (e) { this.toast(e.message, 'error'); }
  },
};
