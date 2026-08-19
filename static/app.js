/* ═══════════════════════════════════════════════════
   POS Pro – Frontend
   Talks to FastAPI backend, uses event listeners,
   Map() caching, pagination, and clean architecture.
   ═══════════════════════════════════════════════════ */
'use strict';

import { S } from './js/core/state.js';
import { API, setUnauthorizedHandler } from './js/core/api.js';
import { Util } from './js/core/util.js';
import { posMethods } from './js/pages/pos.js';
import { productMethods } from './js/pages/products.js';
import { supplierMethods } from './js/pages/suppliers.js';
import { customerMethods } from './js/pages/customers.js';
import { invoiceMethods } from './js/pages/invoices.js';
import { reportMethods } from './js/pages/reports.js';
import { userMethods } from './js/pages/users.js';
import { settingsMethods } from './js/pages/settings.js';
import { auditMethods } from './js/pages/audit.js';
import { quickAddMethods } from './js/pages/quick_add.js';
import { upgradeMethods } from './js/upgrade_methods.js';

const App = {
  async init() {
    this.bindEvents();
    await this.loadPublicBranding();
    try {
      const me = await API.get('/api/auth/me', { dedupe: false });
      S.user = me;
      await this.loadSettings();
      this.showApp();
    } catch {
      this.showLogin();
    }
  },

  showLogin() {
    this.applyBranding();
    document.getElementById('loginScreen').style.display = 'flex';
    document.getElementById('app').style.display = 'none';
    document.getElementById('loginUser').focus();
  },

  showApp() {
    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('app').style.display = 'flex';
    document.getElementById('currentUserName').textContent = S.user.name;
    document.getElementById('currentUserRole').textContent = S.user.role === 'admin' ? 'مدير' : S.user.role === 'manager' ? 'مدير فرع' : 'كاشير';
    this.applyBranding();
    document.getElementById('curLogin').value = S.user.login;
    this.applyPermissions();
    const savedTheme = localStorage.getItem('pos_theme');
    if (savedTheme === 'dark') this.applyTheme('dark');
    else if (S.settings.theme === 'dark') this.applyTheme('dark');
    const firstAllowedPage = document.querySelector('.nav-item.show')?.dataset.page || 'pos';
    this.nav(firstAllowedPage);
  },

  applyPermissions() {
    const perms = new Set(S.user?.permissions || []);
    const can = p => perms.has(p);
    const featureReports = S.settings?.feature_reports_enabled !== false;
    const featureSuppliers = S.settings?.feature_suppliers_enabled !== false;
    const navPerms = {
      pos: can('pos_view'), products: can('product_view'), customers: can('customer_view'),
      invoices: can('invoice_view') || can('invoice_view_own'), suppliers: featureSuppliers && can('supplier_view'),
      reports: featureReports && (can('report_dashboard') || can('report_low_stock') || can('report_profit') || can('report_customer_debts')),
      users: can('user_view'), settings: can('settings_save'), audit: can('audit_view'),
    };
    Object.entries(navPerms).forEach(([page, visible]) => {
      const el = document.querySelector(`.nav-item[data-page="${page}"]`);
      if (el) el.classList.toggle('show', !!visible);
    });
    document.querySelectorAll('.admin-only').forEach(el => { el.style.display = S.user?.is_owner ? '' : 'none'; });
    document.querySelectorAll('.owner-only').forEach(el => { el.style.display = S.user?.is_owner ? '' : 'none'; });
    const backup = document.getElementById('backupBtn'); if (backup) backup.style.display = can('backup_create') ? '' : 'none';
    const addUser = document.getElementById('addUserBtn'); if (addUser) addUser.style.display = can('user_save') ? '' : 'none';
    const createBackup = document.getElementById('createBackupBtn'); if (createBackup) createBackup.style.display = can('backup_create') ? '' : 'none';
    const clearAudit = document.getElementById('clearAuditBtn'); if (clearAudit) clearAudit.style.display = can('audit_clear') ? '' : 'none';
    if (!navPerms[S.currentPage] && S.currentPage !== 'pos') {
      S.currentPage = Object.entries(navPerms).find(([, v]) => v)?.[0] || 'pos';
    }
  },

  bindEvents() {
    document.getElementById('loginBtn').addEventListener('click', () => this.login());
    document.getElementById('loginUser').addEventListener('keydown', e => { if (e.key === 'Enter') document.getElementById('loginPass').focus(); });
    document.getElementById('loginPass').addEventListener('keydown', e => { if (e.key === 'Enter') this.login(); });
    document.getElementById('toggleLoginPass').addEventListener('click', () => {
      const input = document.getElementById('loginPass'); const btn = document.getElementById('toggleLoginPass');
      const showing = input.type === 'text'; input.type = showing ? 'password' : 'text';
      btn.textContent = showing ? '👁' : '🙈'; btn.title = showing ? 'إظهار كلمة المرور' : 'إخفاء كلمة المرور';
    });
    document.querySelectorAll('.nav-item').forEach(el => el.addEventListener('click', () => this.nav(el.dataset.page)));
    document.getElementById('menuToggle').addEventListener('click', () => document.getElementById('sidebar').classList.toggle('open'));
    document.getElementById('logoutBtn').addEventListener('click', () => this.logout());
    document.getElementById('backupBtn').addEventListener('click', () => this.backup());
    document.addEventListener('click', e => { const t = e.target; if (t.dataset.close) this.closeModal(t.dataset.close); if (t.classList && t.classList.contains('modal')) t.classList.remove('active'); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') document.querySelectorAll('.modal.active').forEach(m => m.classList.remove('active')); });

    const posSearch = document.getElementById('posSearch'); let posLastKeyTime = 0;
    posSearch.addEventListener('keydown', e => {
      const now = Date.now(); const timeSinceLastKey = now - posLastKeyTime; posLastKeyTime = now;
      if (e.key === 'Enter') { e.preventDefault(); this.onPOSSearchEnter(); posLastKeyTime = 0; return; }
      if (timeSinceLastKey > 100) { clearTimeout(this._posSearchTimer); this._posSearchTimer = setTimeout(() => { S.pos.q = posSearch.value.trim(); S.pos.page = 1; this.loadPOSProducts(); }, 250); }
    });
    document.getElementById('cartDiscount').addEventListener('input', () => this.recalcCart());
    document.querySelectorAll('.cart-tab').forEach(t => t.addEventListener('click', () => this.setInvoiceType(t.dataset.type)));
    document.querySelectorAll('.cart-actions [data-method]').forEach(b => b.addEventListener('click', () => this.checkout(b.dataset.method)));
    document.getElementById('partialBtn').addEventListener('click', () => this.openPartial());
    document.getElementById('clearCartBtn').addEventListener('click', () => this.clearCart());
    document.getElementById('posReturnBtn').addEventListener('click', () => this.openReturnFromPOS());
    document.getElementById('clearCustomerBtn').addEventListener('click', () => this.clearCustomer());
    document.getElementById('openCustAccountBtn').addEventListener('click', () => { if (S.cartCustomer) { this.showPage('customers'); setTimeout(() => this.viewCustomer(S.cartCustomer), 50); } });
    const cartEl = document.getElementById('cartItems');
    if (cartEl && !cartEl._delegated) {
      cartEl._delegated = true;
      cartEl.addEventListener('click', e => { const btn = e.target.closest('button[data-act]'); if (!btn) return; const idx = parseInt(btn.dataset.idx); const act = btn.dataset.act; if (act === 'inc') this.cartQty(idx, 1); else if (act === 'dec') this.cartQty(idx, -1); else if (act === 'rm') this.cartRemove(idx); });
      cartEl.addEventListener('change', e => { const input = e.target.closest('input.qty-input'); if (!input) return; this.setCartQty(parseInt(input.dataset.idx), input.value); });
    }
    document.getElementById('customerSearch').addEventListener('input', Util.debounce(e => this.searchCustomer(e.target.value), 200));
    document.getElementById('addCustomerBtn').addEventListener('click', () => this.openCustomerModal());

    document.getElementById('addProductBtn').addEventListener('click', () => this.openProductModal());
    document.getElementById('productsSearch').addEventListener('input', Util.debounce(e => { S.productsPage.q = e.target.value.trim(); S.productsPage.page = 1; this.loadProductsPage(); }, 200));
    document.getElementById('saveProductBtn').addEventListener('click', () => this.saveProduct());
    document.getElementById('productCategory').addEventListener('change', () => this.updateProductSubCategories());
    document.getElementById('importExcelInput').addEventListener('change', e => this.importExcel(e.target));
    document.getElementById('updatePricesInput').addEventListener('change', e => this.updatePrices(e.target));
    this.bindDownloadLinks();
    document.getElementById('addCategoryBtn').addEventListener('click', () => this.openCategoryModal());
    document.getElementById('saveCategoryBtn').addEventListener('click', () => this.saveCategory());
    document.querySelectorAll('[data-pctab]').forEach(t => t.addEventListener('click', () => this.switchProductsTab(t.dataset.pctab)));

    document.getElementById('addCustomerPageBtn').addEventListener('click', () => this.openCustomerModal());
    document.getElementById('saveCustomerBtn').addEventListener('click', () => this.saveCustomer());
    document.getElementById('customersSearch').addEventListener('input', Util.debounce(e => { S.customersPage.q = e.target.value.trim(); S.customersPage.page = 1; this.loadCustomersPage(); }, 200));
    document.getElementById('backToCustomersBtn').addEventListener('click', () => this.backToCustomers());
    document.getElementById('calcModeBtn').addEventListener('click', () => this.calcSelected());
    document.getElementById('cdCombinedInvoiceBtn').addEventListener('click', () => this.openCombinedInvoiceOptions(Array.from(S.selectedInvoices || [])));
    document.getElementById('calcDownloadCombinedBtn').addEventListener('click', () => this.openCombinedInvoiceOptions(Array.from(S.selectedInvoices || [])));
    document.getElementById('cdStatementBtn').addEventListener('click', () => this.openCustomerStatement(S._currentCustomerId));
    document.getElementById('printStatementBtn').addEventListener('click', () => this.printCustomerStatement());
    document.getElementById('executeCombinedInvoiceBtn').addEventListener('click', () => this.executeCombinedInvoice());

    document.getElementById('invoicesSearch').addEventListener('input', Util.debounce(e => { S.invoices.q = e.target.value.trim(); S.invoices.page = 1; this.clearInvoicesSelection(); this.loadInvoicesPage(); }, 200));
    document.querySelectorAll('.filter-tab[data-filter]').forEach(t => t.addEventListener('click', () => this.filterInvoices(t.dataset.filter)));
    document.getElementById('invoicesSelectAll').addEventListener('change', e => this.toggleSelectAllInvoices(e.target.checked));
    document.getElementById('invoicesCombinedPdfBtn').addEventListener('click', () => this.openCombinedInvoiceOptions(Array.from(S.invoices.selected)));
    document.getElementById('invoicesClearSelBtn').addEventListener('click', () => this.clearInvoicesSelection());

    document.getElementById('addSupplierBtn').addEventListener('click', () => this.openSupplierModal());
    document.getElementById('saveSupplierBtn').addEventListener('click', () => this.saveSupplier());
    document.getElementById('suppliersSearch').addEventListener('input', Util.debounce(e => { S.suppliersPage.q = e.target.value.trim(); S.suppliersPage.page = 1; this.loadSuppliersPage(); }, 200));
    document.getElementById('loadReportBtn').addEventListener('click', () => this.loadReport());
    document.getElementById('reportType').addEventListener('change', () => this.loadReport());
    document.getElementById('addUserBtn').addEventListener('click', () => this.openUserModal());
    document.getElementById('saveUserBtn').addEventListener('click', () => this.saveUser());
    document.getElementById('userRole').addEventListener('change', () => this.onUserRoleChange());
    document.getElementById('changeCredsBtn').addEventListener('click', () => this.changeCredentials());

    document.getElementById('saveSettingsBtn').addEventListener('click', () => this.saveSettings());
    document.getElementById('setLogoInput').addEventListener('change', e => this.previewLogo(e.target));
    document.getElementById('resetQuickQtyBtn').addEventListener('click', () => { document.getElementById('setQuickQty').value = '1,5,10,20,30,50,100'; });
    document.getElementById('createBackupBtn').addEventListener('click', () => this.backup());
    document.getElementById('settingsChangeCredsBtn').addEventListener('click', () => this.changeCredentialsFromSettings());
    document.getElementById('clearAuditBtn').addEventListener('click', () => this.clearAudit());
    document.getElementById('saveQuickAddBtn').addEventListener('click', () => this.saveQuickAdd());
    document.getElementById('ptPaid').addEventListener('input', () => { const paid = parseFloat(document.getElementById('ptPaid').value) || 0; const total = parseFloat(document.getElementById('ptTotal').value) || 0; document.getElementById('ptRemain').value = Math.max(0, total - paid).toFixed(2); });
    document.getElementById('confirmPartialBtn').addEventListener('click', () => this.confirmPartial());
    document.getElementById('auditSearchBtn').addEventListener('click', () => this.loadAuditPage());
    document.getElementById('auditResetBtn').addEventListener('click', () => this.resetAuditSearch());
    document.getElementById('auditSearch').addEventListener('keydown', e => { if (e.key === 'Enter') this.loadAuditPage(); });
    document.getElementById('previewInvoiceBtn').addEventListener('click', () => this.previewInvoice());
    document.getElementById('printInvoiceBtn').addEventListener('click', () => this.printCurrent());
    document.getElementById('pdfPreviewPrintBtn').addEventListener('click', () => this.printPdfPreview());
    document.getElementById('themeToggle').addEventListener('click', () => this.toggleTheme());
    document.getElementById('collectInvoiceBtn').addEventListener('click', () => this.openCollect());
    document.getElementById('confirmCollectBtn').addEventListener('click', () => this.confirmCollect());
    document.getElementById('returnInvoiceBtn').addEventListener('click', () => this.openReturnInvoice());
    document.getElementById('confirmReturnInvoiceBtn').addEventListener('click', () => this.confirmReturnInvoice());
    document.getElementById('returnPaymentMethod').addEventListener('change', () => this.updateReturnPaymentUI());
    setInterval(() => this.pingServer(), 60000);
  },

  async pingServer() { try { await API.get('/api/auth/me'); this.setServerStatus(true); } catch { this.setServerStatus(false); } },
  setServerStatus(ok) { const dot = document.getElementById('serverStatus'); const text = document.getElementById('serverStatusText'); if (!dot) return; dot.style.background = ok ? 'var(--ok)' : 'var(--err)'; text.textContent = ok ? 'متصل' : 'غير متصل'; },
  async login() {
    const user = document.getElementById('loginUser').value.trim(); const pass = document.getElementById('loginPass').value; const err = document.getElementById('loginError');
    if (!user || !pass) { err.textContent = 'أدخل البيانات'; err.style.display = 'block'; return; }
    try { const r = await API.post('/api/auth/login', { login: user, password: pass }); S.user = r.user; document.getElementById('loginPass').value = ''; err.style.display = 'none'; await this.loadSettings(); this.showApp(); this.toast('مرحباً ' + S.user.name); }
    catch (e) { err.textContent = e.message; err.style.display = 'block'; document.getElementById('loginPass').value = ''; document.getElementById('loginPass').focus(); }
  },
  async logout() { if (!await this.confirm('تسجيل الخروج', 'هل تريد تسجيل الخروج؟')) return; try { await API.post('/api/auth/logout', {}); } catch {} S.user = null; this.clearState(); this.showLogin(); },
  clearState() { S.cart = []; S.cartCustomer = null; S.productCache.clear(); S.categoryCache.clear(); S.customerCache.clear(); S.supplierCache.clear(); S.categoryChildren.clear(); },
  toggleTheme() { const isDark = document.body.classList.toggle('dark-mode'); const btn = document.getElementById('themeToggle'); btn.textContent = isDark ? '☀️' : '🌙'; localStorage.setItem('pos_theme', isDark ? 'dark' : 'light'); },
  applyTheme(theme) { if (theme === 'dark') { document.body.classList.add('dark-mode'); const btn = document.getElementById('themeToggle'); if (btn) btn.textContent = '☀️'; } },

  ...posMethods, ...productMethods, ...supplierMethods, ...customerMethods, ...invoiceMethods,
  ...reportMethods, ...userMethods, ...settingsMethods, ...auditMethods, ...quickAddMethods,
  ...upgradeMethods,
};

setUnauthorizedHandler(() => { App.showLogin(); App.toast('انتهت الجلسة، سجل دخول مرة أخرى', 'warning'); });
window.addEventListener('DOMContentLoaded', () => App.init());
