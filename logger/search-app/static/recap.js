(() => {
  const recap = document.getElementById('recap');
  const status = document.getElementById('recap-status');
  const actions = [...recap.querySelectorAll('[data-action]')];
  const editors = [...recap.querySelectorAll('textarea[data-target]')];
  const attempt = recap.dataset.attemptId;

  function updateStatus(message, error = false) {
    status.textContent = message;
    status.toggleAttribute('data-error', error);
  }

  async function post(url, payload = {}) {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ attempt_id: attempt, csrf_token: recap.dataset.csrfToken, ...payload })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'Salvataggio non disponibile. Riprova.');
    return data;
  }

  recap.querySelectorAll('.recap-column').forEach(column => {
    const cards = [...column.querySelectorAll('.recap-question')];
    if (!cards.length) return;
    const previous = column.querySelector('[data-step="-1"]');
    const next = column.querySelector('[data-step="1"]');
    const counter = column.querySelector('[data-question-index]');
    let index = 0;
    function move(step) {
      const target = index + step;
      if (!cards[target]) return;
      cards[index].hidden = true;
      index = target;
      cards[index].hidden = false;
      counter.textContent = `${index + 1} / ${cards.length}`;
      previous.disabled = index === 0;
      next.disabled = index === cards.length - 1;
      if (document.activeElement === document.body) (step > 0 ? previous : next).focus();
    }
    previous.addEventListener('click', () => move(-1));
    next.addEventListener('click', () => move(1));
  });

  function draftEditor(field) {
    let acknowledged = field.value;
    let revision = Number(field.dataset.revision);
    let pending;
    let sent;
    let timer;
    let conflict = field.dataset.staleDraft === 'true';
    let forceSave = false;
    const error = field.nextElementSibling;
    const bufferKey = `solRecapDraft:${attempt}:${field.dataset.target}:${field.dataset.number}`;
    try {
      const buffer = JSON.parse(sessionStorage.getItem(bufferKey) || 'null');
      if (buffer?.text === acknowledged && (buffer.revision !== revision || !buffer.sent || buffer.sent === acknowledged)) {
        sessionStorage.removeItem(bufferKey);
      } else if (typeof buffer?.text === 'string'
          && (buffer.revision === revision || (buffer.revision + 1 === revision && buffer.sent === acknowledged))) {
        forceSave = buffer.text === acknowledged;
        field.value = buffer.text;
        timer = setTimeout(() => flush().catch(() => {}), 0);
      } else if (typeof buffer?.text === 'string') {
        field.value = buffer.text;
        conflict = true;
        error.textContent = 'La risposta è cambiata in un’altra scheda. Controlla il testo prima di salvarlo.';
      }
    } catch (_) {
      // Server drafts remain available if this browser disallows session storage.
    }

    function buffer() {
      try {
        if (!forceSave && field.value === acknowledged && (!pending || field.value === sent)) {
          sessionStorage.removeItem(bufferKey);
        }
        else sessionStorage.setItem(bufferKey, JSON.stringify({ text: field.value, revision, sent }));
      } catch (_) {
        // The open editor keeps its text until the server acknowledges it.
      }
    }

    async function flush() {
      clearTimeout(timer);
      if (pending) await pending;
      if (conflict) throw new Error(error.textContent);
      const text = field.value;
      if (!forceSave && text === acknowledged) return;
      sent = text;
      buffer();
      pending = post(recap.dataset.draftUrl, {
        target_attempt_id: field.dataset.target, number: Number(field.dataset.number), text, revision,
        answer_revision: Number(field.dataset.answerRevision)
      }).then(result => {
        revision = result.revision;
        acknowledged = text;
        forceSave = false;
        field.dataset.revision = String(revision);
        error.textContent = '';
        buffer();
      }).catch(reason => {
        error.textContent = reason.message;
        throw reason;
      }).finally(() => { pending = null; });
      await pending;
    }

    field.addEventListener('input', () => {
      if (conflict) forceSave = true;
      conflict = false;
      buffer();
      clearTimeout(timer);
      timer = setTimeout(() => flush().catch(() => {}), 250);
    });
    return flush;
  }

  const drafts = editors.map(draftEditor);

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
    [...actions, ...editors].forEach(control => { control.disabled = true; });
    updateStatus('Salvataggio in corso…');
    try {
      await Promise.all(drafts.map(flush => flush()));
      if (button.dataset.action !== 'save') {
        if (!window.studyLogger) throw new Error('Salvataggio dei dati non disponibile. Riprova.');
        await window.studyLogger.sendLogs();
      }
      const revisions = Object.fromEntries(editors.map(field => [
        `${field.dataset.target}:${field.dataset.number}`, Number(field.dataset.revision)
      ]));
      const result = await post(button.dataset.url, { draft_revisions: revisions });
      if (button.dataset.action === 'restart') {
        leave(result.welcome);
      } else {
        window.location.reload();
      }
    } catch (error) {
      updateStatus(error instanceof TypeError ? 'Connessione non disponibile. Riprova.' : error.message, true);
      [...actions, ...editors].forEach(control => { control.disabled = false; });
    }
  }

  actions.forEach(button => button.addEventListener('click', () => { void run(button); }));
})();
