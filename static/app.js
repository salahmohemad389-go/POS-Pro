/* ═══════════════════════════════════════════════════
   POS Pro – Frontend
   Talks to FastAPI backend, uses event listeners,
   Map() caching, pagination, and clean architecture.
   ═══════════════════════════════════════════════════ */
'use strict';

/* ═══════════════════════════════════════════════════
   STATE + CACHE
   ═══════════════════════════════════════════════════ */
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

/* ═══════════════════════════════════════════════════
   APP
   ═══════════════════════════════════════════════════ */
const App = {
  /* ─── INIT ─── */
  async init() {
    this.bindEvents();
    try {
      const me = await API.get('/api/auth/me');
      S.user = me;
      await this.loadSettings();
      this.showApp();
    } catch {
      this.showLogin();
    }
  },

  showLogin() {
    document.getElementById('loginScreen').style.display = 'flex';
    document.getElementById('app').style.display = 'none';
    document.getElementById('loginUser').focus();
  },

  showApp() {
    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('app').style.display = 'flex';
    document.getElementById('currentUserName').textContent = S.user.name;
    document.getElementById('currentUserRole').textContent = S.user.role === 'admin' ? 'مدير' : S.user.role === 'manager' ? 'مدير فرع' : 'كاشير';
    document.getElementById('storeName').textContent = S.settings.store_name || 'POS';
    document.getElementById('curLogin').value = S.user.login;
    this.applyPermissions();
    // Apply saved theme
    const savedTheme = localStorage.getItem('pos_theme');
    if (savedTheme === 'dark') this.applyTheme('dark');
    else if (S.settings.theme === 'dark') this.applyTheme('dark');
    this.nav('pos');
  },

  applyPermissions() {
    const role = S.user.role;
    // Show nav items based on role
    const navPerms = {
      pos: ['admin', 'manager', 'cashier'],
      products: ['admin', 'manager'],
      customers: ['admin', 'manager', 'cashier'],
      invoices: ['admin', 'manager', 'cashier'],
      suppliers: ['admin', 'manager'],
      reports: ['admin', 'manager'],
      users: ['admin', 'manager'],
      settings: ['admin'],
      audit: ['admin', 'manager'],
    };
    Object.entries(navPerms).forEach(([page, roles]) => {
      const el = document.querySelector(`.nav-item[data-page="${page}"]`);
      if (el) el.classList.toggle('show', roles.includes(role));
    });
    // Admin-only elements
    document.querySelectorAll('.admin-only').forEach(el => {
      el.style.display = role === 'admin' ? '' : 'none';
    });
  },

  /* ─── EVENT BINDING ─── */
  bindEvents() {
    // Login
    document.getElementById('loginBtn').addEventListener('click', () => this.login());
    document.getElementById('loginUser').addEventListener('keydown', e => { if (e.key === 'Enter') document.getElementById('loginPass').focus(); });
    document.getElementById('loginPass').addEventListener('keydown', e => { if (e.key === 'Enter') this.login(); });

    // Nav
    document.querySelectorAll('.nav-item').forEach(el => {
      el.addEventListener('click', () => this.nav(el.dataset.page));
    });
    document.getElementById('menuToggle').addEventListener('click', () => document.getElementById('sidebar').classList.toggle('open'));
    document.getElementById('logoutBtn').addEventListener('click', () => this.logout());
    document.getElementById('backupBtn').addEventListener('click', () => this.backup());

    // Modal close (delegated)
    document.addEventListener('click', e => {
      const t = e.target;
      if (t.dataset.close) this.closeModal(t.dataset.close);
      if (t.classList && t.classList.contains('modal')) t.classList.remove('active');
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        document.querySelectorAll('.modal.active').forEach(m => m.classList.remove('active'));
      }
    });

    // POS
    const posSearch = document.getElementById('posSearch');
    // Smart barcode scanner detection:
    // - Track typing speed: barcode scanners type within ~50ms between keys
    // - After Enter (typical scanner terminator), trigger barcode lookup
    // - For manual typing (>150ms between keys), debounce name search
    let posLastKeyTime = 0;
    posSearch.addEventListener('keydown', e => {
      const now = Date.now();
      const timeSinceLastKey = now - posLastKeyTime;
      posLastKeyTime = now;
      if (e.key === 'Enter') {
        e.preventDefault();
        // Enter is the typical scanner terminator - always try barcode lookup
        this.onPOSSearchEnter();
        posLastKeyTime = 0;
        return;
      }
      // Manual typing: schedule a debounced name search ONLY if typing slowly
      if (timeSinceLastKey > 100) {
        // Looks like manual typing - debounce name search
        clearTimeout(this._posSearchTimer);
        this._posSearchTimer = setTimeout(() => {
          S.pos.q = posSearch.value.trim();
          S.pos.page = 1;
          this.loadPOSProducts();
        }, 250);
      }
      // Fast typing (scanner) - do nothing, wait for Enter
    });
    document.getElementById('cartDiscount').addEventListener('input', () => this.recalcCart());
    document.querySelectorAll('.cart-tab').forEach(t => t.addEventListener('click', () => this.setInvoiceType(t.dataset.type)));
    document.querySelectorAll('.cart-actions [data-method]').forEach(b => b.addEventListener('click', () => this.checkout(b.dataset.method)));
    document.getElementById('partialBtn').addEventListener('click', () => this.openPartial());
    document.getElementById('clearCartBtn').addEventListener('click', () => this.clearCart());
    document.getElementById('clearCustomerBtn').addEventListener('click', () => this.clearCustomer());
    document.getElementById('openCustAccountBtn').addEventListener('click', () => { if (S.cartCustomer) { this.showPage('customers'); setTimeout(() => this.viewCustomer(S.cartCustomer), 50); } });

    // Event delegation for cart (one listener for all rows)
    const cartEl = document.getElementById('cartItems');
    if (cartEl && !cartEl._delegated) {
      cartEl._delegated = true;
      cartEl.addEventListener('click', e => {
        const btn = e.target.closest('button[data-act]');
        if (!btn) return;
        const idx = parseInt(btn.dataset.idx);
        const act = btn.dataset.act;
        if (act === 'inc') this.cartQty(idx, 1);
        else if (act === 'dec') this.cartQty(idx, -1);
        else if (act === 'rm') this.cartRemove(idx);
      });
      cartEl.addEventListener('change', e => {
        const input = e.target.closest('input.qty-input');
        if (!input) return;
        const idx = parseInt(input.dataset.idx);
        this.setCartQty(idx, input.value);
      });
    }
    document.getElementById('customerSearch').addEventListener('input', Util.debounce(e => this.searchCustomer(e.target.value), 200));
    document.getElementById('addCustomerBtn').addEventListener('click', () => this.openCustomerModal());

    // Products
    document.getElementById('addProductBtn').addEventListener('click', () => this.openProductModal());
    document.getElementById('productsSearch').addEventListener('input', Util.debounce(e => { S.productsPage.q = e.target.value.trim(); S.productsPage.page = 1; this.loadProductsPage(); }, 200));
    document.getElementById('saveProductBtn').addEventListener('click', () => this.saveProduct());
    document.getElementById('productCategory').addEventListener('change', () => this.updateProductSubCategories());
    document.getElementById('importExcelInput').addEventListener('change', e => this.importExcel(e.target));
    // Protected downloads use the same-origin HttpOnly session cookie
    this.bindDownloadLinks();

    // Categories (inside products page)
    document.getElementById('addCategoryBtn').addEventListener('click', () => this.openCategoryModal());
    document.getElementById('saveCategoryBtn').addEventListener('click', () => this.saveCategory());

    // Products page tabs (products / categories)
    document.querySelectorAll('[data-pctab]').forEach(t => {
      t.addEventListener('click', () => this.switchProductsTab(t.dataset.pctab));
    });

    // Customers
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

    // Invoices
    document.getElementById('invoicesSearch').addEventListener('input', Util.debounce(e => { S.invoices.q = e.target.value.trim(); S.invoices.page = 1; this.clearInvoicesSelection(); this.loadInvoicesPage(); }, 200));
    document.querySelectorAll('.filter-tab[data-filter]').forEach(t => t.addEventListener('click', () => this.filterInvoices(t.dataset.filter)));
    document.getElementById('invoicesSelectAll').addEventListener('change', e => this.toggleSelectAllInvoices(e.target.checked));
    document.getElementById('invoicesCombinedPdfBtn').addEventListener('click', () => this.openCombinedInvoiceOptions(Array.from(S.invoices.selected)));
    document.getElementById('invoicesClearSelBtn').addEventListener('click', () => this.clearInvoicesSelection());

    // Suppliers
    document.getElementById('addSupplierBtn').addEventListener('click', () => this.openSupplierModal());
    document.getElementById('saveSupplierBtn').addEventListener('click', () => this.saveSupplier());
    document.getElementById('suppliersSearch').addEventListener('input', Util.debounce(e => { S.suppliersPage.q = e.target.value.trim(); S.suppliersPage.page = 1; this.loadSuppliersPage(); }, 200));

    // Reports
    document.getElementById('loadReportBtn').addEventListener('click', () => this.loadReport());
    document.getElementById('reportType').addEventListener('change', () => this.loadReport());

    // Users
    document.getElementById('addUserBtn').addEventListener('click', () => this.openUserModal());
    document.getElementById('saveUserBtn').addEventListener('click', () => this.saveUser());
    document.getElementById('changeCredsBtn').addEventListener('click', () => this.changeCredentials());

    // Settings
    document.getElementById('saveSettingsBtn').addEventListener('click', () => this.saveSettings());
    document.getElementById('setLogoInput').addEventListener('change', e => this.previewLogo(e.target));
    document.getElementById('resetQuickQtyBtn').addEventListener('click', () => { document.getElementById('setQuickQty').value = '1,5,10,20,30,50,100'; });
    document.getElementById('createBackupBtn').addEventListener('click', () => this.backup());

    // Audit
    document.getElementById('clearAuditBtn').addEventListener('click', () => this.clearAudit());

    // Quick add modal
    document.getElementById('saveQuickAddBtn').addEventListener('click', () => this.saveQuickAdd());

    // Partial
    document.getElementById('ptPaid').addEventListener('input', () => {
      const paid = parseFloat(document.getElementById('ptPaid').value) || 0;
      const total = parseFloat(document.getElementById('ptTotal').value) || 0;
      document.getElementById('ptRemain').value = Math.max(0, total - paid).toFixed(2);
    });
    document.getElementById('confirmPartialBtn').addEventListener('click', () => this.confirmPartial());

    // Audit search
    document.getElementById('auditSearchBtn').addEventListener('click', () => this.loadAuditPage());
    document.getElementById('auditResetBtn').addEventListener('click', () => this.resetAuditSearch());
    document.getElementById('auditSearch').addEventListener('keydown', e => { if (e.key === 'Enter') this.loadAuditPage(); });

    // Print preview
    document.getElementById('previewInvoiceBtn').addEventListener('click', () => this.previewInvoice());
    document.getElementById('printInvoiceBtn').addEventListener('click', () => this.printCurrent());

    // Theme toggle
    document.getElementById('themeToggle').addEventListener('click', () => this.toggleTheme());

    // Collect payment
    document.getElementById('collectInvoiceBtn').addEventListener('click', () => this.openCollect());
    document.getElementById('confirmCollectBtn').addEventListener('click', () => this.confirmCollect());
    document.getElementById('returnInvoiceBtn').addEventListener('click', () => this.openReturnInvoice());
    document.getElementById('confirmReturnInvoiceBtn').addEventListener('click', () => this.confirmReturnInvoice());
    document.getElementById('returnPaymentMethod').addEventListener('change', () => this.updateReturnPaymentUI());

    // Keep-alive ping every 60s to keep server status updated
    setInterval(() => this.pingServer(), 60000);
  },

  async pingServer() {
    try {
      await API.get('/api/auth/me');
      this.setServerStatus(true);
    } catch {
      this.setServerStatus(false);
    }
  },

  setServerStatus(ok) {
    const dot = document.getElementById('serverStatus');
    const text = document.getElementById('serverStatusText');
    if (!dot) return;
    dot.style.background = ok ? 'var(--ok)' : 'var(--err)';
    text.textContent = ok ? 'متصل' : 'غير متصل';
  },

  /* ─── AUTH ─── */
  async login() {
    const user = document.getElementById('loginUser').value.trim();
    const pass = document.getElementById('loginPass').value;
    const err = document.getElementById('loginError');
    if (!user || !pass) { err.textContent = 'أدخل البيانات'; err.style.display = 'block'; return; }
    try {
      const r = await API.post('/api/auth/login', { login: user, password: pass });
      S.user = r.user;
      document.getElementById('loginPass').value = '';
      err.style.display = 'none';
      await this.loadSettings();
      this.showApp();
      this.toast('مرحباً ' + S.user.name);
    } catch (e) {
      err.textContent = e.message;
      err.style.display = 'block';
      document.getElementById('loginPass').value = '';
      document.getElementById('loginPass').focus();
    }
  },

  async logout() {
    if (!await this.confirm('تسجيل الخروج', 'هل تريد تسجيل الخروج؟')) return;
    try { await API.post('/api/auth/logout', {}); } catch {}
    S.user = null;
    this.clearState();
    this.showLogin();
  },

  clearState() {
    S.cart = [];
    S.cartCustomer = null;
    S.productCache.clear();
    S.categoryCache.clear();
    S.customerCache.clear();
    S.supplierCache.clear();
    S.categoryChildren.clear();
  },

  /* ─── THEME ─── */
  toggleTheme() {
    const isDark = document.body.classList.toggle('dark-mode');
    const btn = document.getElementById('themeToggle');
    btn.textContent = isDark ? '☀️' : '🌙';
    localStorage.setItem('pos_theme', isDark ? 'dark' : 'light');
  },

  applyTheme(theme) {
    if (theme === 'dark') {
      document.body.classList.add('dark-mode');
      const btn = document.getElementById('themeToggle');
      if (btn) btn.textContent = '☀️';
    }
  },

  /* ─── DOMAIN PAGES ─── */
  ...posMethods,
  ...productMethods,
  ...supplierMethods,
  ...customerMethods,
  ...invoiceMethods,
  ...reportMethods,
  ...userMethods,

  /* ─── SETTINGS ─── */
  ...settingsMethods,

  /* ─── AUDIT ─── */
  ...auditMethods,

  /* ─── SCANNER ─── */
  ...quickAddMethods,
};

setUnauthorizedHandler(() => { App.showLogin(); App.toast('انتهت الجلسة، سجل دخول مرة أخرى', 'warning'); });

/* ═══ BOOT ═══ */
window.addEventListener('DOMContentLoaded', () => App.init());
