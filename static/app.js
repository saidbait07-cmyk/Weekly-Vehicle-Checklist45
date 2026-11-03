(() => {
  const connection = document.getElementById('connection');
  const offlineBadge = document.getElementById('offline-indicator');
  const queuePanel = document.getElementById('offline-queue-panel');
  const queueCountEl = document.getElementById('offline-queue-count');
  const manualSyncBtn = document.getElementById('manual-sync-btn');

  const updateNetwork = () => {
    const online = navigator.onLine;
    if (connection) {
      connection.textContent = online ? 'Online' : 'Offline Mode';
      connection.style.color = online ? '#86efac' : '#fde047';
    }
    if (offlineBadge) {
      offlineBadge.textContent = online ? 'Online' : 'Offline Mode';
      offlineBadge.className = `status-text ${online ? 'status-good' : 'status-warn'}`;
    }
  };

  addEventListener('online', () => {
    updateNetwork();
    syncQueue();
  });
  addEventListener('offline', updateNetwork);
  updateNetwork();

  // Propagate signed session token (_st) across forms if third-party iframe cookies are blocked
  const urlParams = new URLSearchParams(window.location.search);
  const iframeSessionToken = urlParams.get('_st') || '';
  if (iframeSessionToken) {
    document.querySelectorAll('form').forEach((formEl) => {
      if (!formEl.querySelector('input[name="_st"]')) {
        const hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = '_st';
        hidden.value = iframeSessionToken;
        formEl.appendChild(hidden);
      }
    });
  }

  // Password visibility toggle on login
  document.querySelectorAll('.toggle-password').forEach((button) => {
    button.addEventListener('click', () => {
      const input = button.parentElement.querySelector('input');
      if (input) {
        input.type = input.type === 'password' ? 'text' : 'password';
      }
    });
  });

  // Quick demo credential fill buttons on login
  document.querySelectorAll('.demo-fill-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const eidInput = document.getElementById('login-eid');
      const pwInput = document.getElementById('login-pw');
      if (eidInput && pwInput) {
        eidInput.value = btn.dataset.eid || '';
        pwInput.value = btn.dataset.pw || '';
      }
    });
  });

  // Supervisor Dashboard Tabs
  document.querySelectorAll('.tab-btn[data-tab-target]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetId = btn.dataset.tabTarget;
      document.querySelectorAll('.tab-btn[data-tab-target]').forEach((b) => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach((pane) => {
        pane.hidden = pane.id !== targetId;
        pane.classList.toggle('active', pane.id === targetId);
      });
      btn.classList.add('active');
    });
  });

  // PWA In-App Install Prompt
  let deferredInstallPrompt = null;
  const installBtn = document.getElementById('pwa-install-btn');
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredInstallPrompt = e;
    if (installBtn) installBtn.hidden = false;
  });
  installBtn?.addEventListener('click', async () => {
    if (!deferredInstallPrompt) return;
    await deferredInstallPrompt.prompt();
    await deferredInstallPrompt.userChoice;
    deferredInstallPrompt = null;
    installBtn.hidden = true;
  });

  // Clear cached private inspection pages on sign-out
  document.querySelector('form[action$="/logout"]')?.addEventListener('submit', () => {
    navigator.serviceWorker?.controller?.postMessage({ type: 'CLEAR_PRIVATE_CACHE' });
  });

  // IndexedDB Offline Inspection Queue
  function openDb() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open('fleet-offline-v1', 1);
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains('queue')) {
          request.result.createObjectStore('queue', { keyPath: 'key' });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async function saveQueue(item) {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('queue', 'readwrite');
      tx.objectStore('queue').put(item);
      tx.oncomplete = () => {
        refreshQueueIndicator();
        resolve();
      };
      tx.onerror = () => reject(tx.error);
    });
  }

  async function getQueue() {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const request = db.transaction('queue').objectStore('queue').getAll();
      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => reject(request.error);
    });
  }

  async function removeQueue(key) {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('queue', 'readwrite');
      tx.objectStore('queue').delete(key);
      tx.oncomplete = () => {
        refreshQueueIndicator();
        resolve();
      };
      tx.onerror = () => reject(tx.error);
    });
  }

  async function refreshQueueIndicator() {
    try {
      const q = await getQueue();
      if (queuePanel && queueCountEl) {
        queuePanel.hidden = q.length === 0;
        queueCountEl.textContent = `${q.length} offline inspection(s) queued in IndexedDB`;
      }
    } catch (_) {}
  }

  async function syncQueue() {
    await refreshQueueIndicator();
    if (!navigator.onLine || !document.querySelector('form[action$="/logout"]')) return;
    let queue;
    try {
      queue = await getQueue();
    } catch (_) {
      return;
    }
    for (const item of queue) {
      try {
        const freshToken = document.querySelector('input[name="csrf"]')?.value || item.csrf;
        const headers = { 'Content-Type': 'application/json', 'X-CSRF-Token': freshToken };
        if (iframeSessionToken) {
          headers['X-Session-Token'] = iframeSessionToken;
        }
        const response = await fetch(item.url, {
          method: 'POST',
          credentials: 'same-origin',
          headers,
          body: JSON.stringify(item.payload),
        });
        if (!response.ok) break;
        const resJson = await response.json();
        await removeQueue(item.key);
        const message = document.getElementById('sync-message');
        if (message) {
          message.textContent = resJson.duplicate
            ? 'Queued inspection already existed on server (duplicate prevented).'
            : 'Offline inspection synced to server.';
        }
      } catch (_) {
        break;
      }
    }
  }

  manualSyncBtn?.addEventListener('click', () => syncQueue());

  // Expose helper on window for programmatic testing of offline queue
  window.__fleetOfflineQueue = { saveQueue, getQueue, removeQueue, syncQueue };

  // Daily Inspection Form Logic
  const form = document.querySelector('.inspection-form');
  if (!form) {
    syncQueue();
    return;
  }

  const updateSummaryCounters = () => {
    const radios = form.querySelectorAll('input[type="radio"]:checked');
    let passCount = 0;
    let failCount = 0;
    let naCount = 0;
    radios.forEach((r) => {
      if (r.value === 'pass') passCount++;
      else if (r.value === 'fail') failCount++;
      else if (r.value === 'na') naCount++;
    });
    const elPass = document.getElementById('sum-pass');
    const elFail = document.getElementById('sum-fail');
    const elNa = document.getElementById('sum-na');
    const elFinal = document.getElementById('live-final-status');
    if (elPass) elPass.textContent = String(passCount);
    if (elFail) elFail.textContent = String(failCount);
    if (elNa) elNa.textContent = String(naCount);
    if (elFinal) {
      if (failCount > 0) {
        elFinal.textContent = `Failed (${failCount} Fault${failCount > 1 ? 's' : ''} Recorded)`;
        elFinal.className = 'final-status-banner status-bad';
      } else {
        elFinal.textContent = `Passed (${passCount} OK)`;
        elFinal.className = 'final-status-banner status-good';
      }
    }
  };

  form.addEventListener('change', (e) => {
    const target = e.target;
    if (target && target.classList?.contains('point-checkbox')) {
      const itemId = target.dataset.itemId;
      const radios = form.querySelectorAll(`input[type="radio"][name="item_${itemId}"]`);
      if (target.checked) {
        const anyChecked = Array.from(radios).some((r) => r.checked);
        if (!anyChecked && radios[0]) {
          radios[0].checked = true;
        }
      } else {
        radios.forEach((r) => {
          r.checked = false;
        });
      }
    } else if (target && target.type === 'radio' && target.name?.startsWith('item_')) {
      const itemId = target.name.replace('item_', '');
      const cb = form.querySelector(`.point-checkbox[data-item-id="${itemId}"]`);
      if (cb) cb.checked = true;
    }
    updateSummaryCounters();
  });

  // Mark All OK helper button
  document.getElementById('mark-all-ok-btn')?.addEventListener('click', () => {
    form.querySelectorAll('input[type="radio"][value="pass"]').forEach((r) => {
      r.checked = true;
    });
    form.querySelectorAll('.point-checkbox').forEach((cb) => {
      cb.checked = true;
    });
    updateSummaryCounters();
  });

  // Photo upload client preview
  const photoInput = document.getElementById('photo-input');
  const previewGrid = document.getElementById('photo-preview-grid');
  photoInput?.addEventListener('change', () => {
    if (!previewGrid) return;
    previewGrid.innerHTML = '';
    const files = Array.from(photoInput.files || []).slice(0, 6);
    files.forEach((file) => {
      const img = document.createElement('img');
      img.className = 'photo-preview-item';
      img.alt = file.name;
      img.src = URL.createObjectURL(file);
      previewGrid.appendChild(img);
    });
  });

  // Restore saved local draft
  const draftKey = `fleet-draft-${form.dataset.vehicle}`;
  const savedDraft = localStorage.getItem(draftKey);
  if (savedDraft) {
    try {
      const data = JSON.parse(savedDraft);
      for (const [name, value] of Object.entries(data)) {
        const element = form.elements[name];
        if (!element) continue;
        if (element instanceof RadioNodeList || (element.length && !element.type)) {
          [...element].forEach((option) => {
            if (option.value === value) option.checked = true;
          });
        } else if (element.type === 'checkbox') {
          element.checked = value === element.value;
        } else {
          element.value = value;
        }
      }
      updateSummaryCounters();
    } catch (_) {
      localStorage.removeItem(draftKey);
    }
  }

  document.getElementById('save-draft')?.addEventListener('click', () => {
    const values = {};
    for (const [key, value] of new FormData(form).entries()) {
      if (typeof value === 'string') values[key] = value;
    }
    localStorage.setItem(draftKey, JSON.stringify(values));
    const message = document.getElementById('sync-message');
    if (message) message.textContent = 'Draft saved locally on this device.';
  });

  form.addEventListener('submit', async (event) => {
    if (navigator.onLine) {
      localStorage.removeItem(draftKey);
      return;
    }
    event.preventDefault();
    const values = new FormData(form);
    const answers = {};
    const remarks = {};
    for (const [key, value] of values.entries()) {
      if (key.startsWith('item_')) answers[key.slice(5)] = value;
      if (key.startsWith('remark_')) remarks[key.slice(7)] = value;
    }
    const payload = {
      vehicle_id: Number(form.dataset.vehicle),
      start_km: values.get('start_km'),
      odometer: values.get('odometer'),
      notes: values.get('notes') || '',
      answers,
      remarks,
      driver_signature: values.get('driver_signature'),
      license_expiry: values.get('license_expiry'),
      attestation: values.get('attestation'),
    };
    try {
      await saveQueue({
        key: `${payload.vehicle_id}-${form.dataset.day}`,
        url: form.dataset.syncUrl,
        csrf: values.get('csrf'),
        payload,
      });
      localStorage.removeItem(draftKey);
      const message = document.getElementById('sync-message');
      if (message) {
        message.textContent =
          'Inspection saved to IndexedDB offline queue and will sync automatically when connected. Photos require an active connection.';
      }
      const submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) submitBtn.disabled = true;
    } catch (_) {
      const message = document.getElementById('sync-message');
      if (message) message.textContent = 'Could not save offline data. Please reconnect and try again.';
    }
  });

  updateSummaryCounters();
  syncQueue();
})();
