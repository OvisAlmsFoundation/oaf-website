(() => {
  const openedFragment = location.hash;
  if (openedFragment.startsWith('#confirm-email=') || openedFragment.startsWith('#unsubscribe=')) {
    // Strip private capabilities before DOM work or any application requests.
    history.replaceState(null, '', location.pathname + location.search);
  }
  if (openedFragment.startsWith('#confirm-email=')) {
    // Keep issued links usable without a query, storage handoff or token renewal.
    location.replace('confirm-email.html' + openedFragment);
    return;
  }
  if (openedFragment.startsWith('#unsubscribe=') || openedFragment.startsWith('#manage=')) {
    history.replaceState(null, '', location.pathname + location.search);
    location.replace('manage-notifications.html' + openedFragment);
    return;
  }
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
  const confirmationForm = document.getElementById('notification-confirmation-form');
  const confirmationEmail = document.getElementById('confirmation-email');
  const requestButton = document.getElementById('notification-confirmation-button');
  const requestNote = document.getElementById('notification-confirmation-message');
  let busy = false;
  let csrf;
  let sessionLoading;
  let confirmationEnabled = null;
  let submission;

  function message(target, text, error = false, appearance = 'information') {
    target.dataset.status = error ? 'error' : appearance;
    target.setAttribute('role', error ? 'alert' : 'status');
    target.setAttribute('aria-live', error ? 'assertive' : 'polite');
    target.textContent = text;
  }

  function updateState() {
    stateField.hidden = !statePreference.checked;
    state.disabled = busy || !statePreference.checked;
    state.required = statePreference.checked;
  }

  function controls(disabled) {
    busy = disabled;
    [email, web, android, ios, statePreference, consent, button, confirmationEmail]
      .forEach(control => { control.disabled = disabled; });
    updateState();
    requestButton.disabled = disabled || !confirmationEnabled;
    button.disabled = disabled || !(globalThis.crypto && crypto.getRandomValues);
    form.setAttribute('aria-busy', String(disabled));
    confirmationForm.setAttribute('aria-busy', String(disabled));
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
    if (csrf) return;
    if (!sessionLoading) sessionLoading = api('/api/notifications/session').then(data => {
      if (typeof data.csrf_token !== 'string' || !/^[0-9a-f]{64}$/.test(data.csrf_token)) {
        throw new Error('We could not confirm this action. Try again.');
      }
      csrf = data.csrf_token;
      confirmationEnabled = data.confirmation_enabled === true;
      confirmationForm.hidden = !confirmationEnabled;
      document.getElementById('subscription-note').textContent = confirmationEnabled ?
        "We save your email and selected preferences for future announcements. If confirmation is needed and permitted, we'll email a link." :
        'We save your email and selected preferences for future announcements. Email delivery is not connected yet; no confirmation email will be sent.';
    }).finally(() => { sessionLoading = null; });
    await sessionLoading;
  }

  function readConfirmationLink(fragment = location.hash) {
    if (!fragment.startsWith('#confirm-email=')) return;
    history.replaceState(null, '', location.pathname + location.search);
    location.replace('confirm-email.html' + fragment);
  }

  function readWithdrawalLink(fragment = location.hash) {
    if (!fragment.startsWith('#unsubscribe=') && !fragment.startsWith('#manage=')) return;
    history.replaceState(null, '', location.pathname + location.search);
    location.replace('manage-notifications.html' + fragment);
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
    message(note, 'Saving your notification preferences...', false, 'processing');
    try {
      await session();
      const data = await api('/api/notifications', { ...choices, token: submission.token });
      if (typeof data.unsubscribe_token !== 'string' || !/^[0-9a-f]{64}\.[0-9a-f]{64}$/.test(data.unsubscribe_token)) {
        throw new Error('We could not confirm this action. Try again with the same form.');
      }
      link.href = `manage-notifications.html#unsubscribe=${data.unsubscribe_token}`;
      receipt.hidden = false;
      message(note, data.message);
      email.value = '';
    } catch (error) {
      message(note, error.message, true);
    } finally {
      controls(false);
    }
  });

  confirmationForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !confirmationEnabled) return;
    const address = confirmationEmail.value;
    controls(true);
    message(requestNote, 'Requesting a confirmation link...', false, 'processing');
    try {
      await session();
      if (!confirmationEnabled) throw new Error('Email confirmation is currently unavailable.');
      const data = await api('/api/notifications/confirmation', { email: address });
      message(requestNote, data.message);
    } catch (error) {
      message(requestNote, error.message, true);
    } finally {
      controls(false);
    }
  });

  statePreference.addEventListener('change', updateState);
  window.addEventListener('pageshow', updateState);
  window.addEventListener('hashchange', () => readWithdrawalLink());
  window.addEventListener('hashchange', () => readConfirmationLink());
  if (globalThis.crypto && crypto.getRandomValues) button.disabled = false;
  else message(note, 'Open this website over HTTPS to subscribe securely.', true);
  updateState();
  readWithdrawalLink(openedFragment);
  readConfirmationLink(openedFragment);
  // Clear either private fragment before the first API request. This script
  // precedes the State Request script, which also performs an initial fetch.
  session().then(() => controls(busy)).catch(() => controls(busy));
})();
