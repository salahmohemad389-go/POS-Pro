import { S } from '../core/state.js';
import { API } from '../core/api.js';
import { Util } from '../core/util.js';

export const reportMethods = {
  async loadReport() {
    const type = document.getElementById('reportType').value;
    const from = document.getElementById('reportFrom').value;
    const to = document.getElementById('reportTo').value;
    const el = document.getElementById('reportContent');
    el.innerHTML = '<div class="empty-cart">جاري التحميل...</div>';
    try {
      if (type === 'dashboard') {
        const d = await API.get('/api/reports/dashboard');
        el.innerHTML = `
          <div class="report-card">
            <div class="report-stats">
              <div class="report-stat blue"><span>مبيعات اليوم</span><strong>${Util.money(d.today_sales)}</strong></div>
              <div class="report-stat"><span>المنتجات</span><strong>${d.products_count}</strong></div>
              <div class="report-stat"><span>العملاء</span><strong>${d.customers_count}</strong></div>
              <div class="report-stat red"><span>إجمالي الديون</span><strong>${Util.money(d.total_debts)}</strong></div>
            </div>
          </div>
          <div class="report-card">
            <h3>📈 مبيعات آخر 7 أيام</h3>
            <div class="chart-bars">
              ${(() => {
                const max = Math.max(1, ...d.sales_chart.map(c => c.total));
                return d.sales_chart.map(c => {
                  const h = Math.max(4, (c.total / max) * 140);
                  return `<div class="chart-bar-wrap"><div class="chart-bar" style="height:${h}px" title="${Util.money(c.total)}"></div><span class="chart-bar-label">${c.date.slice(5)}</span></div>`;
                }).join('');
              })()}
            </div>
          </div>
          <div class="report-card">
            <h3>🏆 أعلى المنتجات مبيعاً</h3>
            <table><thead><tr><th>المنتج</th><th>الإيرادات</th></tr></thead>
            <tbody>${d.top_products.map(p => `<tr><td>${Util.esc(p.product_name)}</td><td><strong>${Util.money(p.revenue)}</strong></td></tr>`).join('') || '<tr><td colspan="2" style="text-align:center">لا توجد بيانات</td></tr>'}</tbody>
            </table>
          </div>`;
      } else if (type === 'profit') {
        const params = new URLSearchParams();
        if (from) params.set('date_from', from);
        if (to) params.set('date_to', to);
        const d = await API.get(`/api/reports/profit?${params}`);
        el.innerHTML = `
          <div class="report-card">
            <h3>💰 تقرير الأرباح</h3>
            <div class="report-stats">
              <div class="report-stat blue"><span>إجمالي المبيعات</span><strong>${Util.money(d.total_revenue)}</strong></div>
              <div class="report-stat red"><span>إجمالي التكلفة</span><strong>${Util.money(d.total_cost)}</strong></div>
              <div class="report-stat green"><span>صافي الربح</span><strong>${Util.money(d.profit)}</strong></div>
              <div class="report-stat"><span>هامش الربح</span><strong>${d.profit_margin}%</strong></div>
            </div>
            <div>عدد الفواتير: <strong>${d.invoices_count}</strong></div>
          </div>`;
      } else if (type === 'low-stock') {
        const items = await API.get('/api/reports/low-stock');
        el.innerHTML = `
          <div class="report-card">
            <h3>⚠️ المنتجات منخفضة المخزون (≤ 5)</h3>
            <table><thead><tr><th>المنتج</th><th>المخزون</th><th>السعر</th><th>الباركود</th></tr></thead>
            <tbody>${items.map(p => `<tr><td>${Util.esc(p.name)}</td><td style="color:var(--err);font-weight:700">${p.stock}</td><td>${Util.money(p.price)}</td><td style="font-family:monospace;font-size:12px">${Util.esc(p.barcode || '-')}</td></tr>`).join('') || '<tr><td colspan="4" style="text-align:center">لا توجد منتجات منخفضة</td></tr>'}</tbody></table>
          </div>`;
      } else if (type === 'debts') {
        const items = await API.get('/api/reports/customer-debts');
        el.innerHTML = `
          <div class="report-card">
            <h3>💸 ديون العملاء</h3>
            <table><thead><tr><th>العميل</th><th>الهاتف</th><th>الديون</th></tr></thead>
            <tbody>${items.map(c => `<tr><td><strong>${Util.esc(c.name)}</strong></td><td>${Util.esc(c.phone || '-')}</td><td style="color:var(--err);font-weight:700">${Util.money(c.balance)}</td></tr>`).join('') || '<tr><td colspan="3" style="text-align:center">لا توجد ديون</td></tr>'}</tbody></table>
          </div>`;
      }
    } catch (e) {
      el.innerHTML = `<div class="empty-cart" style="color:var(--err)">${Util.esc(e.message)}</div>`;
    }
  },
};
