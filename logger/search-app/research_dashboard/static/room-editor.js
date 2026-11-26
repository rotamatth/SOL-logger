/*
 * The Rooms page's editor: a classroom to scale, its desks, islands and landmarks moved, turned and changed by
 * pointer, touch or keyboard, with undo and redo, and saved explicitly with the revision it was based on.
 *
 * Pieces move by 10 cm and line up with other pieces nearby (Alt moves freely); the round handle turns them 15°
 * at a time (Shift for any angle). Nothing reaches the server until "Save the room".
 */
(function () {
  'use strict';
  var root = document.getElementById('room-editor');
  if (!root || !window.SolRoomDrawing) { return; }

  var config = JSON.parse(root.getAttribute('data-config'));
  var strings = JSON.parse(root.getAttribute('data-strings'));
  var drawing = window.SolRoomDrawing.create(config, strings);
  var t = drawing.t, make = drawing.make;
  var $ = function (id) { return document.getElementById(id); };
  var svg = $('room-floor'), list = $('room-list'), props = $('room-props'), message = $('room-message');
  var nameInput = $('room-name'), widthInput = $('room-width'), depthInput = $('room-depth');
  var csrf = root.getAttribute('data-csrf');
  var SNAP = config.snap, ALIGN = 12, TURN = 15, UNDO_LIMIT = 100;

  var rooms = [], current = null, saved = '', selected = null;
  var undoStack = [], redoStack = [], drag = null, guides = [], layers = null, suppressClick = false;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined && text !== null) { node.textContent = text; }
    return node;
  }
  function metres(cm) { return (Math.round(cm) / 100).toLocaleString(document.documentElement.lang || 'it', { maximumFractionDigits: 2 }); }
  function say(text, problem) {
    message.textContent = text || '';
    message.classList.toggle('room-problem', Boolean(problem));
  }
  function url(name, id) { return root.getAttribute(name).replace('ROOM', encodeURIComponent(id || '')); }
  function pieceById(id) { return current ? current.pieces.filter(function (p) { return p.id === id; })[0] || null : null; }
  function newId() { return 'p' + Math.random().toString(36).slice(2, 10); }

  // -- State, undo and redo -------------------------------------------------------------------------------------------
  function snapshot() {
    return current ? JSON.stringify({ name: current.name, width: current.width, depth: current.depth, pieces: current.pieces }) : '';
  }
  function dirty() { return current !== null && snapshot() !== saved; }
  function remember() {
    undoStack.push(snapshot());
    if (undoStack.length > UNDO_LIMIT) { undoStack.shift(); }
    redoStack = [];
  }
  function restore(text) {
    var state = JSON.parse(text);
    current.name = state.name; current.width = state.width; current.depth = state.depth; current.pieces = state.pieces;
    if (selected && !pieceById(selected)) { selected = null; }
    render();
  }
  function undo() { if (undoStack.length) { redoStack.push(snapshot()); restore(undoStack.pop()); } }
  function redo() { if (redoStack.length) { undoStack.push(snapshot()); restore(redoStack.pop()); } }

  function open(room, note) {
    current = { id: room.id || null, name: room.name || '', revision: room.revision || 0,
                width: room.width, depth: room.depth, pieces: JSON.parse(JSON.stringify(room.pieces || [])) };
    saved = room.id ? snapshot() : '';
    undoStack = []; redoStack = []; selected = null;
    if (room.id) {
      try { window.history.replaceState(null, '', window.location.pathname + '?room=' + encodeURIComponent(room.id)); } catch (_) { /* fine */ }
    }
    render();
    say(note || '');
  }
  function blank(note) {
    open({ id: null, name: '', revision: 0, width: config['default'][0], depth: config['default'][1], pieces: [] }, note);
    saved = snapshot();  // An untouched new room has nothing to lose.
    render();
  }
  function leaveOk() { return !dirty() || window.confirm(t('rooms_leave_confirm')); }

  // -- Geometry -----------------------------------------------------------------------------------------------------
  function clamp(piece) {
    piece.x = Math.max(0, Math.min(current.width, Math.round(piece.x * 10) / 10));
    piece.y = Math.max(0, Math.min(current.depth, Math.round(piece.y * 10) / 10));
  }
  function normalizeTurn(value) { return Math.round((((value % 360) + 360) % 360) * 10) / 10; }

  // Snap to 10 cm, then line up with another piece's centre when it is close: that keeps rows straight.
  function place(piece, x, y, free) {
    guides = [];
    if (!free) {
      x = Math.round(x / SNAP) * SNAP;
      y = Math.round(y / SNAP) * SNAP;
      var bestX = null, bestY = null;
      current.pieces.forEach(function (other) {
        if (other.id === piece.id) { return; }
        if (Math.abs(other.x - x) <= ALIGN && (bestX === null || Math.abs(other.x - x) < Math.abs(bestX - x))) { bestX = other.x; }
        if (Math.abs(other.y - y) <= ALIGN && (bestY === null || Math.abs(other.y - y) < Math.abs(bestY - y))) { bestY = other.y; }
      });
      if (bestX !== null) { x = bestX; guides.push({ x: x }); }
      if (bestY !== null) { y = bestY; guides.push({ y: y }); }
    }
    piece.x = x; piece.y = y;
    clamp(piece);
  }

  function add(kind, desks, at) {
    remember();
    var piece = { id: newId(), kind: kind, x: 0, y: 0, rotation: 0 };
    if (kind === 'desk' || kind === 'island') { piece.tablets = 1; }
    if (kind === 'island') { piece.desks = desks; }
    var spot = at || { x: current.width / 2 + (current.pieces.length % 5) * 20, y: current.depth / 2 + (current.pieces.length % 5) * 20 };
    current.pieces.push(piece);
    place(piece, spot.x, spot.y, false);
    guides = [];
    selected = piece.id;
    render();
    focusSelected();
    return piece;
  }
  function duplicate(id) {
    var from = pieceById(id);
    if (!from) { return; }
    remember();
    var copy = JSON.parse(JSON.stringify(from));
    copy.id = newId();
    copy.x += 40; copy.y += 40;
    clamp(copy);
    current.pieces.push(copy);
    selected = copy.id;
    render();
    focusSelected();
  }
  function removePiece(id) {
    if (!pieceById(id)) { return; }
    remember();
    current.pieces = current.pieces.filter(function (p) { return p.id !== id; });
    selected = null;
    render();
    svg.focus();
  }
  function change(id, apply) {
    var piece = pieceById(id);
    if (!piece) { return; }
    remember();
    apply(piece);
    clamp(piece);
    render();
  }

  // -- Drawing --------------------------------------------------------------------------------------------------------
  function render() {
    if (!current) { return; }
    layers = drawing.draw(svg, current, { rulers: true, labels: true, spots: true });
    layers.pieces.querySelectorAll('[data-piece]').forEach(function (group) {
      group.setAttribute('tabindex', '0');
      group.setAttribute('role', 'button');
      var piece = pieceById(group.getAttribute('data-piece'));
      group.setAttribute('aria-label', kindName(piece));
      if (piece.id === selected) { group.classList.add('room-selected'); }
    });
    guides.forEach(function (guide) {
      if (guide.x !== undefined) { make('line', { 'class': 'room-guide', x1: guide.x, y1: 0, x2: guide.x, y2: current.depth }, layers.overlay); }
      if (guide.y !== undefined) { make('line', { 'class': 'room-guide', x1: 0, y1: guide.y, x2: current.width, y2: guide.y }, layers.overlay); }
    });
    var piece = pieceById(selected);
    if (piece) {
      var size = drawing.sizeOf(piece), reach = Math.max(size[1], 30) / 2 + 34;
      var handle = make('g', { 'class': 'room-handle', transform: 'translate(' + piece.x + ' ' + piece.y + ') rotate(' + piece.rotation + ')' }, layers.overlay);
      make('line', { 'class': 'room-handle-line', x1: 0, y1: -Math.max(size[1], 30) / 2, x2: 0, y2: -reach }, handle);
      make('circle', { 'class': 'room-handle-knob', 'data-handle': piece.id, cx: 0, cy: -reach - 8, r: 10 }, handle);
      if (drag && drag.kind === 'rotate') {
        make('text', { 'class': 'room-angle', x: 16, y: -reach - 4, transform: 'rotate(' + (-piece.rotation) + ' 16 ' + (-reach - 4) + ')' },
             handle, Math.round(piece.rotation > 180 ? piece.rotation - 360 : piece.rotation) + '°');
      }
    }
    if (document.activeElement !== nameInput) { nameInput.value = current.name; }
    if (document.activeElement !== widthInput) { widthInput.value = (current.width / 100).toFixed(1); }
    if (document.activeElement !== depthInput) { depthInput.value = (current.depth / 100).toFixed(1); }
    $('room-undo').disabled = !undoStack.length;
    $('room-redo').disabled = !redoStack.length;
    $('room-delete').hidden = !current.id;
    renderList();
    renderProps();
    if (dirty() && !message.classList.contains('room-problem')) { say(t('rooms_unsaved')); }
  }

  function kindName(piece) {
    if (!piece) { return ''; }
    if (piece.kind === 'island') { return t('rooms_kind_island' + piece.desks); }
    return t('rooms_kind_' + piece.kind);
  }

  function renderList() {
    list.textContent = '';
    var items = rooms.slice();
    if (current && !current.id) { items.unshift({ id: null, name: current.name || t('rooms_untitled'), unsaved: true }); }
    items.forEach(function (room) {
      var item = el('li');
      var button = el('button', 'room-list-item');
      button.type = 'button';
      var isCurrent = current && (room.id === current.id);
      if (isCurrent) { button.setAttribute('aria-current', 'true'); }
      button.appendChild(el('span', 'room-list-name', isCurrent ? (current.name || t('rooms_untitled')) : room.name));
      var detail = room.unsaved ? t('rooms_not_saved_yet')
        : t('rooms_summary', { w: metres(room.width), d: metres(room.depth), desks: room.desks });
      if (isCurrent && dirty() && !room.unsaved) { detail += ' · ' + t('rooms_unsaved'); }
      button.appendChild(el('span', 'room-list-detail', detail));
      button.addEventListener('click', function () {
        if (isCurrent || !room.id || !leaveOk()) { return; }
        load(room.id);
      });
      item.appendChild(button);
      list.appendChild(item);
    });
  }

  function segmented(label, values, chosen, onPick) {
    var wrap = el('div', 'room-prop');
    wrap.appendChild(el('span', 'room-prop-label', label));
    var group = el('div', 'room-segmented');
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', label);
    values.forEach(function (value) {
      var button = el('button', null, String(value));
      button.type = 'button';
      button.setAttribute('aria-pressed', String(value === chosen));
      button.addEventListener('click', function () { if (value !== chosen) { onPick(value); } });
      group.appendChild(button);
    });
    wrap.appendChild(group);
    return wrap;
  }

  function renderProps() {
    props.textContent = '';
    var piece = pieceById(selected);
    if (!piece) {
      props.appendChild(el('p', 'muted', t('rooms_props_none')));
      props.appendChild(el('h3', null, t('rooms_keys_heading')));
      var keys = el('ul', 'room-keys');
      [['← → ↑ ↓', 'rooms_key_move'], ['R · ⇧R', 'rooms_key_turn'], ['⌘/Ctrl D', 'rooms_key_duplicate'],
       ['⌫', 'rooms_key_remove'], ['⌘/Ctrl Z · ⇧Z', 'rooms_key_undo']].forEach(function (pair) {
        var item = el('li');
        item.appendChild(el('kbd', null, pair[0]));
        item.appendChild(document.createTextNode(' ' + t(pair[1])));
        keys.appendChild(item);
      });
      props.appendChild(keys);
      return;
    }
    var names = drawing.labels(current);
    props.appendChild(el('h3', null, kindName(piece) + (names[piece.id] ? ' · ' + names[piece.id] : '')));
    var facts = el('dl', 'room-facts');
    var size = drawing.sizeOf(piece);
    facts.appendChild(el('dt', null, t('rooms_size')));
    facts.appendChild(el('dd', null, t('rooms_cm', { w: size[0], h: size[1] })));
    facts.appendChild(el('dt', null, t('rooms_position')));
    facts.appendChild(el('dd', null, t('rooms_position_value', { x: metres(piece.x), y: metres(piece.y) })));
    props.appendChild(facts);

    var turn = el('label', 'room-prop');
    turn.appendChild(el('span', 'room-prop-label', t('rooms_rotation')));
    var turnInput = el('input');
    turnInput.type = 'number'; turnInput.min = '-180'; turnInput.max = '360'; turnInput.step = '1'; turnInput.id = 'room-rotation';
    turnInput.value = String(Math.round(piece.rotation > 180 ? piece.rotation - 360 : piece.rotation));
    turnInput.addEventListener('change', function () {
      var value = Number(turnInput.value);
      if (!isFinite(value)) { return; }
      change(piece.id, function (p) { p.rotation = normalizeTurn(value); });
    });
    turn.appendChild(turnInput);
    props.appendChild(turn);
    props.appendChild(el('p', 'small muted', t('rooms_rotation_hint')));

    if (piece.kind === 'island') {
      props.appendChild(segmented(t('rooms_desks'), [2, 4], piece.desks, function (value) {
        change(piece.id, function (p) { p.desks = value; });
      }));
    }
    if (piece.kind === 'desk' || piece.kind === 'island') {
      props.appendChild(segmented(t('rooms_tablets'), [1, 2], piece.tablets, function (value) {
        change(piece.id, function (p) { p.tablets = value; });
      }));
      props.appendChild(el('p', 'small muted', t('rooms_tablets_hint')));
    }
    var actions = el('div', 'room-prop-actions');
    var dup = el('button', 'button compact', t('rooms_duplicate'));
    dup.type = 'button'; dup.id = 'room-piece-duplicate';
    dup.addEventListener('click', function () { duplicate(piece.id); });
    var rem = el('button', 'button compact', t('rooms_remove'));
    rem.type = 'button'; rem.id = 'room-piece-remove';
    rem.addEventListener('click', function () { removePiece(piece.id); });
    actions.appendChild(dup);
    actions.appendChild(rem);
    props.appendChild(actions);
  }

  function focusSelected() {
    var group = selected && layers ? layers.pieces.querySelector('[data-piece="' + selected + '"]') : null;
    if (group) { group.focus({ preventScroll: true }); }
  }

  // -- Pointer: move, turn, and drop new pieces from the palette ------------------------------------------------------
  svg.addEventListener('pointerdown', function (event) {
    if (event.button > 0 || !current) { return; }
    var knob = event.target.closest('[data-handle]');
    var group = event.target.closest('[data-piece]');
    if (knob) {
      event.preventDefault();
      remember();
      drag = { kind: 'rotate', id: knob.getAttribute('data-handle'), moved: false };
    } else if (group) {
      event.preventDefault();
      var piece = pieceById(group.getAttribute('data-piece'));
      selected = piece.id;
      var at = drawing.toRoom(svg, event.clientX, event.clientY);
      drag = { kind: 'move', id: piece.id, start: at, from: { x: piece.x, y: piece.y }, before: snapshot(), moved: false };
      render();
    } else {
      selected = null;
      render();
      return;
    }
    svg.setPointerCapture(event.pointerId);
  });

  svg.addEventListener('pointermove', function (event) {
    if (!drag) { return; }
    var piece = pieceById(drag.id);
    if (!piece) { return; }
    var at = drawing.toRoom(svg, event.clientX, event.clientY);
    if (drag.kind === 'move') {
      var dx = at.x - drag.start.x, dy = at.y - drag.start.y;
      if (!drag.moved && Math.abs(dx) + Math.abs(dy) < 3) { return; }
      drag.moved = true;
      place(piece, drag.from.x + dx, drag.from.y + dy, event.altKey);
    } else {
      var angle = Math.atan2(at.y - piece.y, at.x - piece.x) * 180 / Math.PI + 90;
      piece.rotation = normalizeTurn(event.shiftKey ? Math.round(angle) : Math.round(angle / TURN) * TURN);
      drag.moved = true;
    }
    render();
  });

  function endDrag() {
    if (!drag) { return; }
    if (drag.kind === 'move' && drag.moved) { undoStack.push(drag.before); redoStack = []; }
    if (drag.kind === 'rotate' && !drag.moved) { undoStack.pop(); }
    drag = null;
    guides = [];
    render();
    focusSelected();
  }
  svg.addEventListener('pointerup', endDrag);
  svg.addEventListener('pointercancel', endDrag);

  // From the palette: a click adds the piece in the middle; a drag drops it where the pointer is let go.
  document.querySelectorAll('#room-palette [data-kind]').forEach(function (button) {
    var kind = button.getAttribute('data-kind'), desks = Number(button.getAttribute('data-desks')) || 0;
    button.addEventListener('click', function () {
      if (suppressClick) { suppressClick = false; return; }
      add(kind, desks, null);
    });
    button.addEventListener('pointerdown', function (event) {
      if (event.button > 0 || event.pointerType === 'touch') { return; }
      var startX = event.clientX, startY = event.clientY, ghost = null;
      function move(e) {
        if (!ghost && Math.abs(e.clientX - startX) + Math.abs(e.clientY - startY) < 6) { return; }
        if (!ghost) {
          ghost = el('div', 'room-ghost', button.textContent.trim());
          document.body.appendChild(ghost);
        }
        ghost.style.left = e.clientX + 'px';
        ghost.style.top = e.clientY + 'px';
      }
      function up(e) {
        document.removeEventListener('pointermove', move);
        document.removeEventListener('pointerup', up);
        if (!ghost) { return; }
        ghost.remove();
        suppressClick = true;
        window.setTimeout(function () { suppressClick = false; }, 0);
        var box = svg.getBoundingClientRect();
        if (e.clientX >= box.left && e.clientX <= box.right && e.clientY >= box.top && e.clientY <= box.bottom) {
          var at = drawing.toRoom(svg, e.clientX, e.clientY);
          add(kind, desks, at);
        }
      }
      document.addEventListener('pointermove', move);
      document.addEventListener('pointerup', up);
    });
  });

  // -- Keyboard ---------------------------------------------------------------------------------------------------------
  document.addEventListener('keydown', function (event) {
    if (!current) { return; }
    var target = event.target, typing = target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName);
    var mod = event.metaKey || event.ctrlKey, key = event.key.toLowerCase();
    if (mod && key === 'z' && !typing) { event.preventDefault(); if (event.shiftKey) { redo(); } else { undo(); } return; }
    if (mod && key === 'y' && !typing) { event.preventDefault(); redo(); return; }
    if (typing || !root.contains(target) && target !== document.body) { return; }
    var piece = pieceById(selected);
    if (!piece) { return; }
    var step = event.shiftKey ? config.grid : SNAP;
    var moves = { arrowleft: [-step, 0], arrowright: [step, 0], arrowup: [0, -step], arrowdown: [0, step] };
    if (moves[key]) {
      event.preventDefault();
      change(piece.id, function (p) { p.x += moves[key][0]; p.y += moves[key][1]; });
      focusSelected();
    } else if (key === 'r' && !mod) {
      event.preventDefault();
      change(piece.id, function (p) { p.rotation = normalizeTurn(p.rotation + (event.shiftKey ? -TURN : TURN)); });
      focusSelected();
    } else if (mod && key === 'd') {
      event.preventDefault();
      duplicate(piece.id);
    } else if (key === 'delete' || key === 'backspace') {
      event.preventDefault();
      removePiece(piece.id);
    } else if (key === 'escape') {
      selected = null;
      render();
      svg.focus();
    }
  });
  svg.addEventListener('focusin', function (event) {
    var group = event.target.closest && event.target.closest('[data-piece]');
    if (group && group.getAttribute('data-piece') !== selected && !drag) {
      selected = group.getAttribute('data-piece');
      render();
      focusSelected();
    }
  });

  // -- The room's name and size -----------------------------------------------------------------------------------------
  nameInput.addEventListener('change', function () {
    if (nameInput.value === current.name) { return; }
    remember();
    current.name = nameInput.value;
    render();
  });
  function sizeChanged(input, field) {
    var value = Math.round(Number(String(input.value).replace(',', '.')) * 100);
    if (!isFinite(value) || value <= 0) { render(); return; }
    value = Math.max(config.room[0], Math.min(config.room[1], value));
    if (value === current[field]) { render(); return; }
    remember();
    current[field] = value;
    current.pieces.forEach(clamp);
    render();
  }
  widthInput.addEventListener('change', function () { sizeChanged(widthInput, 'width'); });
  depthInput.addEventListener('change', function () { sizeChanged(depthInput, 'depth'); });
  $('room-undo').addEventListener('click', undo);
  $('room-redo').addEventListener('click', redo);

  // -- Server ---------------------------------------------------------------------------------------------------------
  function post(address, fields) {
    var body = new URLSearchParams();
    body.set('csrf', csrf);
    Object.keys(fields).forEach(function (name) { body.set(name, fields[name]); });
    return fetch(address, { method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json' }, body: body })
      .then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (data) { return { status: response.status, data: data }; });
      });
  }
  function received(data) {
    if (data.csrf) { csrf = data.csrf; }
    if (data.rooms) { rooms = data.rooms; }
  }

  function load(id) {
    fetch(url('data-room-url', id), { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (data) {
        if (!data || !data.room) { say(t('rooms_save_failed'), true); return; }
        received(data);
        open(data.room);
      }).catch(function () { say(t('rooms_save_failed'), true); });
  }

  $('room-save').addEventListener('click', function () {
    if (!current) { return; }
    current.name = nameInput.value;
    if (!current.name.trim()) { say(t('rooms_name_needed'), true); nameInput.focus(); return; }
    var fields = { name: current.name.trim(), room: JSON.stringify({ width: current.width, depth: current.depth, pieces: current.pieces }) };
    var address = current.id ? url('data-save-url', current.id) : root.getAttribute('data-new-url');
    if (current.id) { fields.revision = current.revision; }
    post(address, fields).then(function (reply) {
      received(reply.data);
      if (reply.status === 200 && reply.data.room) {
        var keep = selected;
        open(reply.data.room, t('rooms_saved'));
        if (pieceById(keep)) { selected = keep; render(); }
        return;
      }
      if (reply.status === 409 && reply.data.room) { open(reply.data.room); say(t('rooms_conflict'), true); return; }
      say(t('rooms_save_failed'), true);
    }).catch(function () { say(t('rooms_save_failed'), true); });
  });

  $('room-new').addEventListener('click', function () {
    if (!leaveOk()) { return; }
    blank();
    nameInput.focus();
  });
  $('room-duplicate').addEventListener('click', function () {
    if (!current) { return; }
    var copy = { id: null, name: t('rooms_copy_name', { name: current.name || t('rooms_untitled') }), revision: 0,
                 width: current.width, depth: current.depth, pieces: current.pieces.map(function (p) { return JSON.parse(JSON.stringify(p)); }) };
    open(copy);
    say(t('rooms_unsaved'));
  });
  $('room-delete').addEventListener('click', function () {
    if (!current || !current.id || !window.confirm(t('rooms_delete_confirm', { name: current.name }))) { return; }
    post(url('data-delete-url', current.id), { revision: current.revision }).then(function (reply) {
      received(reply.data);
      if (reply.status !== 200) { say(reply.status === 409 ? t('rooms_conflict') : t('rooms_save_failed'), true); return; }
      try { window.history.replaceState(null, '', window.location.pathname); } catch (_) { /* fine */ }
      if (rooms.length) { load(rooms[0].id); } else { blank(t('rooms_none')); }
      say(t('rooms_deleted'));
    }).catch(function () { say(t('rooms_save_failed'), true); });
  });

  window.addEventListener('beforeunload', function (event) {
    if (dirty()) { event.preventDefault(); event.returnValue = ''; }
  });

  fetch(root.getAttribute('data-list-url'), { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    .then(function (response) { return response.json(); })
    .then(function (data) {
      received(data);
      var wanted = new URLSearchParams(window.location.search).get('room');
      var first = rooms.filter(function (room) { return room.id === wanted; })[0] || rooms[0];
      if (first) { load(first.id); } else { blank(t('rooms_none')); }
    }).catch(function () { blank(); say(t('rooms_save_failed'), true); });
}());
