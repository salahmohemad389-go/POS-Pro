/* Progressive UI shell for POS Pro upgrades. All icons are inline/local. */
(() => {
  const html = (markup) => { const t = document.createElement('template'); t.innerHTML = markup.trim(); return t.content.firstElementChild; };
  const byId = (id) => document.getElementById(id);
  const icon = (name) => {
    const paths = {
      eye:'<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
      cart:'<circle cx="9" cy="20" r="1"/><circle cx="19" cy="20" r="1"/><path d="M3 4h2l2.4 10.4a2 2 0 0 0 2 1.6h7.7a2 2 0 0 0 2-1.6L21 7H6"/>',
      box:'<path d="m21 8-9 5-9-5 9-5 9 5Z"/><path d="m3 8 9 5 9-5v8l-9 5-9-5V8Z"/>',
      users:'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
      file:'<path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6M9 13h6M9 17h6"/>',
      truck:'<path d="M3 6h11v11H3zM14 10h4l3 3v4h-7z"/><circle cx="7" cy="19" r="2"/><circle cx="18" cy="19" r="2"/>',
      chart:'<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
      user:'<circle cx="12" cy="7" r="4"/><path d="M4 22a8 8 0 0 1 16 0"/>',
      settings:'<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21h-4v-.09A1.7 1.7 0 0 0 9 19.35a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.63 15 1.7 1.7 0 0 0 3.07 14H3v-4h.09A1.7 1.7 0 0 0 4.65 9a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.63 1.7 1.7 0 0 0 10 3.07V3h4v.09A1.7 1.7 0 0 0 15 4.65a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.37 9 1.7 1.7 0 0 0 20.93 10H21v4h-.09A1.7 1.7 0 0 0 19.4 15Z"/>',
      history:'<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
      return:'<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 6 6v3"/>',
      menu:'<path d="M4 6h16M4 12h16M4 18h16"/>'
    };
    return `<svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${paths[name] || paths.file}</svg>`;
  };

  const loginBox = document.querySelector('.login-box');
  if (loginBox) {
    const oldLogo = loginBox.querySelector('.login-logo');
    if (oldLogo) oldLogo.replaceWith(html('<div class="login-brand-mark" id="loginBrandMark"><img id="loginLogoImg" class="brand-logo-img" alt="شعار المتجر" hidden></div>'));
    const title = loginBox.querySelector('h2');
    if (title && !byId('loginStoreName')) title.insertAdjacentElement('beforebegin', html('<h1 id="loginStoreName" class="login-store-name">POS</h1>'));
    const sub = loginBox.querySelector('.login-sub'); if (sub) { sub.id = 'loginTagline'; sub.textContent = ''; }
    const user = byId('loginUser'); if (user) { user.value = ''; user.placeholder = 'اسم الدخول'; }
    const pass = byId('loginPass');
    if (pass && !byId('toggleLoginPass')) { const wrap = html('<div class="password-wrap"></div>'); pass.parentNode.insertBefore(wrap, pass); wrap.appendChild(pass); const btn = html(`<button type="button" id="toggleLoginPass" class="password-eye" aria-label="إظهار كلمة المرور" title="إظهار/إخفاء كلمة المرور">${icon('eye')}</button>`); wrap.appendChild(btn); }
  }

  const sideHeader = document.querySelector('.sidebar-header');
  if (sideHeader) { sideHeader.querySelector('.logo,.sidebar-brand-mark')?.remove(); const small = sideHeader.querySelector('.logo-text small'); if (small) { small.id = 'sidebarTagline'; small.textContent = ''; } }

  const navIcons = {pos:'cart',products:'box',customers:'users',invoices:'file',suppliers:'truck',reports:'chart',users:'user',settings:'settings',audit:'history'};
  document.querySelectorAll('.nav-item[data-page]').forEach(el => { const target = el.querySelector('.nav-icon'); if (target) target.innerHTML = icon(navIcons[el.dataset.page] || 'file'); });

  const menuToggle = byId('menuToggle'); if (menuToggle) menuToggle.innerHTML = icon('menu');
  const topbar = document.querySelector('.topbar'); if (topbar && !byId('sidebarCollapseBtn')) topbar.insertBefore(html(`<button class="menu-toggle sidebar-collapse-btn" id="sidebarCollapseBtn" type="button" title="إخفاء/إظهار الشريط الجانبي">${icon('menu')}</button>`), topbar.children[1] || null);

  const tabs = document.querySelector('#page-pos .cart-tabs');
  if (tabs) {
    tabs.querySelector('.cart-return-hint')?.remove();
    if (!byId('posReturnBtn')) { const saleTab = tabs.querySelector('.cart-tab[data-type="sale"]'); saleTab?.insertAdjacentElement('afterend', html(`<button type="button" class="cart-tab return-tab" id="posReturnBtn">${icon('return')}<span>مرتجع</span></button>`)); }
  }
  const posSearch = document.querySelector('#page-pos .pos-search'); if (posSearch && !byId('scanFeedback')) posSearch.appendChild(html('<div id="scanFeedback" class="scan-feedback" aria-live="polite"></div>'));
  const listHead = document.querySelector('.product-list-head'); if (listHead && listHead.children.length > 3) listHead.lastElementChild.remove();

  const importInput = byId('importExcelInput'); if (importInput && !byId('updatePricesInput')) { const label = html('<label class="btn btn-secondary btn-sm price-update-btn">تحديث الأسعار<input type="file" id="updatePricesInput" accept=".xlsx,.xls,.csv" style="display:none"></label>'); importInput.closest('label')?.insertAdjacentElement('afterend', label); }

  const usersHead = document.querySelector('#page-users thead tr'); if (usersHead) usersHead.innerHTML = '<th>الاسم</th><th>اسم الدخول</th><th>الدور</th><th>الصلاحية حتى</th><th>الحالة</th><th></th>';
  const userRoleGroup = byId('userRole')?.closest('.form-group');
  if (userRoleGroup && !byId('userExpiresAt')) { userRoleGroup.insertAdjacentElement('afterend', html('<div class="form-row user-access-row"><div class="form-group"><label>صلاحية الحساب حتى</label><input type="datetime-local" id="userExpiresAt"><small>اتركها فارغة بدون تاريخ انتهاء.</small></div><div class="form-group"><label class="toggle-label"><input type="checkbox" id="userActive" checked> الحساب نشط</label></div></div>')); userRoleGroup.parentElement.appendChild(html('<div class="form-group" id="userPermissionsGroup"><label>صلاحيات هذا المستخدم</label><div id="userPermissionsGrid" class="permission-grid"></div><small>المالك فقط يمكنه تخصيص الصلاحيات بالتفصيل.</small></div>')); }

  const legacyCredBtn = byId('changeCredsBtn'); if (legacyCredBtn) legacyCredBtn.closest('.card')?.classList.add('legacy-credentials-card');
  const settingsGrid = document.querySelector('#page-settings .settings-grid');
  if (settingsGrid) {
    const financial = byId('setCurrency')?.closest('.card');
    if (financial && !byId('setFeatureReports')) financial.appendChild(html('<div class="settings-feature-box"><h4>الأقسام الظاهرة في النظام</h4><label class="toggle-label"><input type="checkbox" id="setFeatureProducts" checked> المنتجات والأقسام</label><label class="toggle-label"><input type="checkbox" id="setFeatureCustomers" checked> العملاء</label><label class="toggle-label"><input type="checkbox" id="setFeatureInvoices" checked> الفواتير</label><label class="toggle-label"><input type="checkbox" id="setFeatureSuppliers" checked> الموردون</label><label class="toggle-label"><input type="checkbox" id="setFeatureReports" checked> التقارير</label><label class="toggle-label"><input type="checkbox" id="setFeatureAudit" checked> سجل العمليات</label><label class="toggle-label"><input type="checkbox" id="setQuickQtyEnabled" checked> الكميات السريعة في نقطة البيع</label></div>'));
    if (!byId('setPrimaryColor')) settingsGrid.appendChild(html('<div class="card"><div class="card-header"><h3>ألوان الواجهة</h3></div><div class="settings-card-body"><div class="form-row"><div class="form-group"><label>اللون الأساسي</label><input type="color" id="setPrimaryColor" value="#163b63"></div><div class="form-group"><label>اللون المميز</label><input type="color" id="setAccentColor" value="#c99a35"></div></div><small>يتم حفظ الألوان لكل النظام وتطبيقها مباشرة.</small></div></div>'));
    if (!byId('shortcutNewSale')) settingsGrid.appendChild(html('<div class="card"><div class="card-header"><h3>اختصارات لوحة المفاتيح</h3></div><div class="settings-card-body shortcuts-grid"><label>فاتورة جديدة<input id="shortcutNewSale" placeholder="F2"></label><label>مرتجع<input id="shortcutReturn" placeholder="F3"></label><label>بحث المنتجات<input id="shortcutSearch" placeholder="F4"></label><label>إخفاء الشريط الجانبي<input id="shortcutSidebar" placeholder="F6"></label><label>بيع نقدي<input id="shortcutCash" placeholder="F8"></label><label>بيع آجل<input id="shortcutCredit" placeholder="F9"></label><label>إفراغ السلة<input id="shortcutClear" placeholder="F10"></label><small>اكتب مثل F2 أو Ctrl+K أو Alt+R. الاختصارات تعمل بعد حفظ الإعدادات.</small></div></div>'));
    if (!byId('settingsChangeCredsBtn')) settingsGrid.appendChild(html('<div class="card settings-credentials-card"><div class="card-header"><h3>بيانات دخولي</h3></div><div class="settings-card-body"><div class="form-group"><label>اسم الدخول الحالي</label><input id="settingsCurrentLogin" type="text" readonly></div><div class="form-group"><label>اسم دخول جديد</label><input id="settingsNewLogin" type="text" autocomplete="username"></div><div class="form-group"><label>كلمة المرور الحالية</label><input id="settingsCurrentPass" type="password" autocomplete="current-password"></div><div class="form-group"><label>كلمة مرور جديدة</label><input id="settingsNewPass" type="password" autocomplete="new-password" placeholder="12 حرفاً على الأقل"></div><button class="btn btn-primary" id="settingsChangeCredsBtn">حفظ بيانات الدخول</button></div></div>'));
  }

  if (!byId('pdfPreviewModal')) { const confirm = byId('confirmModal'); const modal = html('<div class="modal" id="pdfPreviewModal"><div class="modal-content modal-xl pdf-preview-content"><div class="modal-header"><h3>معاينة الفاتورة PDF</h3><button class="modal-close" data-close="pdfPreviewModal">×</button></div><div class="modal-body pdf-preview-body"><iframe id="pdfPreviewFrame" title="معاينة PDF"></iframe></div><div class="modal-footer"><button class="btn btn-secondary" data-close="pdfPreviewModal">إغلاق</button><a class="btn btn-info" id="pdfPreviewDownload" download="invoice.pdf">تنزيل PDF</a><button class="btn btn-primary" id="pdfPreviewPrintBtn">طباعة</button></div></div></div>'); (confirm?.parentNode || document.body).insertBefore(modal, confirm || null); }

  const normalize = (e) => { const p=[]; if(e.ctrlKey)p.push('CTRL'); if(e.altKey)p.push('ALT'); if(e.shiftKey)p.push('SHIFT'); let k=String(e.key||'').toUpperCase(); if(k===' ')k='SPACE'; p.push(k); return p.join('+'); };
  document.addEventListener('keydown', (e) => {
    const map = window.__posShortcuts || {}; const key = normalize(e); const action = Object.entries(map).find(([,v]) => String(v||'').toUpperCase() === key)?.[0]; if (!action) return;
    if ((e.target?.matches?.('input,textarea,select')) && !/^F\d+$/.test(key)) return;
    const click = (sel) => document.querySelector(sel)?.click();
    const actions = {new_sale:()=>click('.cart-tab[data-type="sale"]'),return_invoice:()=>click('#posReturnBtn'),focus_search:()=>byId('posSearch')?.focus(),cash_checkout:()=>click('.cart-actions [data-method="cash"]'),credit_checkout:()=>click('.cart-actions [data-method="credit"]'),clear_cart:()=>click('#clearCartBtn'),toggle_sidebar:()=>click('#sidebarCollapseBtn')};
    if (actions[action]) { e.preventDefault(); actions[action](); }
  });
  byId('sidebarCollapseBtn')?.addEventListener('click', () => { const app = byId('app'); const collapsed = app?.classList.toggle('sidebar-collapsed'); localStorage.setItem('pos_sidebar_collapsed', collapsed ? '1' : '0'); });
  if (localStorage.getItem('pos_sidebar_collapsed') === '1') byId('app')?.classList.add('sidebar-collapsed');
})();
