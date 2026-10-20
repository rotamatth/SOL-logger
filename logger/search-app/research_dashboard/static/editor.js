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

  var forms = Array.prototype.slice.call(document.querySelectorAll('form[data-guard]'));
  if (!body || !forms.length) { return; }

  var messages = {};
  try { messages = JSON.parse(body.getAttribute('data-editor-messages') || '{}'); } catch (error) { messages = {}; }
  function text(key) { return messages[key] || key; }

  var recoveryUrl = body.getAttribute('data-editor-recovery-url') || '';
  var loginUrl = body.getAttribute('data-editor-login-url') || '';
  var AUTOSAVE_DELAY = 1200;
  var submitting = false;

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

  /* Re-read the server copy: refreshes the CSRF token and keeps the login alive. */
  Recovery.prototype.check = function () {
    var self = this;
    return this.request('GET').then(function (result) {
      if (result.status === 200) {
        setCsrf(result.payload.csrf);
        var record = result.payload.recovery;
        if (record) { self.setSequence(record.sequence); }
      }
      return result;
    });
  };

  Recovery.prototype.save = function (retried) {
    var self = this;
    if (this.inflight) { return this.inflight; }
    if (this.isProtected()) { return Promise.resolve(true); }
    var snapshot = serialize(this.form);
    this.status('protecting');
    this.inflight = this.request('POST', {
      action: 'save', sequence: String(this.sequence), fields: JSON.stringify(this.fields())
    }).then(function (result) {
      self.inflight = null;
      if (result.status === 200 && result.payload.recovery) {
        setCsrf(result.payload.csrf);
        self.setSequence(result.payload.recovery.sequence);
        self.protectedState = snapshot;
        if (serialize(self.form) !== snapshot) { self.schedule(); return true; }
        self.status('protected');
        return true;
      }
      if (result.status === 401) { self.status('expired'); return false; }
      if (result.status === 409) { self.status('conflict'); return false; }
      if (!retried && result.payload && result.payload.error === 'csrf_error') {
        // Signed in again elsewhere: fetch the new token and try once more.
        return self.check().then(function (checked) {
          if (checked.status === 401) { self.status('expired'); return false; }
          return self.save(true);
        });
      }
      self.status('failed');
      return false;
    }, function () {
      self.inflight = null;
      self.status('failed');
      return false;
    });
    return this.inflight;
  };

  Recovery.prototype.schedule = function () {
    var self = this;
    clearTimeout(this.timer);
    if (!this.ready) { return; }
    if (this.isProtected()) { this.status('protected'); return; }
    if (this.state !== 'expired' && this.state !== 'conflict') { this.status('dirty'); }
    this.timer = setTimeout(function () {
      if (self.state !== 'conflict') { self.save(); }
    }, AUTOSAVE_DELAY);
  };

  Recovery.prototype.flush = function () {
    clearTimeout(this.timer);
    if (!this.ready || this.isProtected()) { return Promise.resolve(true); }
    return this.save();
  };

  Recovery.prototype.retry = function () {
    var self = this;
    this.check().then(function (result) {
      if (result.status === 401) { self.status('expired'); return; }
      if (result.status !== 200) { self.status('failed'); return; }
      self.protectedState = null;
      self.save();
    }, function () { self.status('failed'); });
  };

  Recovery.prototype.discard = function () {
    if (!window.confirm(text('editor_discard_confirm'))) { return; }
    var self = this;
    this.request('POST', { action: 'clear', sequence: String(this.sequence) }).then(function () {
      self.protectedState = null;
      submitting = true;  // Reload the saved version without a leave warning.
      window.location.href = window.location.href.split('#')[0];
    }, function () { self.status('failed'); });
  };

  Recovery.prototype.banner = function (values) {
    var self = this;
    var box = document.createElement('div');
    box.className = 'notice warning recovery-banner';
    box.setAttribute('role', 'status');
    var intro = document.createElement('p');
    intro.textContent = text('editor_revision_conflict');
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

  Recovery.prototype.start = function () {
    var self = this;
    var unsavedPage = this.form.hasAttribute('data-unsaved');
    this.check().then(function (result) {
      self.ready = true;
      if (result.status === 401) { self.status('expired'); return; }
      if (result.status !== 200) { self.status('failed'); return; }
      var record = result.payload.recovery;
      var current = self.fields();
      if (unsavedPage) {
        // This page shows text the server just returned (preview or validation
        // error): it is newer than any earlier copy, so protect it right away.
        self.save();
        return;
      }
      if (!record || !record.fields) { self.protectedState = serialize(self.form); self.status('saved'); return; }
      var saved = record.fields;
      var differs = Object.keys(self.textFields(saved)).some(function (name) { return saved[name] !== current[name]; });
      if (!differs) {
        self.protectedState = serialize(self.form);
        self.status('saved');
        return;
      }
      if (saved.revision === current.revision) {
        // Same settings version: put the recovered text back into the form.
        self.apply(saved, false);
        self.protectedState = serialize(self.form);
        self.status('recovered', { discard: function () { self.discard(); } });
      } else {
        // Settings changed since: never overwrite silently; let the researcher choose.
        self.protectedState = serialize(self.form);
        self.status('saved');
        self.banner(saved);
      }
    }, function () {
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

  /* ---------- wiring ---------- */

  var guards = forms.map(function (form) {
    var guard = { form: form, initial: serialize(form), recovery: null };
    if (recoveryUrl && form.hasAttribute('data-recovery-key') && window.fetch && window.URLSearchParams) {
      guard.recovery = new Recovery(form);
    }
    guard.dirty = function () { return serialize(form) !== guard.initial || form.hasAttribute('data-unsaved'); };
    guard.safe = function () { return !guard.dirty() || (guard.recovery && guard.recovery.isProtected()); };

    function changed() { if (guard.recovery) { guard.recovery.schedule(); } }
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
      if (!guard.recovery) { submitting = true; return; }
      // Check the login first so an expired session never swallows the form.
      event.preventDefault();
      var recovery = guard.recovery;
      clearTimeout(recovery.timer);
      recovery.check().then(function (result) {
        if (result.status === 401) { recovery.status('expired'); return; }
        if (result.status !== 200) { recovery.status('failed'); return; }
        var flushed = recovery.isProtected() ? Promise.resolve(true) : recovery.save();
        return flushed.then(function () {
          if (submitter && submitter.name) {
            var hidden = document.createElement('input');
            hidden.type = 'hidden';
            hidden.name = submitter.name;
            hidden.value = submitter.value;
            form.appendChild(hidden);
          }
          submitting = true;
          HTMLFormElement.prototype.submit.call(form);
        });
      }, function () { recovery.status('failed'); });
    });

    if (guard.recovery) { guard.recovery.start(); }
    return guard;
  });

  function unsafeGuards() {
    return guards.filter(function (guard) { return !guard.safe(); });
  }

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
