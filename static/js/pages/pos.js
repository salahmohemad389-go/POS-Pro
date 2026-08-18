import { S } from '../core/state.js';
import { API } from '../core/api.js';
import { Util } from '../core/util.js';

export const posMethods = {
  async renderPOS() {
    this.renderQuickQty();
    this.recalcCart();
    await this.loadPOSProducts();
    await this.loadCategoriesForPOS();
  },

  async loadCategoriesForPOS() {
    if (S.categoryCache.size) {
      this.renderPOSCategories();
      return;
    }
    try {
      const cats = await API.get('/api/categories');
      cats.forEach(c => S.categoryCache.set(c.id, c));
      this.buildCategoryChildren();
      this.renderPOSCategories();
    } catch (e) { console.error(e); }
  },

  buildCategoryChildren() {
    S.categoryChildren.clear();
    S.categoryCache.forEach(c => {
      const pid = c.parent_id || 0;
      if (!S.categoryChildren.has(pid)) S.categoryChildren.set(pid, []);
      S.categoryChildren.get(pid).push(c);
    });
  },

  renderPOSCategories() {
    const el = document.getElementById('posCategories');
    let html = `<button class="category-chip ${!S.pos.cat ? 'active' : ''}" data-id="">الكل</button>`;
    const topLevel = S.categoryChildren.get(0) || [];
    topLevel.forEach(c => {
      html += `<button class="category-chip ${S.pos.cat == c.id ? 'active' : ''}" data-id="${c.id}">${Util.esc(c.name)}</button>`;
      const subs = S.categoryChildren.get(c.id) || [];
      subs.forEach(sc => {
        html += `<button class="category-chip ${S.pos.cat == sc.id ? 'active' : ''}" data-id="${sc.id}" style="font-size:11px">↳ ${Util.esc(sc.name)}</button>`;
      });
    });
    el.innerHTML = html;
    el.querySelectorAll('.category-chip').forEach(b => {
      b.addEventListener('click', () => {
        S.pos.cat = b.dataset.id;
        S.pos.page = 1;
        this.renderPOSCategories();
        this.loadPOSProducts();
      });
    });
  },

  async loadPOSProducts() {
    const el = document.getElementById('posProducts');
    try {
      const params = new URLSearchParams({ page: S.pos.page, limit: S.pos.limit });
      if (S.pos.q) params.set('q', S.pos.q);
      if (S.pos.cat) params.set('category_id', S.pos.cat);
      const data = await API.get(`/api/products?${params}`);
      S.productCache.clear();
      data.items.forEach(p => S.productCache.set(p.id, p));
      this.renderPOSProducts(data);
      this.renderPOSPagination(data);
    } catch (e) {
      el.innerHTML = `<div class="empty-cart">فشل التحميل: ${Util.esc(e.message)}</div>`;
    }
  },

  renderPOSProducts(data) {
    const el = document.getElementById('posProducts');
    const items = data.items || [];
    if (!items.length) {
      const canAdd = S.user && (S.user.role === 'admin' || S.user.role === 'manager');
      const q = (S.pos.q || '').trim();
      el.innerHTML = `<div class="empty-cart">لا توجد منتجات${q ? ` مطابقة لـ «${Util.esc(q)}»` : ''}</div>` +
        (canAdd && q ? `<button class="btn btn-primary pos-quick-add-empty" type="button">+ إضافة المنتج الآن</button>` : '');
      const quick = el.querySelector('.pos-quick-add-empty');
      if (quick) quick.addEventListener('click', () => this.openQuickAdd(q));
      return;
    }
    el.innerHTML = items.map(p => {
      const stock = parseFloat(p.stock) || 0;
      const barcode = p.barcode ? `<span class="pr-barcode">${Util.esc(p.barcode)}</span>` : '';
      return `<div class="product-row ${stock <= 0 ? 'dimmed' : ''}" data-id="${p.id}">
        <div><div class="pr-name">${Util.esc(p.name)}</div>${barcode}</div>
        <div class="pr-stock">${Util.r3(stock)}</div>
        <div class="pr-price">${Util.money(p.price)}</div>
        <button class="pr-add" type="button" aria-label="إضافة ${Util.esc(p.name)}" ${stock <= 0 ? 'disabled' : ''}>+</button>
      </div>`;
    }).join('');
    el.querySelectorAll('.product-row').forEach(row => {
      row.addEventListener('dblclick', () => this.addToCart(parseInt(row.dataset.id)));
      const add = row.querySelector('.pr-add');
      if (add) add.addEventListener('click', (e) => {
        e.stopPropagation();
        this.addToCart(parseInt(row.dataset.id));
      });
    });
  },

  renderPOSPagination(data) {
    const el = document.getElementById('posPagination');
    const total = data.total;
    const pages = Math.ceil(total / S.pos.limit);
    if (pages <= 1) { el.innerHTML = total > 0 ? `<small>${total} منتج</small>` : ''; return; }
    let html = `<small>${total} منتج • صفحة ${data.page}/${pages}</small>`;
    el.innerHTML = html;
  },

  async onPOSSearchEnter() {
    const input = document.getElementById('posSearch');
    const q = (input.value || '').trim();
    if (!q) return;
    const t0 = performance.now();

    // 1) Try barcode/code lookup (instant) - works for USB/Bluetooth scanners
    try {
      const p = await API.get(`/api/products/by-barcode/${encodeURIComponent(q)}`);
      if (p) {
        S.productCache.set(p.id, p);
        const ok = this.addToCart(p.id);
        if (ok) {
          input.value = '';
          S.pos.q = '';
          this.showScanFeedback(true, p.name, performance.now() - t0);
          this.flashCartItem(p.id);
          // Auto-refocus for the next scan (USB/Bluetooth scanners need this)
          setTimeout(() => { input.focus(); input.select(); }, 30);
        } else {
          this.showScanFeedback(false, 'فشل الإضافة', performance.now() - t0);
        }
        return;
      }
    } catch (e) {
      // Network error - fall through to fuzzy filter
    }

    // 2) Fallback: filter products by name/code/barcode substring
    S.pos.q = q;
    S.pos.page = 1;
    await this.loadPOSProducts();
    input.focus();
  },

  renderQuickQty() {
    const list = (S.settings.quick_qty || '1,5,10,20,30,50,100').split(',').map(s => s.trim()).filter(Boolean);
    document.getElementById('quickQtyBtns').innerHTML = list.map(q =>
      `<button class="quick-qty-btn" data-qty="${q}">${q}</button>`
    ).join('');
    document.querySelectorAll('.quick-qty-btn').forEach(b => {
      b.addEventListener('click', () => this.setQtyToActive(parseFloat(b.dataset.qty)));
    });
  },

  setQtyToActive(qty) {
    if (!S.cart.length) return;
    const last = S.cart[S.cart.length - 1];
    const q = Util.r3(qty);
    if (q <= 0) return;
    const product = S.productCache.get(last.product_id);
    const stock = product ? (parseFloat(product.stock) || 0) : Infinity;
    if (S.invoiceType === 'sale' && q > stock + 0.0000001) {
      this.toast(`المخزون غير كافٍ (متاح: ${Util.r3(stock)})`, 'warning');
      return;
    }
    last.quantity = q;
    last.total = Util.r2(q * last.unit_price);
    this.renderCart();
  },

  setInvoiceType(t) {
    S.invoiceType = t;
    document.querySelectorAll('.cart-tab').forEach(b => b.classList.toggle('active', b.dataset.type === t));
  },

  addToCart(id, qtyDelta = 1) {
    // id: product id
    // qtyDelta: how much to add (default 1; use cartQty() for decrements)
    const p = S.productCache.get(id);
    if (!p) {
      this.toast('المنتج غير موجود', 'error');
      return false;
    }
    const stock = parseFloat(p.stock) || 0;
    const inc = Math.max(0, parseFloat(qtyDelta) || 0);
    const existingIdx = S.cart.findIndex(i => i.product_id === id);
    if (existingIdx >= 0) {
      const existing = S.cart[existingIdx];
      const newQty = existing.quantity + inc;
      if (S.invoiceType === 'sale' && newQty > stock + 0.0001) {
        this.toast(`المخزون غير كافٍ (متاح: ${stock})`, 'warning');
        return false;
      }
      if (newQty <= 0) {
        S.cart.splice(existingIdx, 1);
        this.renderCart();
        return true;
      }
      existing.quantity = Util.r3(newQty);
      existing.total = Util.r2(existing.quantity * existing.unit_price);
      // Incremental DOM update - faster than full re-render
      this.updateCartRow(existingIdx);
      return true;
    }
    if (S.invoiceType === 'sale' && stock <= 0) {
      this.toast('المنتج غير متوفر في المخزون', 'warning');
      return false;
    }
    const price = Util.r2(p.price);
    const qty = inc > 0 ? inc : 1;
    S.cart.push({
      product_id: p.id,
      product_name: p.name,
      barcode: p.barcode || '',
      quantity: Util.r3(qty),
      unit_price: price,
      cost: p.cost || 0,
      total: Util.r2(qty * price),
    });
    // New row - need full render (or append new row)
    this.renderCart();
    return true;
  },

  /**
   * Add a product to the cart by barcode.
   * Fetches from server if not in product cache.
   * Shows transient feedback (✓ / ✗) that auto-dismisses.
   */
  async addToCartByBarcode(code, qty = 1) {
    // Normalize: trim whitespace and control chars
    let clean = (code || '').toString();
    clean = clean.replace(/[\x00-]/g, '').trim();
    if (!clean) {
      this.showScanFeedback(false, 'باركود فارغ');
      return false;
    }

    // 1) Try local cache first (very fast, no network)
    for (const [id, p] of S.productCache.entries()) {
      const pBarcode = (p.barcode || '').trim();
      const pCode = (p.code || '').trim();
      if (pBarcode === clean || pCode === clean) {
        const ok = this.addToCart(id, qty);
        this.showScanFeedback(ok, ok ? p.name : 'فشل الإضافة');
        if (ok) this.flashCartItem(id);
        return ok;
      }
    }

    // 2) Fetch from server
    try {
      const t0 = performance.now();
      const p = await API.get(`/api/products/by-barcode/${encodeURIComponent(clean)}`);
      const elapsed = performance.now() - t0;
      if (p) {
        S.productCache.set(p.id, p);
        const ok = this.addToCart(p.id, qty);
        this.showScanFeedback(ok, ok ? p.name : 'فشل الإضافة', elapsed);
        if (ok) this.flashCartItem(p.id);
        return ok;
      } else {
        this.showScanFeedback(false, 'المنتج غير موجود', elapsed);
        this.openQuickAdd(clean);
        return false;
      }
    } catch (e) {
      this.showScanFeedback(false, e.message || 'خطأ في البحث');
      return false;
    }
  },

  /**
   * Show a transient ✓ / ✗ feedback marker that auto-dismisses after a short delay.
   * Used by barcode scanners to give the user immediate feedback without leaving
   * permanent marks in the UI.
   */
  showScanFeedback(success, label = '', elapsed = null) {
    // Remove any existing feedback
    const old = document.getElementById('scanFeedback');
    if (old) old.remove();
    const fb = document.createElement('div');
    fb.id = 'scanFeedback';
    fb.className = 'scan-feedback ' + (success ? 'ok' : 'err');
    const elapsedTxt = elapsed != null ? ` (${Math.round(elapsed)}ms)` : '';
    fb.innerHTML = (success ? '✓ ' : '✗ ') + label + elapsedTxt;
    document.body.appendChild(fb);
    // Trigger CSS transition
    requestAnimationFrame(() => fb.classList.add('visible'));
    // Auto-remove after 1500ms with fade-out
    setTimeout(() => {
      fb.classList.remove('visible');
      setTimeout(() => fb.remove(), 350);
    }, 1500);
    // Play audio feedback
    try { Util.beep(success ? 1800 : 600, success ? 60 : 200); } catch {}
  },

  /**
   * Briefly highlight a cart item to draw attention after a successful add.
   */
  flashCartItem(productId) {
    requestAnimationFrame(() => {
      const items = document.querySelectorAll('.cart-item');
      items.forEach(el => {
        if (el.dataset.productId == productId) {
          el.classList.add('flash');
          setTimeout(() => el.classList.remove('flash'), 600);
        }
      });
    });
  },

  renderCart() {
    const el = document.getElementById('cartItems');
    const cartCount = document.getElementById('cartCount');
    const totalQty = Util.r3(S.cart.reduce((sum, item) => sum + (parseFloat(item.quantity) || 0), 0));
    if (cartCount) cartCount.textContent = `${S.cart.length} صنف • ${totalQty} وحدة`;
    if (!S.cart.length) {
      el.innerHTML = '<div class="empty-cart">السلة فارغة</div>';
      this.recalcCart();
      return;
    }
    // Build HTML once. Event delegation is handled in init() to avoid
    // attaching listeners on every render.
    el.innerHTML = S.cart.map((it, idx) => {
      const product = S.productCache.get(it.product_id);
      const stock = product ? (parseFloat(product.stock) || 0) : Infinity;
      const stockColor = stock <= 0 ? 'var(--err)' : (stock < it.quantity ? 'var(--warn)' : 'var(--g500)');
      const stockTag = (S.invoiceType === 'sale' && product)
        ? `<small style="color:${stockColor};font-size:11px">المخزون: ${stock}</small>`
        : '';
      return `
      <div class="cart-item" data-product-id="${it.product_id}" data-idx="${idx}">
        <div class="cart-item-info">
          <div class="cart-item-name">${Util.esc(it.product_name)}</div>
          <div class="cart-item-price">${Util.money(it.unit_price)} × ${it.quantity} = <strong>${Util.money(it.total)}</strong>${stockTag}</div>
          ${it.barcode ? `<div class="cart-item-barcode" style="font-family:monospace;font-size:10px;color:var(--g500)">${Util.esc(it.barcode)}</div>` : ''}
        </div>
        <div class="cart-item-controls">
          <button data-act="dec" data-idx="${idx}" title="إنقاص">−</button>
          <input type="number" class="qty-input" value="${it.quantity}" min="0.001" step="0.001" data-idx="${idx}">
          <button data-act="inc" data-idx="${idx}" title="زيادة">+</button>
          <button data-act="rm" data-idx="${idx}" title="حذف" style="color:var(--err)">✕</button>
        </div>
      </div>
    `;
    }).join('');
    this.recalcCart();
  },

  /**
   * Lightweight update: only refresh the row corresponding to `idx` in the cart.
   * Used when the cart item already exists (avoids full re-render).
   * Falls back to full renderCart() if the row can't be found.
   */
  updateCartRow(idx) {
    const it = S.cart[idx];
    if (!it) { this.renderCart(); return; }
    const row = document.querySelector(`.cart-item[data-idx="${idx}"]`);
    if (!row) { this.renderCart(); return; }
    const product = S.productCache.get(it.product_id);
    const stock = product ? (parseFloat(product.stock) || 0) : Infinity;
    const stockColor = stock <= 0 ? 'var(--err)' : (stock < it.quantity ? 'var(--warn)' : 'var(--g500)');
    const stockTag = (S.invoiceType === 'sale' && product)
      ? `<small style="color:${stockColor};font-size:11px">المخزون: ${stock}</small>`
      : '';
    row.querySelector('.cart-item-name').textContent = it.product_name;
    row.querySelector('.cart-item-price').innerHTML =
      `${Util.money(it.unit_price)} × ${it.quantity} = <strong>${Util.money(it.total)}</strong>${stockTag}`;
    const qtyInput = row.querySelector('input.qty-input');
    if (qtyInput && document.activeElement !== qtyInput) {
      qtyInput.value = it.quantity;
    }
    this.recalcCart();
  },

  /**
   * Adjust cart item quantity by `delta` (typically +1 or -1).
   * - Never goes below 1 (the item is removed if it would hit 0).
   * - For sale invoices, never exceeds available stock.
   * Uses incremental DOM update for performance.
   */
  cartQty(idx, delta) {
    const it = S.cart[idx];
    if (!it) return;
    const product = S.productCache.get(it.product_id);
    const stock = product ? (parseFloat(product.stock) || 0) : Infinity;
    let newQty = (parseFloat(it.quantity) || 0) + (parseFloat(delta) || 0);
    newQty = Util.r3(newQty);
    if (newQty <= 0) {
      S.cart.splice(idx, 1);
      this.renderCart();
      return;
    }
    if (S.invoiceType === 'sale' && newQty > stock + 0.0001) {
      this.toast(`المخزون غير كافٍ (متاح: ${stock})`, 'warning');
      return;
    }
    it.quantity = Util.r3(newQty);
    it.total = Util.r2(it.quantity * it.unit_price);
    this.updateCartRow(idx);
  },

  /**
   * Set the absolute quantity for a cart item (from input change).
   * Clamps to stock if sale, removes item if <= 0.
   */
  setCartQty(idx, val) {
    const it = S.cart[idx];
    if (!it) return;
    let q = parseFloat(val);
    if (isNaN(q)) q = 0;
    q = Util.r3(q);
    if (q <= 0) {
      S.cart.splice(idx, 1);
      this.renderCart();
      return;
    }
    const product = S.productCache.get(it.product_id);
    const stock = product ? (parseFloat(product.stock) || 0) : Infinity;
    if (S.invoiceType === 'sale' && q > stock + 0.0001) {
      this.toast(`المخزون غير كافٍ (متاح: ${stock})`, 'warning');
      // Re-render to reset input value to current quantity
      this.renderCart();
      return;
    }
    it.quantity = Util.r3(q);
    it.total = Util.r2(it.quantity * it.unit_price);
    this.renderCart();
  },

  cartRemove(idx) { S.cart.splice(idx, 1); this.renderCart(); },

  async clearCart() {
    if (S.cart.length && !await this.confirm('إفراغ السلة', 'هل تريد إفراغ السلة؟')) return;
    S.cart = [];
    S.cartCustomer = null;
    document.getElementById('cartDiscount').value = 0;
    document.getElementById('customerSearch').value = '';
    document.getElementById('customerResults').classList.remove('show');
    document.getElementById('selectedCustomer').style.display = 'none';
    this.renderCart();
  },

  recalcCart() {
    const subtotal = Util.r2(S.cart.reduce((s, i) => s + (parseFloat(i.total) || 0), 0));
    const discountPct = parseFloat(document.getElementById('cartDiscount').value) || 0;
    const discount = Util.r2(subtotal * discountPct / 100);
    const afterDisc = Util.r2(subtotal - discount);
    const vatEnabled = !!S.settings.vat_enabled;
    const taxRate = vatEnabled ? (parseFloat(S.settings.tax_rate) || 0) : 0;
    const tax = Util.r2(afterDisc * taxRate / 100);
    const total = Util.r2(afterDisc + tax);
    document.getElementById('cartSubtotal').textContent = Util.money(subtotal);
    document.getElementById('cartTax').textContent = Util.money(tax);
    document.getElementById('cartTotal').textContent = Util.money(total);
    const taxRow = document.getElementById('taxRow');
    if (taxRate > 0) { taxRow.style.display = 'flex'; document.getElementById('taxRateLabel').textContent = `(${taxRate}%)`; }
    else { taxRow.style.display = 'none'; }
  },

  /* ─── CUSTOMER in POS ─── */
  async searchCustomer(q) {
    const res = document.getElementById('customerResults');
    if (!q) { res.classList.remove('show'); res.innerHTML = ''; return; }
    try {
      const data = await API.get(`/api/customers?q=${encodeURIComponent(q)}&limit=8`);
      if (!data.items.length) { res.classList.remove('show'); return; }
      res.innerHTML = data.items.map(c => `
        <div class="customer-result-item" data-id="${c.id}">
          <strong>${Util.esc(c.name)}</strong>
          <span class="cr-phone">${Util.esc(c.phone || '')}</span>
        </div>
      `).join('');
      res.classList.add('show');
      res.querySelectorAll('.customer-result-item').forEach(it => {
        it.addEventListener('click', () => this.selectCustomer(parseInt(it.dataset.id)));
      });
    } catch (e) { console.error(e); }
  },

  selectCustomer(id) {
    const c = S.customerCache.get(id);
    if (!c) {
      // fetch and cache
      this.fetchCustomer(id);
      return;
    }
    S.cartCustomer = id;
    S.customerCache.set(id, c);
    document.getElementById('customerSearch').value = '';
    document.getElementById('customerResults').classList.remove('show');
    document.getElementById('selectedCustomer').style.display = 'flex';
    document.getElementById('selCustName').textContent = c.name;
    document.getElementById('selCustPhone').textContent = c.phone || '';
    document.getElementById('selCustBalance').textContent = `الرصيد: ${Util.money(c.balance || 0)}`;
  },

  async fetchCustomer(id) {
    try {
      const c = await API.get(`/api/customers/${id}`);
      S.customerCache.set(c.id, c);
      this.selectCustomer(c.id);
    } catch (e) { console.error(e); }
  },

  clearCustomer() {
    S.cartCustomer = null;
    document.getElementById('selectedCustomer').style.display = 'none';
  },

  /* ─── CHECKOUT ─── */
  async checkout(method) {
    if (!S.cart.length) { this.toast('السلة فارغة', 'warning'); return; }
    // Credit/partial sales require a customer
    if ((method === 'credit' || method === 'partial') && !S.cartCustomer) {
      this.toast('يجب اختيار عميل للفاتورة الآجلة أو الجزئية', 'warning');
      document.getElementById('customerSearch').focus();
      return;
    }
    if ((method === 'cash') && !S.cartCustomer) {
      if (!await this.confirm('بدون عميل', 'لم تختر عميل. سيتم تسجيل الفاتورة كفاتورة نقدية. متابعة؟')) return;
    }
    if (method === 'partial') { this.openPartial(); return; }
    await this.completeCheckout(method, null, null);
  },

  openPartial() {
    if (!S.cart.length) { this.toast('السلة فارغة', 'warning'); return; }
    const total = parseFloat(document.getElementById('cartTotal').textContent);
    document.getElementById('ptTotal').value = total.toFixed(2);
    document.getElementById('ptPaid').value = '';
    document.getElementById('ptRemain').value = total.toFixed(2);
    document.getElementById('partialModal').classList.add('active');
  },

  async confirmPartial() {
    const paid = parseFloat(document.getElementById('ptPaid').value) || 0;
    const total = parseFloat(document.getElementById('ptTotal').value) || 0;
    if (paid <= 0 || paid >= total - 0.001) { this.toast('الدفع الجزئي يجب أن يكون أكبر من صفر وأقل من إجمالي الفاتورة', 'warning'); return; }
    const remaining = Math.max(0, total - paid);
    this.closeModal('partialModal');
    await this.completeCheckout('partial', paid, remaining);
  },

  async completeCheckout(method, paidOverride, remainingOverride) {
    const subtotal = Util.r2(S.cart.reduce((s, i) => s + (parseFloat(i.total) || 0), 0));
    const discountPct = parseFloat(document.getElementById('cartDiscount').value) || 0;
    const discount = Util.r2(subtotal * discountPct / 100);
    const afterDisc = Util.r2(subtotal - discount);
    const vatEnabled = !!S.settings.vat_enabled;
    const taxRate = vatEnabled ? (parseFloat(S.settings.tax_rate) || 0) : 0;
    const tax = Util.r2(afterDisc * taxRate / 100);
    const total = Util.r2(afterDisc + tax);
    // Compute paid/remaining based on method
    let paid, remaining;
    if (paidOverride !== null) {
      paid = Util.r2(paidOverride);
      remaining = Util.r2(Math.max(0, total - paid));
    } else if (method === 'credit') {
      paid = 0;
      remaining = total;
    } else {
      // cash
      paid = total;
      remaining = 0;
    }
    if (remainingOverride !== null) remaining = Util.r2(Math.max(0, remainingOverride));

    const payload = {
      customer_id: S.cartCustomer,
      customer_name: '',
      type: 'sale',
      discount_pct: discountPct,
      paid,
      payment_method: method,
      items: S.cart.map(i => ({ product_id: i.product_id, quantity: i.quantity })),
    };

    try {
      const r = await API.post('/api/invoices', payload);
      this.toast(`تم ${S.invoiceType === 'sale' ? 'البيع' : 'المرتجع'} #${r.number} - ${Util.money(total)}`);

      // Print logic: auto-print if setting enabled, else ask
      const autoPrint = S.settings.auto_print_after_sale;
      if (autoPrint) {
        await this.printInvoiceById(r.id);
      } else if (await this.confirm('طباعة الفاتورة', 'هل تريد طباعة الفاتورة الآن؟')) {
        await this.printInvoiceById(r.id);
      }
      // Reset cart
      S.cart = [];
      S.cartCustomer = null;
      document.getElementById('cartDiscount').value = 0;
      document.getElementById('selectedCustomer').style.display = 'none';
      document.getElementById('customerSearch').value = '';
      this.renderCart();
      await this.loadPOSProducts();
    } catch (e) {
      this.toast('فشل: ' + e.message, 'error');
    }
  },
};
