import { S } from '../core/state.js';
import { API } from '../core/api.js';
import { Util } from '../core/util.js';

const PERMISSION_LABELS = {
  pos_view: 'فتح نقطة البيع', invoice_create: 'إنشاء فواتير', invoice_view: 'عرض كل الفواتير', invoice_view_own: 'عرض فواتيره', invoice_collect: 'تحصيل دفعات', invoice_edit: 'المرتجعات والتعديل', invoice_delete: 'حذف الفواتير',
  product_view: 'عرض المنتجات', product_save: 'إضافة وتعديل المنتجات', product_delete: 'حذف المنتجات', product_import: 'استيراد وتحديث الأسعار', product_export: 'تصدير المنتجات',
  customer_view: 'عرض العملاء', customer_create: 'إضافة عميل', customer_save: 'تعديل العملاء', customer_delete: 'حذف العملاء', customer_export: 'تصدير العملاء',
  category_view: 'عرض الأقسام', category_save: 'تعديل الأقسام', category_delete: 'حذف الأقسام', supplier_view: 'عرض الموردين', supplier_save: 'تعديل الموردين', supplier_delete: 'حذف الموردين', supplier_export: 'تصدير الموردين',
  user_view: 'عرض المستخدمين', user_save: 'إدارة المستخدمين', delete_user: 'تعطيل المستخدمين', user_revoke_sessions: 'طرد الجلسات', settings_save: 'تعديل الإعدادات', backup_create: 'إنشاء نسخة احتياطية', backup_restore: 'استعادة نسخة احتياطية',
  report_dashboard: 'لوحة التقارير', report_low_stock: 'مخزون منخفض', report_profit: 'تقارير الأرباح', report_customer_debts: 'تقارير الديون', audit_view: 'عرض سجل العمليات', audit_clear: 'مسح سجل العمليات', clear_data: 'مسح البيانات',
};
function formatExpiry(value) { if (!value) return 'بدون مدة'; const d = new Date(value); return Number.isNaN(d.getTime()) ? value : d.toLocaleString('ar-EG', { dateStyle: 'medium', timeStyle: 'short' }); }
function datetimeLocalValue(value) { if (!value) return ''; const d = new Date(value); if (Number.isNaN(d.getTime())) return ''; const pad = n => String(n).padStart(2, '0'); return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`; }

export const userMethods = {
  async loadUsersPage() {
    try {
      const [users, permissionInfo] = await Promise.all([API.get('/api/users', { dedupe: false }), S.user?.is_owner ? API.get('/api/auth/permissions', { dedupe: false }).catch(() => null) : Promise.resolve(null)]);
      S._usersCache = users; if (permissionInfo?.all_roles) S._rolePermissions = permissionInfo.all_roles;
      const tbody = document.getElementById('usersTable');
      tbody.innerHTML = users.map(u => {
        const expired = u.expires_at && new Date(u.expires_at).getTime() <= Date.now();
        const status = !u.active ? '<span class="badge badge-danger">معطل</span>' : expired ? '<span class="badge badge-danger">منتهي</span>' : '<span class="badge badge-success">نشط</span>';
        const ownerBadge = u.is_owner ? ' <span class="badge badge-warning">المالك الرئيسي</span>' : '';
        const canManage = S.user?.is_owner || (u.role !== 'admin' && u.id !== S.user?.id);
        return `<tr><td><strong>${Util.esc(u.name)}</strong>${ownerBadge}</td><td>${Util.esc(u.login)}</td><td><span class="badge ${u.role === 'admin' ? 'badge-warning' : u.role === 'manager' ? 'badge-info' : 'badge-success'}">${u.role === 'admin' ? 'مدير' : u.role === 'manager' ? 'مدير فرع' : 'كاشير'}</span></td><td>${status}</td><td>${Util.esc(formatExpiry(u.expires_at))}</td><td class="user-actions">${canManage || u.id === S.user?.id ? `<button class="btn btn-sm btn-secondary" data-edit-user="${u.id}">تعديل</button>` : ''}${u.id !== S.user?.id && !u.is_owner && (S.user?.permissions || []).includes('user_revoke_sessions') ? `<button class="btn btn-sm btn-warning" data-kick-user="${u.id}">طرد الجلسات</button>` : ''}${u.id !== S.user?.id && !u.is_owner && (S.user?.permissions || []).includes('delete_user') ? `<button class="btn btn-sm btn-danger" data-del-user="${u.id}">تعطيل</button>` : ''}</td></tr>`;
      }).join('');
      tbody.querySelectorAll('[data-edit-user]').forEach(b => b.addEventListener('click', () => this.openUserModal(parseInt(b.dataset.editUser))));
      tbody.querySelectorAll('[data-kick-user]').forEach(b => b.addEventListener('click', () => this.revokeUserSessions(parseInt(b.dataset.kickUser))));
      tbody.querySelectorAll('[data-del-user]').forEach(b => b.addEventListener('click', () => this.deleteUser(parseInt(b.dataset.delUser))));
    } catch (e) { this.toast(e.message, 'error'); }
  },
  renderUserPermissions(selected = []) {
    const group = document.getElementById('userPermissionsGroup'); const grid = document.getElementById('userPermissionsGrid'); if (!group || !grid) return;
    group.style.display = S.user?.is_owner ? '' : 'none'; if (!S.user?.is_owner) return; const selectedSet = new Set(selected || []);
    grid.innerHTML = Object.entries(PERMISSION_LABELS).map(([key,label]) => `<label class="permission-item"><input type="checkbox" data-user-permission="${key}" ${selectedSet.has(key) ? 'checked' : ''}> <span>${Util.esc(label)}</span></label>`).join('');
  },
  onUserRoleChange() { if (!S.user?.is_owner) return; const role = document.getElementById('userRole').value; this.renderUserPermissions(S._rolePermissions?.[role] || []); },
  openUserModal(id) {
    const m = document.getElementById('userModal'); const users = S._usersCache || []; const u = id ? users.find(x => x.id === id) : null;
    if (id && !u) { this.toast('تعذر العثور على المستخدم', 'error'); return; }
    document.getElementById('userModalTitle').textContent = u ? 'تعديل مستخدم' : 'مستخدم جديد'; document.getElementById('userId').value = u?.id || ''; document.getElementById('userName').value = u?.name || ''; document.getElementById('userLogin').value = u?.login || ''; document.getElementById('userPassword').value = ''; document.getElementById('userRole').value = u?.role || 'cashier'; document.getElementById('userActive').checked = u ? !!u.active : true; document.getElementById('userExpiresAt').value = datetimeLocalValue(u?.expires_at);
    const roleSelect = document.getElementById('userRole'); const ownerEditing = !!u?.is_owner; roleSelect.disabled = ownerEditing || (!S.user?.is_owner && u?.role === 'admin'); document.getElementById('userActive').disabled = ownerEditing; document.getElementById('userExpiresAt').disabled = ownerEditing;
    const selected = u ? (u.permissions ?? u.effective_permissions ?? []) : (S._rolePermissions?.cashier || []); this.renderUserPermissions(ownerEditing ? [] : selected); if (ownerEditing) document.getElementById('userPermissionsGroup').style.display = 'none'; m.classList.add('active');
  },
  async saveUser() {
    const id = document.getElementById('userId').value; const name = document.getElementById('userName').value.trim(); const login = document.getElementById('userLogin').value.trim(); const password = document.getElementById('userPassword').value; const role = document.getElementById('userRole').value; const expiresRaw = document.getElementById('userExpiresAt').value;
    if (!name || !login) { this.toast('الاسم واسم الدخول مطلوبان', 'error'); return; }
    const payload = { id: id ? parseInt(id) : undefined, name, login, role, active: document.getElementById('userActive').checked, expires_at: expiresRaw ? new Date(expiresRaw).toISOString() : null, password: password || undefined };
    if (S.user?.is_owner && document.getElementById('userPermissionsGroup').style.display !== 'none') payload.permissions = Array.from(document.querySelectorAll('[data-user-permission]:checked')).map(x => x.dataset.userPermission);
    try { await API.post('/api/users', payload); this.toast('تم حفظ المستخدم وتطبيق الصلاحيات'); this.closeModal('userModal'); await this.loadUsersPage(); } catch (e) { this.toast(e.message, 'error'); }
  },
  async revokeUserSessions(id) { if (!await this.confirm('طرد المستخدم', 'سيتم إلغاء كل جلساته الحالية وسيحتاج لتسجيل الدخول من جديد. متابعة؟')) return; try { await API.post(`/api/users/${id}/revoke-sessions`, {}); this.toast('تم طرد المستخدم من الجلسات الحالية'); } catch (e) { this.toast(e.message, 'error'); } },
  async deleteUser(id) { if (!await this.confirm('تعطيل المستخدم', 'سيتم تعطيل الحساب وطرده من كل الجلسات. متابعة؟')) return; try { await API.delete(`/api/users/${id}`); this.toast('تم تعطيل الحساب'); await this.loadUsersPage(); } catch (e) { this.toast(e.message, 'error'); } },
  async changeCredentials() {
    const login = document.getElementById('newLogin').value.trim(); const pass = document.getElementById('newPass').value; const currentPass = document.getElementById('currentPass').value;
    if (!login && !pass) { this.toast('أدخل قيمة جديدة', 'warning'); return; }
    try { const r = await API.post('/api/auth/change-credentials', { login: login || undefined, password: pass || undefined, current_password: currentPass || undefined }); S.user = r.user; document.getElementById('curLogin').value = r.user.login; document.getElementById('currentUserName').textContent = r.user.name; document.getElementById('newLogin').value = ''; document.getElementById('newPass').value = ''; document.getElementById('currentPass').value = ''; this.toast('تم التحديث وإلغاء الجلسات القديمة'); } catch (e) { this.toast(e.message, 'error'); }
  },
};
