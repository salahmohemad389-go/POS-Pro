(() => {
  'use strict';

  const endpoint = '/api/client-error';

  async function report(payload) {
    try {
      await fetch(endpoint, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kind: String(payload.kind || '').slice(0, 80),
          source: String(payload.source || '').slice(0, 300),
          line: String(payload.line || '').slice(0, 20),
          col: String(payload.col || '').slice(0, 20),
          message: String(payload.message || '').slice(0, 1000),
        }),
      });
    } catch (_) {}
  }

  window.addEventListener('error', (event) => {
    const targetSrc = event && event.target && event.target.src ? event.target.src : '';
    report({
      kind: 'window-error',
      source: event.filename || targetSrc || '',
      line: event.lineno || '',
      col: event.colno || '',
      message: event.message || (targetSrc ? 'script load/evaluation error' : 'unknown error'),
    });
  }, true);

  window.addEventListener('unhandledrejection', (event) => {
    const reason = event && event.reason;
    report({
      kind: 'unhandledrejection',
      source: '',
      message: reason && reason.message ? reason.message : String(reason || 'unknown rejection'),
    });
  });

  const modules = [
    '/static/js/core/state.js',
    '/static/js/core/util.js',
    '/static/js/core/api.js',
    '/static/js/pages/pos.js',
    '/static/js/pages/products.js',
    '/static/js/pages/suppliers.js',
    '/static/js/pages/customers.js',
    '/static/js/pages/invoices.js',
    '/static/js/pages/reports.js',
    '/static/js/pages/users.js',
    '/static/js/pages/settings.js',
    '/static/js/pages/audit.js',
    '/static/js/pages/quick_add.js',
  ];

  async function diagnoseModuleGraph() {
    for (const source of modules) {
      try {
        await import(source + '?diag=1');
      } catch (error) {
        await report({
          kind: 'module-import',
          source,
          message: error && error.message ? error.message : String(error),
        });
        const err = document.getElementById('loginError');
        if (err) {
          err.textContent = 'تعذر تشغيل واجهة البرنامج. تم إرسال التشخيص تلقائياً.';
          err.style.display = 'block';
        }
        return;
      }
    }

    try {
      await import('/static/app.js?diag=1');
      await report({ kind: 'diag-complete', source: '/static/app.js', message: 'module graph imported successfully' });
    } catch (error) {
      await report({
        kind: 'app-import',
        source: '/static/app.js',
        message: error && error.message ? error.message : String(error),
      });
      const err = document.getElementById('loginError');
      if (err) {
        err.textContent = 'تعذر تشغيل واجهة البرنامج. تم إرسال التشخيص تلقائياً.';
        err.style.display = 'block';
      }
    }
  }

  diagnoseModuleGraph();
})();