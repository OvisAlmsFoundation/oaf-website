(() => {
  const form = document.getElementById('state-request-form');
  const state = document.getElementById('request-state');
  const button = form.querySelector('button');
  const note = document.getElementById('request-note');
  const total = document.getElementById('request-total');
  let csrfToken;
  let counts;
  let busy = false;
  let totalsRequest = 0;

  function message(text, error = false) {
    note.setAttribute('role', error ? 'alert' : 'status');
    note.textContent = text;
  }

  async function jsonResponse(response) {
    let data;
    try {
      data = await response.json();
    } catch (_) {
      throw new Error('State requests are temporarily unavailable. Please try again.');
    }
    if (!response.ok) throw new Error(data.message || 'State requests are temporarily unavailable. Please try again.');
    return data;
  }

  async function session() {
    const data = await jsonResponse(await fetch('/api/state-requests/session', {
      credentials: 'same-origin', cache: 'no-store'
    }));
    csrfToken = data.csrf_token;
  }

  function showTotal() {
    total.textContent = state.value && counts ?
      `${counts[state.value]} counted request${counts[state.value] === 1 ? '' : 's'} for ${state.selectedOptions[0].textContent}.` : '';
  }

  async function loadTotals() {
    const sequence = ++totalsRequest;
    try {
      const data = await jsonResponse(await fetch('/api/state-requests/totals', { cache: 'no-store' }));
      if (sequence !== totalsRequest) return;
      counts = data.totals;
      showTotal();
    } catch (_) {
      if (sequence !== totalsRequest) return;
      counts = null;
      total.textContent = 'State totals are temporarily unavailable.';
    }
  }

  state.addEventListener('change', showTotal);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (busy) return;
    if (!state.value) {
      message('Select one of the 50 U.S. states.', true);
      state.focus();
      return;
    }
    const requestedState = state.value;
    busy = true;
    button.disabled = true;
    state.disabled = true;
    form.setAttribute('aria-busy', 'true');
    message('Submitting your state request…');
    try {
      if (!csrfToken) await session();
      const response = await fetch('/api/state-requests', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ state: requestedState })
      });
      if (response.status === 403) csrfToken = null;
      const data = await jsonResponse(response);
      message(data.message);
      await loadTotals();
    } catch (error) {
      message(error.message === 'Failed to fetch' ?
        'We could not confirm your request. Please try again; a repeat will not add another count.' : error.message, true);
    } finally {
      busy = false;
      button.disabled = false;
      state.disabled = false;
      form.removeAttribute('aria-busy');
    }
  });
  button.disabled = false;
  message('No account or email is needed. This browser can request each state once.');
  loadTotals();
})();
