/* Progressive UI shell for POS Pro. All icons are inline/local: no CDN. */
(() => {
  const byId = id => document.getElementById(id);
  const html = markup => { const t = document.createElement('template'); t.innerHTML = markup.trim(); return t.content.firstElementChild; };
  const icon = name => `<svg class="ui-icon" aria-hidden="true"><use href="#i-${name}"></use></svg>`;

  if (!byId('posIconSprite')) {
    document.body.insertAdjacentHTML('afterbegin', `<svg id="posIconSprite" class="svg-sprite" xmlns="http://www.w3.org/2000/svg">
      <symbol id="i-cart" viewBox="0 0 24 24"><path d="M3 4h2l2 11h10l2-7H7M9 20a1 1 0 1 0 0-2 1 1 0 0 0 0 2Zm8 0a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"/></symbol>
      <symbol id="i-box" viewBox="0 0 24 24"><path d="m4 7 8-4 8 4-8 4-8-4Zm0 0v10l8 4 8-4V7M12 11v10"/></symbol>
      <symbol id="i-users" viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm13 10v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></symbol>
      <symbol id="i-file" viewBox="0 0 24 24"><path d="M6 2h9l5 5v15H6zM14 2v6h6M9 13h8M9 17h8"/></symbol>
      <symbol id="i-truck" viewBox="0 0 24 24"><path d="M3 5h11v11H3zM14 9h4l3 4v3h-7zM7 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm11 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"/></symbol>
      <symbol id="i-chart" viewBox="0 0 24 24"><path d="M4 20V10h4v10M10 20V4h4v16M16 20v-7h4v7M2 20h20"/></symbol>
      <symbol id="i-user" viewBox="0 0 24 24"><path d="M20 21a8 8 0 0 0-16 0M12 13a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z"/></symbol>
      <symbol id="i-settings" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21h-4v-.09A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3v-4h.09A1.7 1.7 0 0 0 4.6 8.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3h4v.09A1.7 1.7 0 0 0 15.4 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.12.37.34.72.64 1 .3.28.7.42 1.1.4H21v4h-.09A1.7 1.7 0 0 0 19.4 15Z"/></symbol>
      <symbol id="i-log" viewBox="0 0 24 24"><path d="M7 3h10v18H7zM9 7h6M9 11h6M9 15h4"/></symbol>
      <symbol id="i-return" viewBox="0 0 24 24"><path d="M9 7 4 12l5 5M5 12h8a6 6 0 0 1 6 6v1"/></symbol>
      <symbol id="i-cash" viewBox="0 0 24 24"><rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="3"/><path d="M7 9H5m14 6h-2"/></symbol>
      <symbol id="i-credit" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18M7 15h4"/></symbol>
      <symbol id="i-split" viewBox="0 0 24 24"><path d="M5 4v5a3 3 0 0 0 3 3h8M5 20v-5a3 3 0 0 1 3-3h8M14 8l4 4-4 4"/></symbol>
      <symbol id="i-trash" viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3m-9 0 1 14h10l1-14M10 11v6m4-6v6"/></symbol>
      <symbol id="i-eye" viewBox="0 0 24 24"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></symbol>
      <symbol id="i-eye-off" viewBox="0 0 24 24"><path d="m3 3 18 18M10.6 5.2A9.9 9.9 0 0 1 12 5c6 0 10 7 10 7a17 17 0 0 1-2.1 2.8M6.2 6.2C3.6 8.2 2 12 2 12s4 7 10 7a9.5 9.5 0 0 0 4.1-.9M9.9 9.9a3 3 0 0 0 4.2 4.2"/></symbol>
      <symbol id="i-menu" viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h16"/></symbol>
      <symbol id="i-palette" viewBox="0 0 24 24"><path d="M12 3a9 9 0 1 0 0 18h1.5a2 2 0 0 0 0-4H12a2 2 0 0 1 0-4h3a6 6 0 0 0 0-12h-3Z"/><circle cx="7.5" cy="10" r=".8"/><circle cx="9" cy="6.5" r=".8"/><circle cx="14" cy="6" r=".8"/></symbol>
      <symbol id="i-keyboard" viewBox="0 0 24 24"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 9h1m3 0h1m3 0h1m3 0h1M6 13h1m3 0h1m3 0h1m3 0h1M7 16h10"/></symbol>
      <symbol id="i-upload" viewBox="0 0 24 24"><path d="M12 16V3m0 0L7 8m5-5 5 5M4 15v5h16v-5"/></symbol>
      <symbol id="i-download" viewBox="0 0 24 24"><path d="M12 3v13m0 0 5-5m-5 5-5-5M4 20h16"/></symbol>
      <symbol id="i-backup" viewBox="0 0 24 24"><path d="M12 4a8 8 0 1 1-7.4 5M4 4v5h5"/><path d="M12 8v5l3 2"/></symbol>
    </svg>`);
  }

  // Login: keep a simple POS monogram; configured image is reserved for invoices.
  const loginBox = document.querySelector('.login-box');
  if (loginBox) {
    const oldLogo = loginBox.querySelector('.login-logo');
    if (oldLogo) oldLogo.textContent = 'POS';
    const title = loginBox.querySelector('h2');
    if (title && !byId('loginStoreName')) title.insertAdjacentElement('beforebegin', html('<h1 id="loginStoreName" class="login-store-name">POS</h1>'));
    const sub = loginBox.querySelector('.login-sub'); if (sub) { sub.id = 'loginTagline'; sub.textContent = ''; }
    const user = byId('loginUser'); if (user) { user.value = ''; user.placeholder = 'اسم الدخول'; }
    const pass = byId('loginPass');
    if (pass && !byId('toggleLoginPass')) {
      const wrap = html('<div class="password-wrap"></div>'); pass.parentNode.insertBefore(wrap, pass); wrap.appendChild(pass);
      wrap.appendChild(html(`<button type="button" id="toggleLoginPass" class="password-eye" aria-label="إظهار كلمة المرور" title="إظهار/إخفاء كلمة المرور">${icon('eye')}</button>`));
    }
  }

  // Sidebar: POS stays as the local monogram; store name remains data-driven.
  const sideHeader = document.querySelector('.sidebar-header');
  if (sideHeader) {
    const oldLogo = sideHeader.querySelector('.logo'); if (oldLogo) oldLogo.textContent = 'POS';
    const small = sideHeader.querySelector('.logo-text small'); if (small) { small.id = 'sidebarTagline'; small.textContent = ''; }
    if (!byId('sidebarCollapseBtn')) sideHeader.insertAdjacentElement('beforeend', html(`<button type="button" id="sidebarCollapseBtn" class="sidebar-collapse-btn" title="طي/فتح الشريط">${icon('menu')}</button>`));
  }

  const navIcons = { pos:'cart', products:'box', customers:'users', invoices:'file', suppliers:'truck', reports:'chart', users:'user', settings:'settings', audit:'log' };
  Object.entries(navIcons).forEach(([page, name]) => {
    const slot = document.querySelector(`.nav-item[data-page="${page}"] .nav-icon`); if (slot) slot.innerHTML = icon(name);
  });
  const menuToggle = byId('menuToggle'); if (menuToggle) menuToggle.innerHTML = icon('menu');

  // POS return is a real action beside "فاتورة جديدة", not an explanatory sentence.
  document.querySelectorAll('.cart-return-hint').forEach(el => el.remove());
  const cartTabs = document.querySelector('#page-pos .cart-tabs');
  if (cartTabs && !byId('posReturnBtn')) {
    const saleTab = cartTabs.querySelector('.cart-tab[data-type="sale"]');
    const btn = html(`<button type="button" class="cart-tab cart-return-tab" id="posReturnBtn">${icon('return')}<span>مرتجع</span></button>`);
    saleTab?.insertAdjacentElement('afterend', btn);
  }
  const posSearch = document.querySelector('#page-pos .pos-search');
  if (posSearch && !byId('scanFeedback')) posSearch.appendChild(html('<div id="scanFeedback" class="scan-feedback" aria-live="polite"></div>'));
  const listHead = document.querySelector('.product-list-head'); if (listHead && listHead.children.length > 3) listHead.lastElementChild.remove();

  const cash = document.querySelector('.cart-actions [data-method="cash"]'); if (cash) cash.innerHTML = `${icon('cash')}<span>نقدي</span>`;
  const credit = document.querySelector('.cart-actions [data-method="credit"]'); if (credit) credit.innerHTML = `${icon('credit')}<span>آجل</span>`;
  const partial = byId('partialBtn'); if (partial) partial.innerHTML = `${icon('split')}<span>جزئي</span>`;
  const clear = byId('clearCartBtn'); if (clear) clear.innerHTML = `${icon('trash')}<span>إفراغ</span>`;

  const importInput = byId('importExcelInput');
  if (importInput && !byId('updatePricesInput')) {
    const label = html(`<label class="btn btn-secondary btn-sm price-update-btn">${icon('upload')}<span>تحديث الأسعار</span><input type="file" id="updatePricesInput" accept=".xlsx,.xls,.csv" style="display:none"></label>`);
    importInput.closest('label')?.insertAdjacentElement('afterend', label);
  }

  const usersHead = document.querySelector('#page-users thead tr');
  if (usersHead) usersHead.innerHTML = '<th>الاسم</th><th>اسم الدخول</th><th>الدور</th><th>الصلاحية حتى</th><th>الحالة</th><th></th>';
  const userRoleGroup = byId('userRole')?.closest('.form-group');
  if (userRoleGroup && !byId('userExpiresAt')) {
    userRoleGroup.insertAdjacentElement('afterend', html('<div class="form-row user-access-row"><div class="form-group"><label>صلاحية الحساب حتى</label><input type="datetime-local" id="userExpiresAt"><small>اتركها فارغة بدون تاريخ انتهاء.</small></div><div class="form-group"><label class="toggle-label"><input type="checkbox" id="userActive" checked> الحساب نشط</label></div></div>'));
    userRoleGroup.parentElement.appendChild(html('<div class="form-group" id="userPermissionsGroup"><label>صلاحيات هذا المستخدم</label><div id="userPermissionsGrid" class="permission-grid"></div><small>المالك الرئيسي فقط يستطيع تخصيص الصلاحيات بالتفصيل.</small></div>'));
  }

  const legacyCredBtn = byId('changeCredsBtn'); if (legacyCredBtn) legacyCredBtn.closest('.card')?.classList.add('legacy-credentials-card');
  const settingsGrid = document.querySelector('#page-settings .settings-grid');
  if (settingsGrid) {
    const financial = byId('setCurrency')?.closest('.card');
    if (financial && !byId('setFeatureReports')) financial.appendChild(html(`<div class="settings-feature-box"><h4>الأقسام الظاهرة في النظام</h4>
      <label class="toggle-label"><input type="checkbox" id="setFeatureReports" checked> التقارير</label>
      <label class="toggle-label"><input type="checkbox" id="setFeatureSuppliers" checked> الموردون</label>
      <label class="toggle-label"><input type="checkbox" id="setFeatureInvoices" checked> الفواتير</label>
      <label class="toggle-label"><input type="checkbox" id="setFeatureCustomers" checked> العملاء</label>
      <label class="toggle-label"><input type="checkbox" id="setQuickQtyEnabled" checked> الكميات السريعة في نقطة البيع</label>
      <small>الإخفاء يزيل القسم من الواجهة. صلاحيات المستخدم تبقى طبقة حماية مستقلة.</small>
    </div>`));

    if (!byId('setPrimaryColor')) settingsGrid.appendChild(html(`<div class="card appearance-settings-card"><div class="card-header"><h3>${icon('palette')} ألوان النظام</h3></div><div class="settings-card-body color-settings-grid">
      <div class="form-group"><label>اللون الرئيسي</label><div class="color-control"><input type="color" id="setPrimaryColor" value="#2563eb"><input type="text" id="setPrimaryColorText" value="#2563eb" maxlength="7" dir="ltr"></div></div>
      <div class="form-group"><label>اللون المساعد</label><div class="color-control"><input type="color" id="setAccentColor" value="#0891b2"><input type="text" id="setAccentColorText" value="#0891b2" maxlength="7" dir="ltr"></div></div>
      <small>الألوان محفوظة على النظام وتظهر لكل المستخدمين.</small>
    </div></div>`));

    if (!byId('shortcutNewSale')) settingsGrid.appendChild(html(`<div class="card shortcuts-settings-card"><div class="card-header"><h3>${icon('keyboard')} اختصارات الكيبورد</h3></div><div class="settings-card-body"><div class="shortcut-grid">
      <label>فاتورة جديدة<input id="shortcutNewSale" class="shortcut-input" dir="ltr"></label>
      <label>بحث نقطة البيع<input id="shortcutSearch" class="shortcut-input" dir="ltr"></label>
      <label>مرتجع<input id="shortcutReturn" class="shortcut-input" dir="ltr"></label>
      <label>دفع نقدي<input id="shortcutCash" class="shortcut-input" dir="ltr"></label>
      <label>بيع آجل<input id="shortcutCredit" class="shortcut-input" dir="ltr"></label>
      <label>دفع جزئي<input id="shortcutPartial" class="shortcut-input" dir="ltr"></label>
      <label>إفراغ السلة<input id="shortcutClearCart" class="shortcut-input" dir="ltr"></label>
      <label>طي/فتح الشريط<input id="shortcutSidebar" class="shortcut-input" dir="ltr"></label>
      <label>صفحة الفواتير<input id="shortcutInvoices" class="shortcut-input" dir="ltr"></label>
    </div><small>مثال: Alt+N أو Ctrl+Shift+S أو F2. اترك الحقل فارغًا لإلغاء الاختصار.</small></div></div>`));

    if (!byId('settingsChangeCredsBtn')) settingsGrid.appendChild(html('<div class="card settings-credentials-card"><div class="card-header"><h3>بيانات دخولي</h3></div><div class="settings-card-body"><div class="form-group"><label>اسم الدخول الحالي</label><input id="settingsCurrentLogin" type="text" readonly></div><div class="form-group"><label>اسم دخول جديد</label><input id="settingsNewLogin" type="text" autocomplete="username"></div><div class="form-group"><label>كلمة المرور الحالية</label><input id="settingsCurrentPass" type="password" autocomplete="current-password"></div><div class="form-group"><label>كلمة مرور جديدة</label><input id="settingsNewPass" type="password" autocomplete="new-password" placeholder="12 حرفاً على الأقل"></div><button class="btn btn-primary" id="settingsChangeCredsBtn">حفظ بيانات الدخول</button></div></div>'));
  }

  if (!byId('pdfPreviewModal')) {
    const confirm = byId('confirmModal');
    const modal = html(`<div class="modal" id="pdfPreviewModal"><div class="modal-content modal-xl pdf-preview-content"><div class="modal-header"><h3>معاينة الفاتورة PDF</h3><button class="modal-close" data-close="pdfPreviewModal">×</button></div><div class="modal-body pdf-preview-body"><iframe id="pdfPreviewFrame" title="معاينة PDF"></iframe></div><div class="modal-footer"><button class="btn btn-secondary" data-close="pdfPreviewModal">إغلاق</button><a class="btn btn-info" id="pdfPreviewDownload" download="invoice.pdf">${icon('download')}<span>تنزيل PDF</span></a><button class="btn btn-primary" id="pdfPreviewPrintBtn"><span>طباعة</span></button></div></div></div>`);
    (confirm?.parentNode || document.body).insertBefore(modal, confirm || null);
  }
})();
