(() => {
  const form = document.getElementById('first-answer-form');
  if (!form) return;

  const text = document.getElementById('first-answer-text');
  const dialog = document.getElementById('first-answer-unknown-dialog');
  document.getElementById('first-answer-unknown').addEventListener('click', () => {
    dialog.showModal();
  });
  document.getElementById('first-answer-cancel-unknown').addEventListener('click', () => {
    dialog.close();
  });
  text.addEventListener('input', () => text.setCustomValidity(''));
  form.addEventListener('submit', (event) => {
    if (!text.value.trim()) {
      event.preventDefault();
      text.setCustomValidity('Scrivi una risposta oppure scegli “Non lo so”.');
      text.reportValidity();
    }
  });
})();
