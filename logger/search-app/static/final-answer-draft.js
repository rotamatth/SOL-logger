(() => {
  const status = document.getElementById('final-answer-draft-status');
  if (!status) return;
  const text = document.getElementById('textarea_feedback');
  const retry = document.getElementById('final-answer-draft-retry');
  const scope = {
    csrf_token: status.dataset.csrfToken,
    attempt_id: status.dataset.attemptId,
    question_number: Number(status.dataset.questionNumber)
  };
  const key = `solFinalDraft:${scope.attempt_id}:${scope.question_number}`;
  const legacyKey = answerStorageKey();
  let revision = Number(status.dataset.revision);
  let dirty = false;
  let saving = false;
  let blocked = false;
  let paused = false;
  let timer;

  function remember() {
    try { sessionStorage.setItem(key, JSON.stringify({revision, text: text.value})); }
    catch (_) { /* Keep the live field even when optional browser storage is full. */ }
  }
  function forget() {
    try { sessionStorage.removeItem(key); sessionStorage.removeItem(legacyKey); }
    catch (_) { /* Server drafts and the current field remain authoritative. */ }
  }
  async function save() {
    if (paused || saving || !dirty || blocked) return;
    const value = text.value;
    dirty = false;
    saving = true;
    status.textContent = 'Salvataggio della bozza…';
    try {
      const response = await fetch(status.dataset.url, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({...scope, text: value, revision})
      });
      if (!response.ok) throw new Error(response.status === 409
        ? 'La bozza è cambiata. Conserva il testo e ricarica la pagina per recuperarlo.'
        : 'Bozza non salvata. Il testo resta qui: riprova.');
      const saved = await response.json();
      if (saved.revision !== revision + 1 || saved.text !== value) throw new Error('Salvataggio non confermato. Riprova.');
      if (paused) return;
      revision = saved.revision;
      dirty = text.value !== value;
      if (dirty) remember(); else forget();
      retry.hidden = true;
      status.textContent = dirty ? 'Modifiche da salvare…' : 'Bozza salvata.';
    } catch (error) {
      if (paused) return;
      dirty = true;
      blocked = true;
      remember();
      status.textContent = error.message || 'Bozza non salvata. Riprova.';
      retry.hidden = false;
    } finally {
      saving = false;
      if (dirty && !blocked && !paused) timer = window.setTimeout(save, 600);
    }
  }
  function update(value) {
    if (paused) return;
    text.value = value;
    dirty = true;
    remember();
    if (!blocked) status.textContent = 'Modifiche da salvare…';
    window.clearTimeout(timer);
    timer = window.setTimeout(save, 600);
  }
  function pause() {
    paused = true;
    window.clearTimeout(timer);
    retry.disabled = true;
  }
  window.finalAnswerDraft = {value: () => text.value, update, pause, clear: () => { pause(); forget(); }};
  retry.addEventListener('click', () => { blocked = false; save(); });

  // A confirmed pending upload owns its exact text, even if SQLite still has
  // an earlier draft. The existing confirmation-retry UI restores that intent.
  try {
    const pending = JSON.parse(localStorage.getItem(`solTaskSubmission:${window.SESSION_ID}:${window.TASK_NUMBER}`) || 'null');
    if (pending && typeof pending.answer === 'string') {
      text.value = pending.answer;
      pause();
      return;
    }
  } catch (_) { /* The existing pending-submission UI handles an unreadable intent. */ }

  function offerRecovery(value) {
    const recovery = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'Testo non salvato sul dispositivo';
    const recovered = document.createElement('textarea');
    recovered.readOnly = true;
    recovered.setAttribute('aria-label', 'Testo finale recuperato dal dispositivo');
    recovered.value = value;
    const use = document.createElement('button');
    use.type = 'button';
    use.className = 'app-btn app-btn-secondary';
    use.textContent = 'Usa questo testo';
    use.addEventListener('click', () => { recovery.remove(); update(value); });
    recovery.append(summary, recovered, use);
    status.after(recovery);
  }
  try {
    let local = JSON.parse(sessionStorage.getItem(key) || 'null');
    if (!local || typeof local.text !== 'string') {
      const old = sessionStorage.getItem(legacyKey);
      if (old !== null) local = {text: old, revision: 0};
    }
    if (local && typeof local.text === 'string') {
      if (local.text === text.value) forget();
      else if (local.revision === revision) update(local.text);
      else offerRecovery(local.text);
    }
  } catch (_) { /* An optional unreadable recovery buffer cannot overwrite SQLite. */ }
})();
