(() => {
  // A blocking head script removes private material before resources/API work.
  let fragment = location.hash;
  const hadFragment = Boolean(fragment);
  history.replaceState(null, '', location.pathname + location.search);
  window.addEventListener('hashchange', () => {
    if (location.hash.startsWith('#manage=') || location.hash.startsWith('#unsubscribe=')) location.reload();
  });
  const managementShape = /^m2\.(testing|development)\.[0-9a-f]{64}\.[0-9]{1,10}\.[0-9]{1,12}\.[0-9]{1,12}\.[0-9a-f]{64}\.[0-9a-f]{64}$/;
  let token = fragment.startsWith('#manage=') ? fragment.slice(8) : null;
  if (!managementShape.test(token || '')) token = null;
  let legacy = fragment.startsWith('#unsubscribe=') ? fragment.slice(13) : null;
  if (!/^[0-9a-f]{64}\.[0-9a-f]{64}$/.test(legacy || '')) legacy = null;
  let revision = token ? Number(token.split('.')[3]) : null;
  fragment = null;

  document.addEventListener('DOMContentLoaded', () => {
    const card = document.getElementById('notification-management');
    const form = document.getElementById('management-form');
    const recovery = document.getElementById('management-recovery');
    const view = document.getElementById('management-view');
    const withdrawal = document.getElementById('management-withdrawal');
    const unsubscribe = document.getElementById('management-unsubscribe');
    const status = document.getElementById('management-status');
    const error = document.getElementById('management-error');
    const title = document.getElementById('management-title');
    const web = document.getElementById('management-web');
    const android = document.getElementById('management-android');
    const ios = document.getElementById('management-ios');
    const stateEnabled = document.getElementById('management-state-enabled');
    const state = document.getElementById('management-state');
    const consent = document.getElementById('management-consent');
    let busy = false, csrf, loading, enabled, action, authorized = false, withdrawalOnly = false;
    const unavailable = 'This link is unavailable. Use your latest email or request a new link.';
    const failure = 'We could not confirm this action. Try again with this link.';

    function message(text, appearance = 'information') {
      status.dataset.status = appearance;
      status.textContent = text;
    }

    function controls(value) {
      busy = value;
      card.setAttribute('aria-busy', String(value));
      card.querySelectorAll('input, select, button').forEach(item => { item.disabled = value; });
      document.getElementById('management-state-field').hidden = !stateEnabled.checked;
      state.disabled = value || !stateEnabled.checked;
      state.required = stateEnabled.checked;
      unsubscribe.disabled = value || !(authorized || withdrawalOnly || legacy) || enabled === false && !legacy;
    }

    async function api(path, body) {
      const abort = new AbortController();
      const timer = setTimeout(() => abort.abort(), 15000);
      try {
        const response = await fetch(path, { method: body ? 'POST' : 'GET',
          credentials: 'same-origin', cache: 'no-store', referrerPolicy: 'no-referrer', signal: abort.signal,
          headers: body ? { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf } : {},
          body: body ? JSON.stringify(body) : undefined });
        if (response.status === 403) csrf = null;
        return { response, data: await response.json() };
      } finally { clearTimeout(timer); }
    }

    async function session() {
      if (csrf) return;
      if (!loading) loading = (async () => {
        const { response, data } = await api('/api/notifications/session');
        if (!response.ok || !data || !/^[0-9a-f]{64}$/.test(data.csrf_token || '')) throw new Error();
        csrf = data.csrf_token;
        enabled = data.management_enabled === true;
      })().finally(() => { loading = null; });
      await loading;
    }

    async function perform(work, failureMessage = failure) {
      if (busy) return;
      controls(true); error.textContent = ''; message('Processing…', 'processing');
      try { await session(); await work(); }
      catch { status.textContent = ''; error.textContent = failureMessage; }
      finally { controls(false); }
    }

    async function readPreferences() {
      if (!enabled) { status.textContent = ''; error.textContent = 'Notification management is currently unavailable.'; return; }
      const hadAuthority = Boolean(token || authorized || withdrawalOnly);
      const { response, data } = await api('/api/notifications/manage', token ? { token } : {});
      if (!response.ok) {
        status.textContent = '';
        if (response.status === 400) {
          rejectAuthority(hadAuthority ? unavailable : '');
        } else error.textContent = failure;
        return;
      }
      if (data && data.status === 'withdrawal_only' && token && data.revision === revision) {
        authorized = false; withdrawalOnly = true; action = null;
        form.hidden = true; withdrawal.hidden = false; view.hidden = false;
        message('You can unsubscribe now. Confirm your email before viewing or changing preferences.');
        return;
      }
      const p = data && data.preferences;
      if (!p || data.status !== 'preferences' || !Number.isInteger(data.revision) ||
          data.revision < 0 || data.revision >= 2147483647 || (token && data.revision !== revision) ||
          ['web_launch', 'android_launch', 'ios_launch'].some(name => typeof p[name] !== 'boolean') ||
          !(p.state === null || typeof p.state === 'string' && Array.from(state.options).some(o => o.value === p.state && o.value))) throw new Error();
      token = null; revision = data.revision; authorized = true; withdrawalOnly = false; action = null;
      web.checked = p.web_launch; android.checked = p.android_launch; ios.checked = p.ios_launch;
      stateEnabled.checked = p.state !== null; state.value = p.state || ''; consent.checked = false;
      form.hidden = false; view.hidden = true; withdrawal.hidden = false;
      message('Your current notification preferences are ready.', 'information');
    }

    function rejectAuthority(text = unavailable) {
      token = null; legacy = null; authorized = false; withdrawalOnly = false; action = null;
      form.hidden = true; withdrawal.hidden = true; view.hidden = true;
      status.textContent = ''; error.textContent = text;
    }

    function mutation(preferences) {
      const body = { ...(token ? { token } : {}), revision, ...(preferences ? { preferences } : {}) };
      const snapshot = JSON.stringify(body);
      if (!action || action.snapshot !== snapshot) {
        const bytes = crypto.getRandomValues(new Uint8Array(32));
        action = { snapshot, id: Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('') };
      }
      return { ...body, action: action.id };
    }

    async function save(body) {
      const withdrawing = !body.preferences || !['web_launch', 'android_launch', 'ios_launch', 'state']
        .some(name => body.preferences[name]);
      if (withdrawing) {
        // Obtain acknowledgment authority before the response can clear the
        // management cookie. It stays with this exact action only in memory.
        if (!action.receipt) {
          const prepared = await api('/api/notifications/manage/withdrawal-receipt', body);
          if (prepared.response.status === 400 || prepared.response.status === 409) {
            rejectAuthority(); return;
          }
          if (!prepared.response.ok || typeof prepared.data.receipt !== 'string' ||
              !prepared.data.receipt || prepared.data.receipt.length > 1536) throw new Error();
          action.receipt = prepared.data.receipt;
        }
        if (action.attempted) {
          const acknowledgment = await api('/api/notifications/manage/withdrawal-ack', {
            receipt: action.receipt, action: body.action, revision: body.revision,
            ...(body.preferences ? { preferences: body.preferences } : {}) });
          if (acknowledgment.response.ok && acknowledgment.data.status === 'unsubscribed' &&
              acknowledgment.data.revision === body.revision + 1) { completeWithdrawal(); return; }
          if (acknowledgment.response.status !== 400) throw new Error();
        }
        action.attempted = true;
      }
      const { response, data } = await api('/api/notifications/manage/save', body);
      if (!response.ok) {
        status.textContent = '';
        if (response.status === 400 || response.status === 409) rejectAuthority();
        error.textContent = response.status === 409 ? 'Preferences changed. Reopen your latest link or request a new one.' :
          response.status === 400 ? unavailable : failure;
        return;
      }
      if (withdrawing && data.status === 'unsubscribed' && data.revision === body.revision + 1) { completeWithdrawal(); return; }
      if (withdrawing) throw new Error();
      if (data.status !== 'saved' || data.revision !== revision + 1) throw new Error();
      revision = data.revision; action = null; consent.checked = false;
      message('Your notification preferences have been saved.', 'success');
      title.focus();
    }

    function completeWithdrawal(conditionalMessage = null) {
      token = null; legacy = null; action = null; authorized = false; withdrawalOnly = false;
      form.hidden = true; withdrawal.hidden = true; view.hidden = true;
      document.getElementById('management-instructions').hidden = true;
      recovery.hidden = !conditionalMessage;
      title.textContent = conditionalMessage ? 'Request processed' : 'Unsubscribed';
      message(conditionalMessage || 'You have unsubscribed from all notifications for this subscription.',
        conditionalMessage ? 'information' : 'success');
      title.focus();
    }

    form.addEventListener('submit', event => {
      event.preventDefault(); if (busy || !authorized) return;
      const preferences = { web_launch: web.checked, android_launch: android.checked, ios_launch: ios.checked,
        state: stateEnabled.checked ? state.value : null, consent: consent.checked };
      if ((web.checked || android.checked || ios.checked || stateEnabled.checked) && !consent.checked) {
        error.textContent = 'Consent is required to save the selected announcements.'; consent.focus(); return;
      }
      const body = mutation(preferences);
      perform(() => save(body));
    });
    unsubscribe.addEventListener('click', () => {
      if (busy || !(authorized || withdrawalOnly || legacy)) return;
      const body = authorized || token ? mutation() : null;
      perform(async () => {
        if (body) await save(body);
        else {
          const { response, data } = await api('/api/notifications/unsubscribe', { token: legacy });
          if (response.status === 400) { rejectAuthority(); return; }
          if (!response.ok || data.status !== 'unsubscribed' || typeof data.message !== 'string' || !data.message) throw new Error();
          completeWithdrawal(data.message);
        }
      });
    });
    recovery.addEventListener('submit', event => {
      event.preventDefault(); if (busy) return;
      const email = document.getElementById('management-email').value;
      perform(async () => {
        if (!enabled) { status.textContent = ''; error.textContent = 'Notification management is currently unavailable.'; return; }
        const { response, data } = await api('/api/notifications/manage/recovery', { email });
        if (response.status === 400) { status.textContent = ''; error.textContent = 'Enter a valid email address.'; return; }
        if (!response.ok || data.status !== 'received') throw new Error();
        message("If a link is needed and permitted, we'll email it. Check your inbox.");
      }, 'We could not request a recovery link. Please try again later.');
    });
    view.addEventListener('click', () => perform(readPreferences));
    stateEnabled.addEventListener('change', () => controls(busy));
    // BFCache restores closures and form values. Hide them before suspension and
    // reload on return so suspended requests cannot revive a stale form.
    window.addEventListener('pagehide', () => { form.hidden = true; withdrawal.hidden = true; });
    window.addEventListener('pageshow', event => {
      if (event.persisted && !legacy) location.reload();
    });
    withdrawal.hidden = !(token || legacy);
    document.getElementById('management-legacy-note').hidden = !legacy;
    view.hidden = !token;
    if (!token && !legacy && hadFragment) error.textContent = unavailable;
    if (token || !legacy && !hadFragment) perform(readPreferences);
    else session().then(() => controls(false)).catch(() => { error.textContent = failure; controls(false); });
  });
})();
