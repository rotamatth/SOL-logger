/*
 * "Un momento…" (templates/busy.html): the answers are saved, but the server was busy recording the next step.
 * The page reloads itself, 3 s after the first time, 5 s after the second and every 10 s after that; from the
 * fourth try in a row it also asks for an adult. Tries older than two minutes no longer count. The start page's
 * version (nothing saved yet) does not reload by itself: its Riprova goes back to the ID page.
 */
(function () {
  'use strict';
  var box = document.getElementById('busy-retry');
  if (!box) { return; }
  var url = box.getAttribute('data-retry-url');
  var key = 'solBusyRetry:' + url;
  var tries = 0;
  try {
    var saved = JSON.parse(sessionStorage.getItem(key) || 'null');
    if (saved && Date.now() - saved.at < 120000) { tries = saved.tries; }
  } catch (_) { tries = 0; }
  if (tries >= 3) { document.getElementById('busy-adult').hidden = false; }

  function counted() {
    try { sessionStorage.setItem(key, JSON.stringify({ tries: tries + 1, at: Date.now() })); } catch (_) { /* Optional. */ }
  }
  document.getElementById('busy-retry-btn').addEventListener('click', counted);
  if (box.getAttribute('data-auto') !== '1') { return; }
  window.setTimeout(function () {
    counted();
    window.location.replace(url);
  }, [3000, 5000][tries] || 10000);
}());
