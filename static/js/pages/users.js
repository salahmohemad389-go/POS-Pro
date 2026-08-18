import { S } from '../core/state.js';
import { API } from '../core/api.js';
import { Util } from '../core/util.js';

export const userMethods = {
  async loadUsersPage() {
    try {
      const users = await API.get('/api/users');
      const tbody = document.getElementById('usersTable');
      tbody.innerHTML = users.map(u => `
        <tr>
          <td><strong>${Util.esc(u.name)}</strong></td>
          <td>${Util.esc(u.login)}</td>
          <td><span class="badge ${u.role === 'admin' ? 'badge-warning' : u.role === 'manager' ? 'badge-info' : 'badge-success'}">${u.role === 'admin' ? 'مدير' : u.role === 'manager' ? 'مدير فرع' : 'كاشير'}</span></td>
          <td>${u.active ? '<span class="badge badge-success">نشط</span>' : '<span class="badge badge-danger">معطل</span>'}</td>
          <td>
            <button class="btn btn-sm btn-secondary" data-edit-user="${u.id}">تعديل</button>
            ${u.id !== S.user.id ? `<button class="btn btn-sm btn-danger" data-del-user="${u.id}">حذف</button>` : ''}
          </td>
        </tr>`).join('');
      tbody.querySelectorAll('[data-edit-user]').forEach(b => b.addEventListener('click', () => this.openUserModal(parseInt(b.dataset.editUser))));
      tbody.querySelectorAll('[data-del-user]').forEach(b => b.addEventListener('click', () => this.deleteUser(parseInt(b.dataset.delUser))));
    } catch (e) { this.toast(e.message, 'error'); }
  },

  openUserModal(id) {
    const m = document.getElementById('userModal');
    if (id) {
      API.get('/api/users').then(users => {
        const u = users.find(x => x.id === id); if (!u) return;
        document.getElementById('userModalTitle').textContent = 'تعديل مستخدم';
        document.getElementById('userId').value = u.id;
        document.getElementById('userName').value = u.name;
        document.getElementById('userLogin').value = u.login;
        document.getElementById('userPassword').value = '';
        document.getElementById('userRole').value = u.role;
        m.classList.add('active');
      });
    } else {
      document.getElementById('userModalTitle').textContent = 'مستخدم جديد';
      document.getElementById('userId').value = '';
      document.getElementById('userName').value = '';
      document.getElementById('userLogin').value = '';
      document.getElementById('userPassword').value = '';
      document.getElementById('userRole').value = 'cashier';
      m.classList.add('active');
    }
  },

  async saveUser() {
    const id = document.getElementById('userId').value;
    const name = document.getElementById('userName').value.trim();
    const login = document.getElementById('userLogin').value.trim();
    const password = document.getElementById('userPassword').value;
    const role = document.getElementById('userRole').value;
    if (!name || !login) { this.toast('الاسم واسم الدخول مطلوبان', 'error'); return; }
    try {
      await API.post('/api/users', {
        id: id || undefined,
        name, login, role,
        password: password || undefined,
      });
      this.toast('تم الحفظ');
      this.closeModal('userModal');
      await this.loadUsersPage();
    } catch (e) { this.toast(e.message, 'error'); }
  },

  async deleteUser(id) {
    if (!await this.confirm('حذف مستخدم', 'حذف هذا المستخدم؟')) return;
    try {
      await API.delete(`/api/users/${id}`);
      this.toast('تم الحذف');
      await this.loadUsersPage();
    } catch (e) { this.toast(e.message, 'error'); }
  },

  async changeCredentials() {
    const login = document.getElementById('newLogin').value.trim();
    const pass = document.getElementById('newPass').value;
    const currentPass = document.getElementById('currentPass').value;
    if (!login && !pass) { this.toast('أدخل قيمة جديدة', 'warning'); return; }
    try {
      const r = await API.post('/api/auth/change-credentials', { login: login || undefined, password: pass || undefined, current_password: currentPass || undefined });
      S.user = r.user;
      document.getElementById('curLogin').value = r.user.login;
      document.getElementById('currentUserName').textContent = r.user.name;
      document.getElementById('newLogin').value = '';
      document.getElementById('newPass').value = '';
      document.getElementById('currentPass').value = '';
      this.toast('تم التحديث');
    } catch (e) { this.toast(e.message, 'error'); }
  },
};
