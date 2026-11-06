/* Keeps the live view current. Rows change in place, so an open child and keyboard focus stay put. */
(function () {
  'use strict';
  var root = document.querySelector('[data-live-url]');
  if (!root) { return; }
  var INTERVAL_MS = 5000;
  var url = root.getAttribute('data-live-url');
  var status = document.getElementById('live-status');
  var statusText = document.getElementById('live-status-text');
  var refresh = document.getElementById('live-refresh');
  var list = document.getElementById('live-children');
  var totals = document.getElementById('live-totals');
  var questions = document.getElementById('live-questions');
  var timer = null;
  var pending = false;
  var stopped = false;
  var lastTotals = totals.innerHTML;
  var lastQuestions = questions.innerHTML;

  refresh.hidden = true;

  function say(text, problem) {
    statusText.textContent = text;
    status.classList.toggle('live-problem', Boolean(problem));
  }

  function rowsById() {
    var rows = {};
    Array.prototype.forEach.call(list.querySelectorAll('[data-child]'), function (row) {
      rows[row.getAttribute('data-child')] = row;
    });
    return rows;
  }

  function fromHtml(html) {
    var holder = document.createElement('template');
    holder.innerHTML = html.trim();
    return holder.content.firstElementChild;
  }

  function replaceRow(old, html) {
    var fresh = fromHtml(html);
    var hadFocus = old.contains(document.activeElement);
    fresh.open = old.open;
    old.replaceWith(fresh);
    if (hadFocus) { fresh.querySelector('summary').focus(); }
  }

  function apply(data) {
    var rows = rowsById();
    var seen = {};
    data.rows.forEach(function (row) {
      seen[row.id] = true;
      var current = rows[row.id];
      if (!current) {
        list.appendChild(fromHtml(row.html));
      } else if (current.getAttribute('data-digest') !== row.digest) {
        replaceRow(current, row.html);
      }
    });
    Object.keys(rows).forEach(function (id) {
      if (!seen[id]) { rows[id].remove(); }
    });
    if (data.totals !== lastTotals) { totals.innerHTML = data.totals; lastTotals = data.totals; }
    if (data.questions !== lastQuestions) { questions.innerHTML = data.questions; lastQuestions = data.questions; }
    say(status.getAttribute('data-updated-label') + ' ' + data.updated, false);
  }

  function schedule() {
    clearTimeout(timer);
    if (!stopped && document.visibilityState === 'visible') { timer = setTimeout(check, INTERVAL_MS); }
  }

  function check() {
    if (pending || stopped) { return; }
    pending = true;
    fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } }).then(function (response) {
      if (response.status === 401) {
        stopped = true;
        say(status.getAttribute('data-signed-out'), true);
        refresh.href = root.getAttribute('data-login-url');
        refresh.hidden = false;
        return null;
      }
      if (!response.ok) { throw new Error('status ' + response.status); }
      return response.json().then(apply);
    }).catch(function () {
      say(status.getAttribute('data-reconnecting'), true);
    }).then(function () {
      pending = false;
      schedule();
    });
  }

  // A hidden tab stops asking, which also lets the 30-minute inactivity limit apply.
  document.addEventListener('visibilitychange', function () {
    clearTimeout(timer);
    if (document.visibilityState === 'visible') { check(); }
  });
  schedule();
}());
