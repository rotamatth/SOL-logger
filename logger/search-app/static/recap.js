(() => {
  const recap = document.getElementById('recap');
  const status = document.getElementById('recap-status');
  const actions = [...recap.querySelectorAll('[data-action]')];
  const attempt = recap.dataset.attemptId;
  // The answers can no longer change here. Saving still confirms that no draft has changed meanwhile.
  const draftRevisions = JSON.parse(recap.dataset.draftRevisions || '{}');

  function updateStatus(message, error = false) {
    status.textContent = message;
    status.toggleAttribute('data-error', error);
  }

  // This page is out of date, usually after the idle limit. The server knows where the child belongs:
  // after the limit that is the start page, as on every other page. A request that stays refused
  // must not reload the page for ever.
  function reopen() {
    const key = `solRecapReopened:${attempt}`;
    try {
      if (Date.now() - Number(sessionStorage.getItem(key)) < 30000) return false;
      sessionStorage.setItem(key, String(Date.now()));
    } catch (_) {
      // Without storage the page reloads once per tap at most, which is still not a loop.
    }
    window.location.reload();
    return true;
  }

  async function post(url, payload = {}) {
    let response;
    try {
      response = await window.tryAgain(() => fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ attempt_id: attempt, csrf_token: recap.dataset.csrfToken, ...payload })
      }));
    } catch (_) {
      throw new Error('Connessione non disponibile. Riprova.');
    }
    const data = await response.json().catch(() => ({}));
    if (response.status < 500 && !response.ok && !data.error && reopen()) {
      return new Promise(() => {});
    }
    if (!response.ok) throw new Error(data.error || 'Salvataggio non disponibile. Riprova.');
    return data;
  }

  function leave(welcome) {
    for (const number of [1, 2, 3]) {
      sessionStorage.removeItem(`solFirstDraft:${attempt}:${number}`);
      sessionStorage.removeItem(`solFinalDraft:${attempt}:${number}`);
    }
    Object.keys(sessionStorage).filter(key => key.startsWith(`solRecapDraft:${attempt}:`))
      .forEach(key => sessionStorage.removeItem(key));
    sessionStorage.removeItem('solLastAllowedAppUrl');
    if (localStorage.getItem('sessionID') === window.SESSION_ID) {
      for (const key of ['sessionID', 'sessionLogs', 'browserHistory']) localStorage.removeItem(key);
    }
    window.SESSION_ID = '';
    window.location.replace(welcome);
  }

  async function run(button) {
    actions.forEach(control => { control.disabled = true; });
    updateStatus('Salvataggio in corso…');
    try {
      try {
        await window.tryAgain(() => window.studyLogger.sendLogs());
      } catch (_) {
        throw new Error('Salvataggio dei dati non disponibile. Riprova.');
      }
      const result = await post(button.dataset.url, { draft_revisions: draftRevisions });
      if (button.dataset.action === 'restart') {
        leave(result.welcome);
      } else {
        window.location.reload();
      }
    } catch (error) {
      updateStatus(error.message, true);
      actions.forEach(control => { control.disabled = false; });
    }
  }

  // The buttons arrive disabled, so a tap before this script has started is not silently lost.
  actions.forEach(button => {
    button.addEventListener('click', () => { void run(button); });
    button.disabled = false;
  });
})();
