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
  var sessionUrl = body.getAttribute('data-editor-session-url') || '';
  var loginUrl = body.getAttribute('data-editor-login-url') || '';
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
    if (this.discarding) { return Promise.resolve(false); }
    if (this.inflight) { return this.inflight; }
    if (this.isProtected()) {
      if (this.state === 'expired' || this.state === 'failed') { this.status('protected'); }
      return Promise.resolve(true);
    }
    var snapshot = serialize(this.form);
    var sent = this.fields();
    this.status('protecting');
    var pending = this.request('POST', {
      action: 'save', sequence: String(this.sequence), fields: JSON.stringify(sent)
    }).then(function (result) {
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
      self.status('failed');
      return false;
    });
    var operation = pending.then(function (stored) {
      if (self.inflight === operation) { self.inflight = null; }
      return stored;
    }, function () {
      if (self.inflight === operation) { self.inflight = null; }
      self.status('failed');
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
    return this.request('GET').then(function (result) {
      var record = result.status === 200 ? result.payload.recovery : null;
      if (record && sameFields(record.fields, sent)) { return self.stored(record.sequence, snapshot); }
      self.status('conflict');
      return false;
    }, function () {
      self.status('conflict');
      return false;
    });
  };

  Recovery.prototype.schedule = function () {
    var self = this;
    clearTimeout(this.timer);
    if (this.discarding) { return; }
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
    if (this.discarding) { return Promise.resolve(false); }
    if (this.isProtected()) { return Promise.resolve(true); }
    if (!this.ready) { return this.started.then(function () { return self.flush(attempt); }); }
    if (this.state === 'conflict' || attempt >= FLUSH_ATTEMPTS) { return Promise.resolve(false); }
    return this.save().then(function (stored) {
      return stored && self.flush(attempt + 1);
    });
  };

  Recovery.prototype.retry = function () {
    var self = this;
    authCheck().then(function (status) {
      if (status === 401) { self.status('expired'); return; }
      if (status !== 200) { self.status('failed'); return; }
      self.save();
    }, function () { self.status('failed'); });
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
    this.started = this.request('GET').then(function (result) {
      self.ready = true;
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
