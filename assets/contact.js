(() => {
  const form = document.getElementById('contact-form');
  const email = document.getElementById('contact-email');
  const message = document.getElementById('contact-text');
  const button = form.querySelector('button[type="submit"]');
  const note = document.getElementById('contact-feedback');
  const uncertain = 'We could not confirm whether your message was accepted. Please wait 15 minutes before trying again.';
  let busy = false;
  let csrf;

  function feedback(text, error = false) {
    note.setAttribute('role', error ? 'alert' : 'status');
    note.setAttribute('aria-live', error ? 'assertive' : 'polite');
    note.textContent = text;
  }

  function controls(disabled) {
    busy = disabled;
    [email, message, button].forEach(control => { control.disabled = disabled; });
    form.setAttribute('aria-busy', String(disabled));
  }

  async function api(path, body) {
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), 60000);
    try {
      const response = await fetch(path, {
        method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
        signal: abort.signal,
        headers: body ? { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf } : {},
        body: body ? JSON.stringify(body) : undefined
      });
      if (response.status === 403) csrf = null;
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.message === 'string' ? data.message : uncertain);
      return data;
    } catch (error) {
      if (error instanceof SyntaxError || error instanceof TypeError || error.name === 'AbortError') {
        throw new Error(uncertain);
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    const words = message.value.trim().split(/\s+/u).filter(Boolean).length;
    if (words > 200 || !message.value.trim()) {
      feedback(words > 200 ? 'Keep your message within 200 words.' : 'Enter a message.', true);
      message.focus();
      return;
    }
    const body = { email: email.value, message: message.value };
    controls(true);
    feedback('Sending your message...');
    try {
      if (!csrf) csrf = (await api('/api/contact/session')).csrf_token;
      const data = await api('/api/contact', body);
      if (data.status !== 'accepted' || typeof data.message !== 'string') throw new Error(uncertain);
      feedback(data.message);
      form.reset();
    } catch (error) {
      feedback(error.message, true);
    } finally {
      controls(false);
      note.focus();
    }
  });

  button.disabled = false;
})();
