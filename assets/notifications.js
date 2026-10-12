(() => {
  const form = document.getElementById('notification-form');
  const email = document.getElementById('notification-email');
  const web = document.getElementById('notify-web');
  const android = document.getElementById('notify-android');
  const ios = document.getElementById('notify-ios');
  const statePreference = document.getElementById('notify-state');
  const stateField = document.getElementById('notification-state-field');
  const state = document.getElementById('notification-state');
  const consent = document.getElementById('notification-consent');
  const button = form.querySelector('button[type="submit"]');
  const note = document.getElementById('notification-message');
  const receipt = document.getElementById('notification-receipt');
  const link = document.getElementById('notification-unsubscribe-link');
  const withdrawal = document.getElementById('notification-unsubscribe');
  const withdrawButton = document.getElementById('notification-unsubscribe-button');
  const withdrawNote = document.getElementById('notification-unsubscribe-message');
  let busy = false;
  let csrf;
  let submission;
  let withdrawalToken;

  function message(target, text, error = false) {
    target.setAttribute('role', error ? 'alert' : 'status');
    target.textContent = text;
  }

  function updateState() {
    stateField.hidden = !statePreference.checked;
    state.disabled = busy || !statePreference.checked;
    state.required = statePreference.checked;
  }

  function controls(disabled) {
    busy = disabled;
    [email, web, android, ios, statePreference, consent, button, withdrawButton]
      .forEach(control => { control.disabled = disabled; });
    updateState();
    withdrawButton.disabled = disabled || !withdrawalToken;
    form.setAttribute('aria-busy', String(disabled));
  }

  async function api(path, body) {
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), 15000);
    try {
      const response = await fetch(path, {
        method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
        signal: abort.signal,
        headers: body ? { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf } : {},
        body: body ? JSON.stringify(body) : undefined
      });
      if (response.status === 403) csrf = null;
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.message === 'string' ? data.message : 'Announcements are temporarily unavailable. Try again.');
      return data;
    } catch (error) {
      if (error instanceof SyntaxError || error.name === 'AbortError' || error instanceof TypeError) {
        throw new Error('We could not confirm this action. Try again; repeated submissions are safe.');
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  async function session() {
    if (!csrf) csrf = (await api('/api/notifications/session')).csrf_token;
  }

  function readWithdrawalLink() {
    if (!location.hash.startsWith('#unsubscribe=')) return;
    const token = location.hash.slice('#unsubscribe='.length);
    // Fragments never reach HTTP/access logs. Remove the capability from the
    // address bar before any API call; no token is put in a query or path.
    history.replaceState(null, '', location.pathname + location.search);
    withdrawal.hidden = false;
    if (/^[0-9a-f]{64}\.[0-9a-f]{64}$/.test(token)) {
      withdrawalToken = token;
      withdrawButton.disabled = busy;
      message(withdrawNote, 'Select Unsubscribe to withdraw these announcement preferences.');
    } else {
      withdrawalToken = null;
      withdrawButton.disabled = true;
      message(withdrawNote, 'Use the complete private unsubscribe link saved when subscribing.', true);
    }
    document.getElementById('unsubscribe-title').focus();
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    if (!web.checked && !android.checked && !ios.checked && !statePreference.checked) {
      message(note, 'Choose at least one notification preference.', true);
      web.focus();
      return;
    }
    const choices = { email: email.value, web_launch: web.checked, android_launch: android.checked,
      ios_launch: ios.checked, state: statePreference.checked ? state.value : null, consent: consent.checked };
    const snapshot = JSON.stringify(choices);
    if (!submission || submission.snapshot !== snapshot) {
      const bytes = crypto.getRandomValues(new Uint8Array(32));
      submission = { snapshot, token: Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('') };
    }
    controls(true);
    message(note, 'Saving your notification preferences...');
    try {
      await session();
      const data = await api('/api/notifications', { ...choices, token: submission.token });
      if (typeof data.unsubscribe_token !== 'string' || !/^[0-9a-f]{64}\.[0-9a-f]{64}$/.test(data.unsubscribe_token)) {
        throw new Error('We could not confirm this action. Try again with the same form.');
      }
      link.href = `${location.pathname}#unsubscribe=${data.unsubscribe_token}`;
      receipt.hidden = false;
      message(note, data.message);
      email.value = '';
    } catch (error) {
      message(note, error.message, true);
    } finally {
      controls(false);
    }
  });

  withdrawButton.addEventListener('click', async () => {
    if (busy || !withdrawalToken) return;
    controls(true);
    message(withdrawNote, 'Processing unsubscribe...');
    try {
      await session();
      const data = await api('/api/notifications/unsubscribe', { token: withdrawalToken });
      message(withdrawNote, data.message);
      submission = null;
    } catch (error) {
      message(withdrawNote, error.message, true);
    } finally {
      controls(false);
    }
  });

  statePreference.addEventListener('change', updateState);
  window.addEventListener('pageshow', updateState);
  window.addEventListener('hashchange', readWithdrawalLink);
  if (globalThis.crypto && crypto.getRandomValues) button.disabled = false;
  else message(note, 'Open this website over HTTPS to subscribe securely.', true);
  updateState();
  readWithdrawalLink();
})();
