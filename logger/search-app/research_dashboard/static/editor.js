/*
 * Researcher edit protection (no third-party code, CSP script-src 'self').
 *
 * form[data-guard]          warn before leaving with unsaved changes.
 * form[data-recovery-key]   additionally autosave a private recovery copy on the
 *                           server (8 h, this browser only), offer it back after a
 *                           reload, language switch or re-login, and refresh the
 *                           CSRF token after signing in again in another tab.
 *
 * The recovery copy never changes study settings: only Save draft / Approve do.
 * When the server is unreachable or the login expired, text stays in this page only.
 */
(function () {
  'use strict';

  var body = document.body;

  /* In-page menus (<details class="preparation-menu">): Escape or a click outside closes them. */
  function openMenus() {
    return Array.prototype.slice.call(document.querySelectorAll('details.preparation-menu[open]'));
  }
  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') { return; }
    openMenus().forEach(function (menu) {
      menu.open = false;
      var summary = menu.querySelector('summary');
      if (summary && menu.contains(document.activeElement)) { summary.focus(); }
    });
  });
  document.addEventListener('click', function (event) {
    openMenus().forEach(function (menu) {
      if (!menu.contains(event.target)) { menu.open = false; }
    });
  });

  // Bulk downloads always refer to the checkboxes in the currently displayed scope.
  var selectionControls = document.querySelector('[data-selection-controls]');
  if (selectionControls) {
    var rows = Array.prototype.slice.call(document.querySelectorAll('input[name="participant"][form="selected-export"]:not(:disabled)'));
    var selectAll = selectionControls.querySelector('[data-select-all]');
    var selectionCount = selectionControls.querySelector('[data-selection-count]');
    function updateSelection() {
      var count = rows.filter(function (row) { return row.checked; }).length;
      selectionCount.textContent = String(count);
      selectAll.checked = rows.length > 0 && count === rows.length;
      selectAll.indeterminate = count > 0 && count < rows.length;
      selectAll.disabled = !rows.length;
    }
    selectAll.addEventListener('change', function () {
      rows.forEach(function (row) { row.checked = selectAll.checked; });
      updateSelection();
    });
    rows.forEach(function (row) { row.addEventListener('change', updateSelection); });
    window.addEventListener('pageshow', updateSelection);
    updateSelection();
    selectionControls.hidden = false;
  }

  var jump = document.querySelector('[data-participant-jump]');
  if (jump) {
    var jumpInput = jump.querySelector('input');
    var jumpResult = jump.querySelector('[data-jump-result]');
    var lastJump = '', jumpIndex = -1;
    function jumpToId() {
      var value = jumpInput.value.trim();
      var matches = Array.prototype.filter.call(document.querySelectorAll('.participant-link[data-participant-id]'), function (link) {
        return link.getAttribute('data-participant-id') === value;
      }).map(function (link) { return link.closest('tr'); });
      document.querySelectorAll('.participant-jump-target').forEach(function (row) { row.classList.remove('participant-jump-target'); });
      if (!value || !matches.length) {
        jumpResult.textContent = jump.getAttribute('data-missing');
        jumpInput.focus();
        return;
      }
      jumpIndex = value === lastJump ? (jumpIndex + 1) % matches.length : 0;
      lastJump = value;
      var row = matches[jumpIndex];
      row.classList.add('participant-jump-target');
      row.querySelector('.participant-link').focus({ preventScroll: true });
      row.scrollIntoView({ block: 'center' });
      jumpResult.textContent = jump.getAttribute('data-participant-label') + ' ' + value + ' · ' + (jumpIndex + 1) + ' / ' + matches.length;
    }
    jump.querySelector('button').addEventListener('click', jumpToId);
    jumpInput.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') { event.preventDefault(); jumpToId(); }
    });
    jump.hidden = false;
  }

  var forms = Array.prototype.slice.call(document.querySelectorAll('form[data-guard]'));
  if (!body) { return; }

  var messages = {};
  try { messages = JSON.parse(body.getAttribute('data-editor-messages') || '{}'); } catch (error) { messages = {}; }
  function text(key) { return messages[key] || key; }

  var recoveryUrl = body.getAttribute('data-editor-recovery-url') || '';
  var sessionUrl = body.getAttribute('data-editor-session-url') || '';
  var loginUrl = body.getAttribute('data-editor-login-url') || '';
  var logoutCheckUrl = body.getAttribute('data-editor-logout-check-url') || '';
  var AUTOSAVE_DELAY = 1200;
  var FLUSH_ATTEMPTS = 4;
  var submitting = false;
  var canFetch = !!(window.fetch && window.URLSearchParams);

  function editable(form) {
    return Array.prototype.filter.call(form.elements, function (field) {
      if (!field.name || field.disabled) { return false; }
      var type = (field.type || '').toLowerCase();
      return ['hidden', 'submit', 'button', 'reset', 'file'].indexOf(type) === -1;
    });
  }

  function serialize(form) {
    return JSON.stringify(editable(form).map(function (field) {
      var type = (field.type || '').toLowerCase();
      return [field.name, type === 'checkbox' || type === 'radio' ? field.checked : field.value];
    }));
  }

  function setCsrf(token) {
    if (!token) { return; }
    Array.prototype.forEach.call(document.querySelectorAll('input[name="csrf"]'), function (input) {
      input.value = token;
    });
  }

  function csrfValue() {
    var input = document.querySelector('input[name="csrf"]');
    return input ? input.value : '';
  }

  /*
   * Login check before anything is sent: refreshes the CSRF token (after signing in
   * again in another tab) and keeps the login alive. Resolves to the HTTP status.
   * It never touches a recovery copy, so a stale tab cannot adopt another tab's version.
   */
  function authCheck() {
    if (!sessionUrl || !canFetch) { return Promise.resolve(200); }
    return fetch(sessionUrl, { credentials: 'same-origin', cache: 'no-store', headers: { 'Accept': 'application/json' } })
      .then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (payload) {
          if (response.status === 200) { setCsrf(payload.csrf); }
          return response.status;
        });
      });
  }

  function sameFields(left, right) {
    if (!left || !right) { return false; }
    var keys = Object.keys(left);
    return keys.length === Object.keys(right).length && keys.every(function (name) { return left[name] === right[name]; });
  }

  /* ---------- Private server recovery for long editor forms ---------- */

  function Recovery(form) {
    this.form = form;
    this.key = form.getAttribute('data-recovery-key');
    this.names = (form.getAttribute('data-recovery-fields') || '').split(/\s+/).filter(Boolean);
    this.sequence = 0;
    this.protectedState = null;
    this.timer = null;
    this.inflight = null;
    this.state = 'saved';
    this.ready = false;
    this.started = null;
    this.discarding = false;
    this.epoch = 0;
    this.needsRebind = false;
    this.statusNode = form.querySelector('[data-editor-status]');
    this.sequenceInput = form.querySelector('input[name="recovery_sequence"]');
  }

  Recovery.prototype.fields = function () {
    var form = this.form, values = {};
    this.names.forEach(function (name) {
      var field = form.elements.namedItem(name);
      if (field && typeof field.value === 'string') { values[name] = field.value; }
    });
    return values;
  };

  Recovery.prototype.textFields = function (values) {
    var result = {};
    Object.keys(values || {}).forEach(function (name) {
      if (name !== 'draft_token' && name !== 'revision') { result[name] = values[name]; }
    });
    return result;
  };

  Recovery.prototype.apply = function (values, textOnly) {
    var form = this.form;
    var source = textOnly ? this.textFields(values) : values;
    Object.keys(source).forEach(function (name) {
      var field = form.elements.namedItem(name);
      if (field && typeof source[name] === 'string') { field.value = source[name]; }
    });
  };

  Recovery.prototype.setSequence = function (sequence) {
    if (typeof sequence === 'number') {
      this.sequence = sequence;
      if (this.sequenceInput) { this.sequenceInput.value = String(sequence); }
    }
  };

  Recovery.prototype.isProtected = function () {
    return this.protectedState !== null && this.protectedState === serialize(this.form);
  };

  Recovery.prototype.status = function (state, extra) {
    this.state = state;
    var node = this.statusNode;
    if (!node) { return; }
    var tones = { saved: 'muted', dirty: 'warn', protecting: 'busy', protected: 'ok', recovered: 'warn',
                  failed: 'error', conflict: 'error', expired: 'error' };
    var keys = { saved: 'editor_saved', dirty: 'editor_unsaved', protecting: 'editor_protecting',
                 protected: 'editor_protected', recovered: 'editor_recovered', failed: 'editor_failed',
                 conflict: 'editor_conflict', expired: 'editor_expired' };
    node.textContent = text(keys[state]);
    node.setAttribute('data-tone', tones[state]);
    var self = this;
    if (state === 'failed' || state === 'expired') {
      if (state === 'expired' && loginUrl) {
        var link = document.createElement('a');
        link.className = 'button';
        link.href = loginUrl;
        link.target = '_blank';
        link.rel = 'noopener';
        link.textContent = text('editor_sign_in');
        node.appendChild(link);
      }
      node.appendChild(button(text('editor_retry'), function () { self.retry(); }));
    }
    if (state === 'conflict') {
      node.appendChild(button(text('editor_copy'), function () { copyText(self.plainText(self.fields())); }));
    }
    if (state === 'recovered' && extra && extra.discard) {
      node.appendChild(button(text('editor_discard_recovery'), extra.discard));
    }
  };

  Recovery.prototype.plainText = function (values) {
    return this.names.filter(function (name) { return name !== 'draft_token' && name !== 'revision'; })
      .map(function (name) { return values[name] || ''; })
      .filter(Boolean).join('\n\n');
  };

  Recovery.prototype.request = function (method, params) {
    var options = { method: method, credentials: 'same-origin', headers: { 'Accept': 'application/json' } };
    var url = recoveryUrl;
    if (method === 'GET') {
      url += (url.indexOf('?') === -1 ? '?' : '&') + 'key=' + encodeURIComponent(this.key);
    } else {
      var data = new URLSearchParams();
      data.set('csrf', csrfValue());
      data.set('key', this.key);
      Object.keys(params || {}).forEach(function (name) { data.set(name, params[name]); });
      options.body = data;
      options.headers['Content-Type'] = 'application/x-www-form-urlencoded';
    }
    return fetch(url, options).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (payload) {
        return { status: response.status, payload: payload };
      });
    });
  };

  /*
   * Compare-and-swap save of the current fields. Resolves true when this request was
   * stored; the form may have changed meanwhile, so callers that need the *current*
   * text protected use flush().
   */
  Recovery.prototype.save = function (retried) {
    var self = this;
    if (this.discarding || this.needsRebind) { return Promise.resolve(false); }
    if (this.inflight) { return this.inflight; }
    if (this.isProtected()) {
      if (this.state === 'expired' || this.state === 'failed') { this.status('protected'); }
      return Promise.resolve(true);
    }
    var snapshot = serialize(this.form);
    var epoch = this.epoch;
    var sent = this.fields();
    this.status('protecting');
    var pending = this.request('POST', {
      action: 'save', sequence: String(this.sequence), fields: JSON.stringify(sent)
    }).then(function (result) {
      if (self.epoch !== epoch) { return false; }
      if (result.status === 200 && result.payload.recovery) {
        setCsrf(result.payload.csrf);
        return self.stored(result.payload.recovery.sequence, snapshot);
      }
      if (result.status === 401) { self.status('expired'); return false; }
      if (result.status === 409) { return self.reconcile(sent, snapshot); }
      if (!retried && result.payload && result.payload.error === 'csrf_error') {
        // Signed in again elsewhere: fetch the new token and try once more.
        return authCheck().then(function (status) {
          if (status === 401) { self.status('expired'); return false; }
          self.inflight = null;
          return self.save(true);
        });
      }
      if (self.epoch === epoch) { self.status('failed'); }
      return false;
    });
    var operation = pending.then(function (stored) {
      if (self.inflight === operation) { self.inflight = null; }
      return stored;
    }, function () {
      if (self.inflight === operation) { self.inflight = null; }
      if (self.epoch === epoch) { self.status('failed'); }
      return false;
    });
    this.inflight = operation;
    return this.inflight;
  };

  Recovery.prototype.stored = function (sequence, snapshot) {
    this.setSequence(sequence);
    this.protectedState = snapshot;
    if (serialize(this.form) !== snapshot) { this.schedule(); } else { this.status('protected'); }
    return true;
  };

  /*
   * The server copy moved on. If it holds exactly the text this tab sent (our own
   * earlier save whose answer was lost), continue from it; otherwise another tab wrote
   * it: never overwrite that copy, keep this tab's text on the page and say so.
   */
  Recovery.prototype.reconcile = function (sent, snapshot) {
    var self = this;
    var epoch = this.epoch;
    return this.request('GET').then(function (result) {
      if (self.epoch !== epoch) { return false; }
      var record = result.status === 200 ? result.payload.recovery : null;
      if (record && sameFields(record.fields, sent)) { return self.stored(record.sequence, snapshot); }
      self.status('conflict');
      return false;
    }, function () {
      if (self.epoch === epoch) { self.status('conflict'); }
      return false;
    });
  };

  Recovery.prototype.schedule = function () {
    var self = this;
    clearTimeout(this.timer);
    if (this.discarding || this.needsRebind) { return; }
    if (!this.ready) { return; }
    if (this.isProtected()) { this.status('protected'); return; }
    if (this.state !== 'expired' && this.state !== 'conflict') { this.status('dirty'); }
    this.timer = setTimeout(function () {
      if (self.state !== 'conflict') { self.save(); }
    }, AUTOSAVE_DELAY);
  };

  /*
   * Resolve true only once the text currently in the form is stored. A save that was
   * already running covers older text, so keep saving until the snapshot matches.
   */
  Recovery.prototype.flush = function (attempt) {
    var self = this;
    attempt = attempt || 0;
    clearTimeout(this.timer);
    if (this.discarding || this.needsRebind) { return Promise.resolve(false); }
    if (this.isProtected()) { return Promise.resolve(true); }
    if (!this.ready) { return this.started.then(function () { return self.flush(attempt); }); }
    if (this.state === 'conflict' || attempt >= FLUSH_ATTEMPTS) { return Promise.resolve(false); }
    return this.save().then(function (stored) {
      return stored && self.flush(attempt + 1);
    });
  };

  Recovery.prototype.retry = function () {
    var self = this;
    var epoch = this.epoch;
    authCheck().then(function (status) {
      if (self.epoch !== epoch) { return; }
      if (status === 401) { self.status('expired'); return; }
      if (status !== 200) { self.status('failed'); return; }
      if (!self.needsRebind) { self.save(); return; }
      if (self.blockedCsrf === csrfValue()) { self.status('expired'); return; }
      // A confirmed sign-out removes the owner cookie and its copies. Adopt a
      // fresh empty scope only after signing in; never replace another tab's text.
      Promise.resolve(self.inflight).then(function () { return self.request('GET'); }).then(function (result) {
        if (self.epoch !== epoch) { return; }
        if (result.status !== 200) { self.status(result.status === 401 ? 'expired' : 'failed'); return; }
        var record = result.payload.recovery;
        if (record && record.fields && !sameFields(record.fields, self.fields())) {
          self.status('conflict');
          return;
        }
        self.setSequence(record ? record.sequence : 0);
        self.needsRebind = false;
        self.protectedState = null;
        self.save();
      }).catch(function () { if (self.epoch === epoch) { self.status('failed'); } });
    }, function () { if (self.epoch === epoch) { self.status('failed'); } });
  };

  Recovery.prototype.discard = function () {
    if (this.discarding) { return; }
    if (!window.confirm(text('editor_discard_confirm'))) { return; }
    var self = this;
    this.discarding = true;
    clearTimeout(this.timer);
    // Finish any save already sent before clearing its acknowledged version.
    // New input must not start another autosave while the discard is pending.
    return Promise.resolve(this.inflight || this.started).then(function () {
      return self.request('POST', { action: 'clear', sequence: String(self.sequence) });
    }).then(function (result) {
      if (result.status !== 200) {
        self.discarding = false;
        self.protectedState = null;
        self.status(result.status === 401 ? 'expired' : result.status === 409 ? 'conflict' : 'failed');
        return false;
      }
      self.protectedState = null;
      submitting = true;  // Reload the saved version without a leave warning.
      window.location.href = window.location.href.split('#')[0];
      return true;
    }, function () {
      self.discarding = false;
      self.protectedState = null;
      self.status('failed');
      return false;
    });
  };

  Recovery.prototype.banner = function (values, introKey) {
    var self = this;
    var box = document.createElement('div');
    box.className = 'notice warning recovery-banner';
    box.setAttribute('role', 'status');
    var intro = document.createElement('p');
    intro.textContent = text(introKey);
    box.appendChild(intro);
    var list = document.createElement('ol');
    ['question_0', 'question_1', 'question_2'].forEach(function (name) {
      if (values[name]) {
        var item = document.createElement('li');
        item.textContent = values[name];
        list.appendChild(item);
      }
    });
    if (list.children.length) { box.appendChild(list); }
    var actions = document.createElement('div');
    actions.className = 'actions';
    actions.appendChild(button(text('editor_use_recovered'), function () {
      self.apply(values, true);
      box.parentNode.removeChild(box);
      self.protectedState = null;
      self.schedule();
    }, 'primary'));
    actions.appendChild(button(text('editor_copy'), function () { copyText(self.plainText(values)); }));
    actions.appendChild(button(text('editor_discard_recovery'), function () { self.discard(); }));
    box.appendChild(actions);
    this.form.parentNode.insertBefore(box, this.form);
  };

  /*
   * Load the private copy once. Only the page as the server rendered it counts as
   * safe; anything typed while this request runs is kept and protected afterwards,
   * and a recovered copy never replaces it silently.
   */
  Recovery.prototype.start = function () {
    var self = this;
    var unsavedPage = this.form.hasAttribute('data-unsaved');
    var rendered = serialize(this.form);
    var renderedFields = this.fields();
    var epoch = this.epoch;
    this.started = this.request('GET').then(function (result) {
      self.ready = true;
      if (self.epoch !== epoch) { return; }
      if (result.status === 401) { self.status('expired'); return; }
      if (result.status !== 200) { self.status('failed'); return; }
      setCsrf(result.payload.csrf);
      var record = result.payload.recovery;
      if (record) { self.setSequence(record.sequence); }  // The version this page builds on.
      if (unsavedPage) {
        // This page shows text the server just returned (preview or validation
        // error): it is newer than any earlier copy, so protect it right away.
        self.save();
        return;
      }
      var typed = serialize(self.form) !== rendered;
      self.protectedState = rendered;
      var saved = record && record.fields;
      var differs = saved && Object.keys(self.textFields(saved)).some(function (name) {
        return saved[name] !== renderedFields[name];
      });
      if (!differs) {
        self.status('saved');
      } else if (saved.revision === renderedFields.revision && !typed) {
        // Same settings version: put the recovered text back into the form.
        self.apply(saved, false);
        self.protectedState = serialize(self.form);
        self.status('recovered', { discard: function () { self.discard(); } });
      } else {
        // Settings changed since, or the researcher already started typing:
        // never overwrite silently; let the researcher choose.
        self.status('saved');
        self.banner(saved, typed ? 'editor_recovered_choice' : 'editor_revision_conflict');
      }
      if (typed) { self.schedule(); }
    }).catch(function () {
      self.ready = true;
      self.status('failed');
    });
  };

  /* ---------- helpers ---------- */

  function button(label, handler, className) {
    var node = document.createElement('button');
    node.type = 'button';
    if (className) { node.className = className; }
    node.textContent = label;
    node.addEventListener('click', handler);
    return node;
  }

  function copyText(value) {
    function fallback() {
      var area = document.createElement('textarea');
      area.className = 'recovery-copy-buffer';
      area.value = value;
      document.body.appendChild(area);
      area.select();
      try { document.execCommand('copy'); } catch (error) { /* the text is still on the page */ }
      document.body.removeChild(area);
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(value).catch(fallback);
    } else {
      fallback();
    }
  }

  /* A message next to the submit button; called without a key it removes the message. */
  function formNotice(form, submitter, key, withLogin) {
    var old = form.querySelector('.editor-form-notice');
    if (old) { old.parentNode.removeChild(old); }
    if (!key) { return; }
    var node = document.createElement('p');
    node.className = 'notice warning editor-form-notice';
    node.setAttribute('role', 'alert');
    node.textContent = text(key) + ' ';
    if (withLogin && loginUrl) {
      var link = document.createElement('a');
      link.href = loginUrl;
      link.target = '_blank';
      link.rel = 'noopener';
      link.textContent = text('editor_sign_in');
      node.appendChild(link);
    }
    var anchor = submitter && submitter.form === form ? submitter : null;
    if (anchor) { anchor.parentNode.insertBefore(node, anchor); } else { form.appendChild(node); }
  }

  /* Submit without firing the submit event again, keeping the clicked button's value. */
  function submitNatively(form, submitter) {
    Array.prototype.forEach.call(form.querySelectorAll('input[data-editor-submitter]'), function (input) {
      input.parentNode.removeChild(input);
    });
    if (submitter && submitter.name && submitter.form === form) {
      var hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = submitter.name;
      hidden.value = submitter.value;
      hidden.setAttribute('data-editor-submitter', '');
      form.appendChild(hidden);
    }
    submitting = true;
    HTMLFormElement.prototype.submit.call(form);
  }

  /* ---------- wiring ---------- */

  var guards = forms.map(function (form) {
    var guard = { form: form, initial: serialize(form), recovery: null, pending: false };
    if (recoveryUrl && form.hasAttribute('data-recovery-key') && canFetch) {
      guard.recovery = new Recovery(form);
    }
    guard.dirty = function () { return serialize(form) !== guard.initial || form.hasAttribute('data-unsaved'); };
    guard.safe = function () { return !guard.dirty() || (guard.recovery && guard.recovery.isProtected()); };

    function changed() {
      if (guard.recovery) { guard.recovery.schedule(); }
      publishTab();
    }
    form.addEventListener('input', changed);
    form.addEventListener('change', changed);

    // Enter in a one-line field must not trigger the first (library) button.
    form.addEventListener('keydown', function (event) {
      var target = event.target;
      if (event.key === 'Enter' && target && target.tagName === 'INPUT' && guard.recovery) {
        event.preventDefault();
      }
    });

    form.addEventListener('submit', function (event) {
      var submitter = event.submitter || document.activeElement;
      var question = submitter && submitter.getAttribute && submitter.getAttribute('data-confirm');
      if (question && !window.confirm(question)) { event.preventDefault(); return; }
      if (!sessionUrl || !canFetch) { submitting = true; return; }
      // Check the login first so an expired session never swallows what was typed.
      event.preventDefault();
      if (guard.pending) { return; }
      guard.pending = true;
      var recovery = guard.recovery;
      if (recovery) { clearTimeout(recovery.timer); }
      authCheck().then(function (status) {
        if (status !== 200) {
          guard.pending = false;
          if (recovery) {
            recovery.status(status === 401 ? 'expired' : 'failed');  // Its status line explains.
          } else {
            formNotice(form, submitter, status === 401 ? 'editor_session_expired' : 'editor_submit_failed', status === 401);
          }
          return;
        }
        formNotice(form);
        // The explicit save goes ahead even if the private copy cannot be updated.
        return (recovery ? recovery.flush() : Promise.resolve(true)).then(function () {
          submitNatively(form, submitter);
        });
      }).catch(function () {
        guard.pending = false;
        if (recovery) { recovery.status('failed'); } else { formNotice(form, submitter, 'editor_submit_failed', false); }
      });
    });

    if (guard.recovery) { guard.recovery.start(); }
    return guard;
  });

  function unsafeGuards() {
    return guards.filter(function (guard) { return !guard.safe(); });
  }

  // Cross-tab notices contain flags only, never questions, IDs, tokens or URLs.
  // Stored flags also cover a suspended tab that cannot answer a live query.
  var tabId = Date.now().toString(36) + Math.random().toString(36).slice(2);
  var tabPrefix = 'sol-research-unsaved:';
  var tabKey = tabPrefix + tabId;
  var channel = null;
  var tabRequests = {};
  try { if (window.BroadcastChannel) { channel = new BroadcastChannel('sol-research-editor'); } } catch (error) { /* storage fallback */ }

  function announce(message) {
    message.sender = tabId;
    if (channel) { channel.postMessage(message); return; }
    try {
      localStorage.setItem('sol-research-tab-message', JSON.stringify(message));
      localStorage.removeItem('sol-research-tab-message');
    } catch (error) { /* Logout also checks server copies. */ }
  }

  function dirtyTab() { return guards.some(function (guard) { return guard.dirty(); }); }

  function publishTab() {
    try {
      if (dirtyTab()) { localStorage.setItem(tabKey, String(Date.now())); }
      else { localStorage.removeItem(tabKey); }
    } catch (error) { /* Live queries and server copies remain available. */ }
  }

  function storedOtherEdits() {
    try {
      return Object.keys(localStorage).some(function (key) {
        if (key === tabKey || key.indexOf(tabPrefix) !== 0) { return false; }
        var updated = Number(localStorage.getItem(key));
        if (Date.now() - updated > 8 * 60 * 60 * 1000) { localStorage.removeItem(key); return false; }
        return updated > 0;
      });
    } catch (error) { return false; }
  }

  function receive(message) {
    if (!message || message.sender === tabId) { return; }
    if (message.type === 'query') {
      announce({ type: 'answer', nonce: message.nonce, dirty: dirtyTab() });
    } else if (message.type === 'answer' && message.dirty && tabRequests[message.nonce]) {
      tabRequests[message.nonce].dirty = true;
    } else if (message.type === 'logout') {
      guards.forEach(function (guard) {
        if (guard.recovery) {
          var recovery = guard.recovery;
          clearTimeout(recovery.timer);
          recovery.epoch += 1;
          recovery.needsRebind = true;
          recovery.blockedCsrf = csrfValue();
          recovery.protectedState = null;
          recovery.status('expired');
        } else if (guard.dirty()) {
          formNotice(guard.form, null, 'editor_signed_out_elsewhere', true);
        }
      });
    }
  }
  if (channel) { channel.onmessage = function (event) { receive(event.data); }; }
  window.addEventListener('storage', function (event) {
    if (event.key !== 'sol-research-tab-message' || !event.newValue) { return; }
    try { receive(JSON.parse(event.newValue)); } catch (error) { /* Ignore malformed flags. */ }
  });
  window.addEventListener('pagehide', function (event) {
    if (event.persisted) { publishTab(); return; }
    try { localStorage.removeItem(tabKey); } catch (error) { /* unavailable */ }
  });
  window.addEventListener('pageshow', publishTab);
  document.addEventListener('visibilitychange', publishTab);
  setInterval(publishTab, 30000);
  publishTab();
  guards.forEach(function (guard) { if (guard.recovery) { guard.recovery.started.then(publishTab); } });

  function checkOtherTabs() {
    var nonce = tabId + ':' + Date.now();
    var result = { dirty: storedOtherEdits() };
    tabRequests[nonce] = result;
    announce({ type: 'query', nonce: nonce });
    return new Promise(function (resolve) {
      setTimeout(function () { delete tabRequests[nonce]; resolve(result.dirty); }, 200);
    });
  }

  function logoutCheck() {
    if (!canFetch || !logoutCheckUrl) { return Promise.resolve({ checked: false }); }
    var timer;
    var check = fetch(logoutCheckUrl, { credentials: 'same-origin', cache: 'no-store', headers: { 'Accept': 'application/json' } })
      .then(function (response) {
        return response.json().then(function (payload) {
          setCsrf(payload.csrf);
          return { checked: response.status === 200, hasRecovery: payload.has_recovery };
        });
      }).catch(function () { return { checked: false }; });
    return Promise.race([check, new Promise(function (resolve) {
      timer = setTimeout(function () { resolve({ checked: false }); }, 4000);
    })]).then(function (result) { clearTimeout(timer); return result; });
  }

  // A normal submission leaves sibling forms behind. Logout additionally checks
  // every tab and durable copy before its existing revocation endpoint is called.
  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (form.hasAttribute('data-clears-editor-recovery')) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (form.hasAttribute('data-logout-pending')) { return; }
      form.setAttribute('data-logout-pending', '');
      var submitter = event.submitter;
      Promise.all([checkOtherTabs(), logoutCheck()]).then(function (results) {
        form.removeAttribute('data-logout-pending');
        var copies = results[1];
        var warning = !copies.checked ? 'editor_logout_check_failed' :
          dirtyTab() || results[0] || copies.hasRecovery ? 'editor_logout_confirm' : null;
        if (warning && !window.confirm(text(warning))) { return; }
        if (!canFetch) { submitNatively(form, submitter); return; }
        var data = new URLSearchParams(new FormData(form));
        form.setAttribute('data-logout-pending', '');
        fetch(form.action, { method: 'POST', credentials: 'same-origin', body: data,
          headers: { 'Accept': 'application/json' } }).then(function (response) {
          return response.json().catch(function () { return {}; }).then(function (payload) {
            form.removeAttribute('data-logout-pending');
            if ((response.status === 200 && payload.logged_out) || response.status === 401) {
              // Notify only after revocation; an earlier notification can race a retry.
              announce({ type: 'logout' });
              submitting = true;
              window.location.href = payload.login_url || loginUrl;
            } else { formNotice(form, submitter, 'editor_submit_failed', false); }
          });
        }).catch(function () {
          form.removeAttribute('data-logout-pending');
          // Delivery is uncertain. Other tabs must not claim their copies survived.
          announce({ type: 'logout' });
          receive({ type: 'logout', sender: 'logout-local' });
          formNotice(form, submitter, 'editor_submit_failed', false);
        });
      });
      return;
    }
    var otherEdits = guards.some(function (guard) {
      return guard.form !== form && !guard.safe();
    });
    if (!otherEdits) { return; }
    if (!window.confirm(text('editor_leave_unsaved'))) {
      event.preventDefault();
      event.stopImmediatePropagation();
    } else if (!form.hasAttribute('data-guard')) {
      // The user already confirmed this ordinary form navigation.
      submitting = true;
    }
  }, true);

  window.addEventListener('beforeunload', function (event) {
    if (submitting || !unsafeGuards().length) { return; }
    event.preventDefault();
    event.returnValue = '';
  });

  // Links (including EN/IT): protect first, then leave; ask only if protection failed.
  document.addEventListener('click', function (event) {
    var link = event.target && event.target.closest ? event.target.closest('a[href]') : null;
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey
        || event.shiftKey || event.altKey || link.target === '_blank' || link.hasAttribute('download')) { return; }
    var href = link.getAttribute('href');
    if (!href || href.charAt(0) === '#') { return; }
    var pending = unsafeGuards();
    if (!pending.length) { return; }
    event.preventDefault();
    var plainForms = pending.some(function (guard) { return !guard.recovery; });
    Promise.all(pending.map(function (guard) {
      return guard.recovery ? guard.recovery.flush() : Promise.resolve(false);
    })).then(function (results) {
      var safe = results.every(Boolean);
      if (safe || window.confirm(text(plainForms ? 'editor_leave_unsaved' : 'editor_leave_confirm'))) {
        submitting = true;
        window.location.href = link.href;
      }
    });
  });

  // Back/forward cache: the page is live again, so the leave warning applies again.
  window.addEventListener('pageshow', function (event) {
    if (!event.persisted) { return; }
    submitting = false;
    guards.forEach(function (guard) { guard.pending = false; });
  });

  // Coming back to the tab (for example after signing in elsewhere): retry protection.
  window.addEventListener('focus', function () {
    guards.forEach(function (guard) {
      var recovery = guard.recovery;
      if (recovery && (recovery.state === 'expired' || recovery.state === 'failed') && guard.dirty()) {
        recovery.retry();
      }
    });
  });
}());
