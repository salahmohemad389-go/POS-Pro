import { S } from './state.js';
import { Util } from './util.js';

let unauthorizedHandler = null;
export function setUnauthorizedHandler(fn) { unauthorizedHandler = fn; }

export const API = {
  base: '',
  _isUnauthorized: false,
  async request(method, url, body = null, options = {}) {
    const headers = {};
    if (options.headers) Object.assign(headers, options.headers);
    const opts = { method, headers, credentials: 'same-origin' };
    if (body instanceof FormData) opts.body = body;
    else if (body && method !== 'GET') { headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    const resp = (method === 'GET' && !body && options.dedupe !== false)
      ? await Util.dedupedFetch(this.base + url, opts)
      : await fetch(this.base + url, opts);
    if (resp.status === 401 && !this._isUnauthorized && !url.includes('/auth/')) {
      this._isUnauthorized = true;
      try { if (unauthorizedHandler) unauthorizedHandler(); } finally {
        setTimeout(() => { this._isUnauthorized = false; }, 2000);
      }
      throw new Error('غير مصرح');
    }
    if (!resp.ok) {
      let err = 'خطأ';
      try { const data = await resp.json(); err = data.detail || err; } catch {}
      throw new Error(err);
    }
    const ct = resp.headers.get('content-type') || '';
    return ct.includes('application/json') ? resp.json() : resp;
  },
  get(url, opts) { return this.request('GET', url, null, opts || { dedupe: true }); },
  post(url, body) { return this.request('POST', url, body); },
  put(url, body) { return this.request('PUT', url, body); },
  delete(url) { return this.request('DELETE', url); },
};
