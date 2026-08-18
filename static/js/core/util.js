import { S } from './state.js';

export const Util = {
  esc(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
  },
  r2(n) { return Math.round((parseFloat(n) || 0) * 100) / 100; },
  r3(n) { return Math.round((parseFloat(n) || 0) * 1000) / 1000; },
  invLabel(type) { return type === 'sale' ? 'بيع' : type === 'combined' ? 'مجمعة' : 'مرتجع'; },
  invBadgeClass(type) { return type === 'sale' ? 'badge-success' : type === 'combined' ? 'badge-info' : 'badge-warning'; },
  // In-flight request cache: deduplicate simultaneous identical GETs
  _inFlight: new Map(),
  _memo: new Map(),

  /**
   * Deduplicated async fetch: if an identical request is already in-flight,
   * return the same Promise instead of issuing another network call.
   * Prevents spam behavior when user double-clicks or multiple UI parts
   * request the same data at once.
   */
  async dedupedFetch(url, opts) {
    const key = url + '|' + JSON.stringify(opts || {});
    const existing = this._inFlight.get(key);
    if (existing) return existing;
    const p = fetch(url, opts).then((r) => {
      setTimeout(() => this._inFlight.delete(key), 50);
      return r;
    }).catch((e) => {
      this._inFlight.delete(key);
      throw e;
    });
    this._inFlight.set(key, p);
    return p;
  },

  /**
   * Short-lived memoization for derived data. Called at most once per ttl ms.
   */
  memo(key, ttl, compute) {
    const entry = this._memo.get(key);
    const now = Date.now();
    if (entry && now - entry.t < ttl) return entry.v;
    const v = compute();
    this._memo.set(key, { v, t: now });
    if (this._memo.size > 200) {
      for (const [k, e] of this._memo.entries()) {
        if (now - e.t > ttl * 5) this._memo.delete(k);
      }
    }
    return v;
  },

    money(n) { return this.r2(n).toFixed(2) + ' ' + (S.settings.currency || 'ج.م'); },
  date(ts) {
    if (!ts) return '-';
    const d = new Date(ts);
    const p = n => String(n).padStart(2, '0');
    return `${p(d.getDate())}/${p(d.getMonth()+1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
  },
  shortDate(ts) {
    if (!ts) return '-';
    const d = new Date(ts);
    const p = n => String(n).padStart(2, '0');
    return `${p(d.getDate())}/${p(d.getMonth()+1)}/${d.getFullYear()}`;
  },
  debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  },
  // Generate a beep using Web Audio API (no audio file needed)
  beep(freq = 1800, duration = 80) {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      const ctx = new Ctx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = freq;
      osc.type = 'sine';
      gain.gain.setValueAtTime(0.3, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration / 1000);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + duration / 1000);
      setTimeout(() => ctx.close().catch(() => {}), duration + 50);
    } catch (e) { /* ignore */ }
  },
  // Build a DOM element safely (XSS-safe for user content)
  el(tag, attrs = {}, children = []) {
    const e = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === 'class') e.className = v;
      else if (k === 'text') e.textContent = v;
      else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
      else if (v != null) e.setAttribute(k, v);
    });
    (Array.isArray(children) ? children : [children]).forEach(c => {
      if (c == null) return;
      e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return e;
  },
};
