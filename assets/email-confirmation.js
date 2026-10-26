(() => {
  const prefix = '#confirm-email=';
  if (location.pathname === '/gramanna.html') {
    if (location.hash.startsWith('#unsubscribe=') || location.hash.startsWith('#manage=')) {
      const fragment = location.hash;
      history.replaceState(null, '', location.pathname + location.search);
      location.replace('manage-notifications.html' + fragment);
      return;
    }
    // Capture issued links at head-script entry, before legacy-page API work.
    if (location.hash.startsWith(prefix)) {
      const fragment = location.hash;
      history.replaceState(null, '', location.pathname + location.search);
      location.replace('confirm-email.html' + fragment);
    }
    return;
  }
  // This blocking head script clears the capability before any application fetch.
  // Retain it only in this closure; never copy it into DOM, history state or storage.
  let token;
  if (location.hash.startsWith(prefix)) {
    const candidate = location.hash.slice(prefix.length);
    if (/^[0-9a-f]{64}$/.test(candidate)) token = candidate;
  }
  history.replaceState(null, '', location.pathname + location.search);

  document.addEventListener('DOMContentLoaded', () => {
    const card = document.getElementById('email-confirmation');
    const title = document.getElementById('email-confirmation-title');
    const explanation = document.getElementById('email-confirmation-explanation');
    const button = document.getElementById('email-confirmation-button');
    const status = document.getElementById('email-confirmation-status');
    const error = document.getElementById('email-confirmation-error');
    const help = document.getElementById('email-confirmation-help');
    let busy = false;
    let csrf;
    let enabled;
    let loading;
    const unavailable = 'This link is unavailable. Request a new confirmation link.';
    const failure = 'We could not confirm your email. Please try again with this link.';

    function problem(text, terminal = false) {
      status.textContent = '';
      error.textContent = text;
      help.hidden = false;
      if (terminal) {
        token = null;
        button.hidden = true;
        title.textContent = 'Confirmation link unavailable';
        explanation.textContent = 'Use the latest confirmation email, or request a new link for your selected announcements.';
      }
    }

    function controls() {
      card.setAttribute('aria-busy', String(busy));
      button.disabled = busy || !token || enabled === false;
      button.textContent = busy ? 'Confirming your email…' : 'Confirm email';
    }

    async function api(path, body) {
      const abort = new AbortController();
      const timer = setTimeout(() => abort.abort(), 15000);
      try {
        const response = await fetch(path, {
          method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
          referrerPolicy: 'no-referrer', signal: abort.signal,
          headers: body ? { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf } : {},
          body: body ? JSON.stringify(body) : undefined
        });
        if (response.status === 403) csrf = null;
        const data = await response.json();
        return { response, data };
      } finally {
        clearTimeout(timer);
      }
    }

    async function session() {
      if (csrf) return;
      if (!loading) loading = (async () => {
        const { response, data } = await api('/api/notifications/session');
        if (!response.ok || !data || typeof data.csrf_token !== 'string' ||
            !/^[0-9a-f]{64}$/.test(data.csrf_token) || typeof data.confirmation_enabled !== 'boolean') {
          throw new Error();
        }
        csrf = data.csrf_token;
        enabled = data.confirmation_enabled;
      })().finally(() => { loading = null; });
      await loading;
    }

    button.addEventListener('click', async () => {
      if (busy || !token || enabled === false) return;
      busy = true;
      error.textContent = '';
      status.textContent = 'Confirming your email…';
      controls();
      try {
        await session();
        if (!enabled) {
          problem('Email confirmation is currently unavailable. Please try your link later.');
          return;
        }
        const { response, data } = await api('/api/notifications/confirm', { token });
        if (response.ok && data && data.status === 'confirmed' &&
            (data.already_confirmed === undefined || typeof data.already_confirmed === 'boolean')) {
          const alreadyConfirmed = data.already_confirmed === true;
          token = null;
          button.hidden = true;
          help.hidden = true;
          document.getElementById('email-confirmation-check').removeAttribute('hidden');
          title.textContent = alreadyConfirmed ? 'Your email is already confirmed!' : 'Your email is confirmed!';
          explanation.textContent = alreadyConfirmed
            ? 'Your email address has already been verified. No further action is needed.'
            : "Thank you for confirming your email address. You're now subscribed to the GraManna announcements you selected.";
          status.textContent = 'Email verification complete';
          title.focus();
        } else if (response.status === 400) {
          problem(unavailable, true);
          title.focus();
        } else if (response.status === 403) {
          problem('Enable cookies, then select Confirm email to try again.');
        } else {
          problem(failure);
        }
      } catch {
        problem(failure);
      } finally {
        busy = false;
        controls();
        if (token && enabled !== false) button.focus();
      }
    });

    title.focus();
    if (!token) {
      problem(unavailable, true);
      controls();
      return;
    }
    // Session discovery cannot verify anything. Only the click handler may POST.
    session().then(() => {
      if (!enabled) problem('Email confirmation is currently unavailable. Please try your link later.');
    }).catch(() => {
      problem('We could not prepare confirmation. Enable cookies and select Confirm email to try again.');
    }).finally(controls);
  }, { once: true });
})();
