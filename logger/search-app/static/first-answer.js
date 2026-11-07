(() => {
  const form = document.getElementById('first-answer-form');
  if (!form) return;

  const text = document.getElementById('first-answer-text');
  const assessment = document.getElementById('first-answer-confidence');
  const options = Array.from(assessment.querySelectorAll('input[name="confidence"]'));
  function confidence() {
    const selected = options.find(option => option.checked);
    return selected ? Number(selected.value) : null;
  }
  function updateAssessment() {
    const blank = !text.value.trim();
    assessment.hidden = blank;
    assessment.disabled = blank;
    if (blank) options.forEach(option => { option.checked = false; });
    showReadiness();
  }
  // Conferma stays tappable, so a child who taps early is told what is missing.
  function showReadiness() {
    document.getElementById('first-answer-confirm').classList.toggle('is-waiting', !text.value.trim() || confidence() === null);
    document.getElementById('first-answer-unknown').classList.toggle('is-waiting', Boolean(text.value.trim()));
  }
  function restore(value) {
    text.value = value.text;
    options.forEach(option => { option.checked = Number(option.value) === value.confidence; });
    updateAssessment();
  }
  updateAssessment();
  const dialog = document.getElementById('first-answer-unknown-dialog');
  document.getElementById('first-answer-unknown').addEventListener('click', () => {
    dialog.showModal();
  });
  document.getElementById('first-answer-cancel-unknown').addEventListener('click', () => {
    dialog.close();
  });
  // The browser words its own warnings in the tablet's language, so the form turns them off and asks in Italian.
  function ask(event, field, message) {
    event.preventDefault();
    field.setCustomValidity(message);
    field.reportValidity();
  }
  text.addEventListener('input', () => { text.setCustomValidity(''); updateAssessment(); });
  options.forEach(option => option.addEventListener('change', () => {
    options[0].setCustomValidity('');
    showReadiness();
  }));
  form.addEventListener('submit', (event) => {
    if (!text.value.trim()) ask(event, text, 'Scrivi una risposta oppure scegli “Non lo so”.');
    else if (confidence() === null) ask(event, options[0], 'Scegli quanto è giusta la tua risposta.');
  });

  const status = document.getElementById('first-answer-draft-status');
  if (!status) return;
  const retry = document.getElementById('first-answer-retry-draft');
  const fields = new FormData(form);
  const scope = {
    csrf_token: fields.get('csrf_token'),
    attempt_id: fields.get('attempt_id'),
    question_number: fields.get('question_number')
  };
  const bufferKey = `solFirstDraft:${scope.attempt_id}:${scope.question_number}`;
  let revision = Number(status.dataset.revision);
  let dirty = false;
  let saving = false;
  let blocked = false;
  let timer;

  function buffer() {
    try { sessionStorage.setItem(bufferKey, JSON.stringify({revision, text: text.value, confidence: confidence()})); }
    catch (_) { /* The field remains available even when browser storage is full. */ }
  }

  async function save() {
    if (saving || !dirty || blocked) return;
    const value = text.value;
    const selected = confidence();
    dirty = false;
    saving = true;
    try {
      const response = await fetch(status.dataset.url, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({...scope, text: value, confidence: selected, revision})
      });
      if (!response.ok) throw new Error(response.status === 409
        ? 'La bozza è cambiata. Il testo resta qui: ricarica la pagina per recuperarlo.'
        : 'Bozza non salvata. Il testo resta qui: riprova.');
      const saved = await response.json();
      if (saved.revision !== revision + 1 || saved.text !== value || saved.confidence !== selected) {
        throw new Error('Salvataggio non confermato. Riprova.');
      }
      revision = saved.revision;
      if (text.value === value && confidence() === selected) {
        try { sessionStorage.removeItem(bufferKey); } catch (_) { /* Optional recovery buffer. */ }
      } else {
        dirty = true;
        buffer();
      }
      retry.hidden = true;
      status.textContent = '';
    } catch (error) {
      dirty = true;
      blocked = true;
      buffer();
      status.textContent = error.message || 'Bozza non salvata. Riprova.';
      retry.hidden = false;
    } finally {
      saving = false;
      if (dirty && !blocked) timer = window.setTimeout(save, 600);
    }
  }

  function changed() {
    dirty = true;
    buffer();
    window.clearTimeout(timer);
    timer = window.setTimeout(save, 600);
  }
  text.addEventListener('input', changed);
  options.forEach(option => option.addEventListener('change', changed));
  retry.addEventListener('click', () => { blocked = false; void save(); });

  try {
    const local = JSON.parse(sessionStorage.getItem(bufferKey) || 'null');
    if (local && typeof local.text === 'string'
        && (local.text !== text.value || (local.confidence ?? null) !== confidence())) {
      if (local.revision === revision) {
        restore(local);
        changed();
      } else {
        // A stale tab must never silently overwrite a newer server draft.
        const recovery = document.createElement('details');
        const summary = document.createElement('summary');
        summary.textContent = 'Testo non salvato sul dispositivo';
        const recovered = document.createElement('textarea');
        recovered.className = 'first-answer-text';
        recovered.readOnly = true;
        recovered.setAttribute('aria-label', 'Testo recuperato dal dispositivo');
        recovered.value = local.text;
        const use = document.createElement('button');
        use.type = 'button';
        use.className = 'app-btn first-answer-outline';
        use.textContent = 'Usa questo testo';
        use.addEventListener('click', () => { restore(local); recovery.remove(); changed(); });
        recovery.append(summary, recovered, use);
        status.after(recovery);
      }
    }
  } catch (_) { /* An unreadable optional buffer cannot change the server draft. */ }
})();
