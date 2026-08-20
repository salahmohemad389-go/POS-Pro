/* Barcode UX: keyboard-wedge scanners first, camera fallback second. */
(() => {
  'use strict';

  let cameraStream = null;
  let cameraTimer = null;
  let scannerStartedAt = 0;
  let scannerLastAt = 0;
  let scannerKeyCount = 0;
  let scannerAutoTimer = null;

  const byId = id => document.getElementById(id);

  function stopCamera() {
    if (cameraTimer) { clearTimeout(cameraTimer); cameraTimer = null; }
    if (cameraStream) {
      cameraStream.getTracks().forEach(track => track.stop());
      cameraStream = null;
    }
    const modal = byId('barcodeCameraModal');
    if (modal) modal.classList.remove('active');
    const video = byId('barcodeCameraVideo');
    if (video) video.srcObject = null;
  }

  function markHardwareScannerDetected() {
    try { sessionStorage.setItem('pos_hardware_barcode_detected', '1'); } catch (_) {}
    const button = byId('posCameraScanBtn');
    if (button) button.hidden = true;
  }

  function hardwareScannerDetected() {
    try { return sessionStorage.getItem('pos_hardware_barcode_detected') === '1'; }
    catch (_) { return false; }
  }

  function ensureCameraModal() {
    if (byId('barcodeCameraModal')) return;
    const modal = document.createElement('div');
    modal.id = 'barcodeCameraModal';
    modal.className = 'barcode-camera-modal';
    modal.innerHTML = `
      <div class="barcode-camera-card" role="dialog" aria-modal="true" aria-label="قراءة الباركود بالكاميرا">
        <div class="barcode-camera-head">
          <strong>قراءة الباركود بالكاميرا</strong>
          <button type="button" id="barcodeCameraClose" class="barcode-camera-close" aria-label="إغلاق">×</button>
        </div>
        <div class="barcode-camera-stage">
          <video id="barcodeCameraVideo" autoplay playsinline muted></video>
          <div class="barcode-camera-guide" aria-hidden="true"></div>
        </div>
        <div id="barcodeCameraStatus" class="barcode-camera-status">وجّه الكاميرا نحو الباركود</div>
      </div>`;
    document.body.appendChild(modal);
    byId('barcodeCameraClose')?.addEventListener('click', stopCamera);
    modal.addEventListener('click', event => { if (event.target === modal) stopCamera(); });
  }

  function ensureStyles() {
    if (byId('barcodeUxStyle')) return;
    const style = document.createElement('style');
    style.id = 'barcodeUxStyle';
    style.textContent = `
      .pos-search{display:flex;align-items:center;gap:8px}
      .pos-search #posSearch{flex:1;min-width:0}
      #posCameraScanBtn{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-width:44px;height:42px;padding:0 12px;border:1px solid var(--g200);border-radius:10px;background:var(--card);color:var(--g700);cursor:pointer}
      #posCameraScanBtn:hover{border-color:var(--p);color:var(--p)}
      #posCameraScanBtn svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
      #posCameraScanBtn[hidden]{display:none!important}
      .barcode-camera-modal{position:fixed;inset:0;z-index:99999;display:none;align-items:center;justify-content:center;padding:18px;background:rgba(15,23,42,.72)}
      .barcode-camera-modal.active{display:flex}
      .barcode-camera-card{width:min(560px,96vw);background:var(--card,#fff);border-radius:16px;overflow:hidden;box-shadow:0 24px 70px rgba(0,0,0,.35)}
      .barcode-camera-head{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;border-bottom:1px solid var(--g200)}
      .barcode-camera-close{border:0;background:transparent;font-size:28px;line-height:1;cursor:pointer;color:var(--g600)}
      .barcode-camera-stage{position:relative;background:#020617;aspect-ratio:4/3;overflow:hidden}
      .barcode-camera-stage video{width:100%;height:100%;object-fit:cover}
      .barcode-camera-guide{position:absolute;left:10%;right:10%;top:37%;height:26%;border:2px solid rgba(255,255,255,.9);border-radius:12px;box-shadow:0 0 0 999px rgba(0,0,0,.12)}
      .barcode-camera-status{padding:12px 14px;text-align:center;font-size:13px;color:var(--g600)}
      @media(max-width:640px){#posCameraScanBtn span{display:none}#posCameraScanBtn{padding:0 11px}}
    `;
    document.head.appendChild(style);
  }

  function removeLegacyOptionalInvoiceFields() {
    document.querySelectorAll('.invoice-optional-meta').forEach(el => el.remove());
  }

  function submitBarcode(code) {
    const input = byId('posSearch');
    if (!input) return;
    input.value = String(code || '').trim();
    if (!input.value) return;
    input.focus();
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }));
  }

  async function startCamera() {
    ensureCameraModal();
    const modal = byId('barcodeCameraModal');
    const video = byId('barcodeCameraVideo');
    const status = byId('barcodeCameraStatus');
    modal?.classList.add('active');

    if (!navigator.mediaDevices?.getUserMedia) {
      if (status) status.textContent = 'المتصفح لا يسمح باستخدام الكاميرا هنا.';
      return;
    }
    if (!('BarcodeDetector' in window)) {
      if (status) status.textContent = 'هذا المتصفح لا يدعم قراءة الباركود بالكاميرا. استخدم Chrome حديث أو قارئ USB/Bluetooth.';
      return;
    }

    try {
      const supported = typeof BarcodeDetector.getSupportedFormats === 'function'
        ? await BarcodeDetector.getSupportedFormats()
        : [];
      const preferred = ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'code_39', 'itf', 'codabar', 'qr_code'];
      const formats = supported.length ? preferred.filter(f => supported.includes(f)) : preferred;
      const detector = formats.length ? new BarcodeDetector({ formats }) : new BarcodeDetector();
      cameraStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      video.srcObject = cameraStream;
      await video.play();
      if (status) status.textContent = 'وجّه الكاميرا نحو الباركود';

      const scanFrame = async () => {
        if (!cameraStream || !video || video.readyState < 2) {
          cameraTimer = setTimeout(scanFrame, 140);
          return;
        }
        try {
          const results = await detector.detect(video);
          const raw = String(results?.[0]?.rawValue || '').trim();
          if (raw) {
            if (status) status.textContent = `تمت القراءة: ${raw}`;
            stopCamera();
            submitBarcode(raw);
            return;
          }
        } catch (_) {}
        cameraTimer = setTimeout(scanFrame, 120);
      };
      scanFrame();
    } catch (err) {
      if (status) {
        status.textContent = err?.name === 'NotAllowedError'
          ? 'تم رفض إذن الكاميرا. اسمح للمتصفح باستخدامها ثم حاول مرة أخرى.'
          : 'تعذر تشغيل الكاميرا.';
      }
      if (cameraStream) { cameraStream.getTracks().forEach(track => track.stop()); cameraStream = null; }
    }
  }

  function installScannerDetection(input) {
    if (!input || input.dataset.barcodeUxBound === '1') return;
    input.dataset.barcodeUxBound = '1';

    input.addEventListener('keydown', event => {
      const now = performance.now();
      if (event.key === 'Enter') {
        clearTimeout(scannerAutoTimer);
        const elapsed = scannerStartedAt ? now - scannerStartedAt : Infinity;
        const average = scannerKeyCount > 1 ? elapsed / (scannerKeyCount - 1) : Infinity;
        if (input.value.trim().length >= 4 && scannerKeyCount >= 4 && average <= 70) {
          markHardwareScannerDetected();
        }
        scannerStartedAt = 0; scannerLastAt = 0; scannerKeyCount = 0;
        return;
      }
      if (event.ctrlKey || event.altKey || event.metaKey || event.key.length !== 1) return;
      const gap = scannerLastAt ? now - scannerLastAt : Infinity;
      if (!scannerStartedAt || gap > 120) {
        scannerStartedAt = now;
        scannerKeyCount = 1;
      } else {
        scannerKeyCount += 1;
      }
      scannerLastAt = now;
      clearTimeout(scannerAutoTimer);
      scannerAutoTimer = setTimeout(() => {
        const end = performance.now();
        const elapsed = scannerStartedAt ? scannerLastAt - scannerStartedAt : Infinity;
        const average = scannerKeyCount > 1 ? elapsed / (scannerKeyCount - 1) : Infinity;
        const value = input.value.trim();
        // Some scanners are configured without an Enter suffix. A fast burst is
        // treated as a completed scan, while normal human typing is left alone.
        if (value.length >= 5 && scannerKeyCount >= 5 && average <= 45 && end - scannerLastAt >= 55) {
          markHardwareScannerDetected();
          submitBarcode(value);
        }
        scannerStartedAt = 0; scannerLastAt = 0; scannerKeyCount = 0;
      }, 70);
    }, true);
  }

  function install() {
    ensureStyles();
    removeLegacyOptionalInvoiceFields();

    const search = byId('posSearch');
    const host = search?.closest('.pos-search');
    if (search) {
      search.placeholder = 'بحث بالاسم / الباركود / الكود...';
      search.autocomplete = 'off';
      installScannerDetection(search);
    }
    if (host && !byId('posCameraScanBtn')) {
      const button = document.createElement('button');
      button.id = 'posCameraScanBtn';
      button.type = 'button';
      button.title = 'قراءة الباركود بالكاميرا';
      button.setAttribute('aria-label', 'قراءة الباركود بالكاميرا');
      button.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-2M7 9v6M10 9v6M13 9v6M17 9v6"/></svg><span>كاميرا</span>`;
      button.hidden = hardwareScannerDetected();
      button.addEventListener('click', startCamera);
      host.appendChild(button);
    }

    const customerHost = document.querySelector('.cart-customer');
    if (customerHost && !customerHost.dataset.noOptionalMetaObserver) {
      customerHost.dataset.noOptionalMetaObserver = '1';
      new MutationObserver(removeLegacyOptionalInvoiceFields).observe(customerHost, { childList: true });
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();

  window.addEventListener('pagehide', stopCamera);
})();
