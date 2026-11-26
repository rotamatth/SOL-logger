/*
 * The live view's classroom map: tables, one circle per tablet (its sticker's ID), and each tablet's health.
 *
 * The layout comes from map.json and changes only through explicit saves (with their revision); the health comes
 * from health.json every two seconds and only repaints the circles, so polling never disturbs a drag or an unsaved
 * arrangement. When the health feed fails, the whole map says it is not current instead of blaming the tablets.
 * Sound is off until the researcher turns it on, and then beeps once per new problem, never per poll.
 */
(function () {
  'use strict';
  var root = document.getElementById('live-map');
  if (!root) { return; }

  var W = 1000, H = 700;                     // research_dashboard/room_maps.py CANVAS
  var HEALTH_MS = 2000, HEALTH_TIMEOUT_MS = 2000, MAP_REFRESH_MS = 15000, BEEP_GAP_MS = 4000;
  var ACTIONABLE = ['no_contact', 'search_failed', 'save_failed', 'save_unconfirmed', 'page_hidden', 'fullscreen_off',
                    'search_waiting', 'two_tablets'];
  var strings = JSON.parse(root.getAttribute('data-strings') || '{}');
  var $ = function (id) { return document.getElementById(id); };
  var canvas = $('live-map-canvas'), tray = $('live-map-tray'), roomsSelect = $('live-map-rooms');
  var message = $('live-map-message'), monitorLine = $('live-map-monitor'), problems = $('live-map-problems');
  var details = $('live-map-details'), detailsBody = $('live-map-details-body'), detailsId = $('live-map-details-id');
  var editBar = $('live-map-editbar'), tableTools = $('live-map-table-tools'), empty = $('live-map-empty');
  var listView = $('live-list-view');

  var map = null, rooms = [], csrf = '', dirty = false, editing = false;
  var selectedTable = null, selectedId = null;
  var health = null, healthGoodAt = null, stale = true, signedOut = false;
  var sound = false, audio = null, seen = null, lastBeep = 0;
  var healthTimer = null, healthInFlight = false, drag = null;

  function t(key, values) {
    var text = strings[key] || key;
    Object.keys(values || {}).forEach(function (name) { text = text.split('{' + name + '}').join(values[name]); });
    return text;
  }
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined && text !== null) { node.textContent = text; }
    return node;
  }
  function duration(seconds) {
    seconds = Math.max(0, Math.round(seconds));
    return seconds < 120 ? t('seconds', { n: seconds }) : t('minutes', { n: Math.round(seconds / 60) });
  }
  function clock(epoch) {
    try {
      return new Date(epoch * 1000).toLocaleTimeString('it-CH', { timeZone: 'Europe/Zurich', hour12: false });
    } catch (_) { return new Date(epoch * 1000).toLocaleTimeString(); }
  }
  function say(text, problem) {
    message.textContent = text || '';
    message.classList.toggle('live-map-problem', Boolean(problem));
  }
  function numeric(a, b) { return a.localeCompare(b, undefined, { numeric: true }); }

  // -- Which IDs exist: the class's roster, IDs placed earlier, and any tablet registered in this session --------
  function ids() {
    var found = {};
    document.querySelectorAll('#live-children [data-child]').forEach(function (row) { found[row.getAttribute('data-child')] = true; });
    if (health) {
      health.roster.forEach(function (id) { found[id] = true; });
      Object.keys(health.tablets).forEach(function (id) { found[id] = true; });
    }
    if (map) { Object.keys(map.placements).forEach(function (id) { found[id] = true; }); }
    return Object.keys(found).sort(numeric);
  }
  function tableById(id) { return map.tables.filter(function (table) { return table.id === id; })[0] || null; }

  // -- Drawing the layout -------------------------------------------------------------------------------------------
  function percent(value, total) { return (value / total * 100) + '%'; }

  function tabletButton(id) {
    var button = el('button', 'map-tablet');
    button.type = 'button';
    button.dataset.id = id;
    var circle = el('span', 'map-tablet-circle', id);
    circle.appendChild(el('span', 'map-tablet-icon'));
    button.appendChild(circle);
    button.appendChild(el('span', 'map-tablet-reason'));
    button.addEventListener('click', function () { if (!drag || !drag.moved) { select(id); } });
    button.addEventListener('pointerdown', function (event) { startTabletDrag(event, id, button); });
    return button;
  }

  function render() {
    canvas.textContent = '';
    if (map.image) {
      var plan = el('img', 'live-map-plan');
      plan.alt = '';
      plan.src = root.getAttribute('data-image-url').replace('NAME', encodeURIComponent(map.image));
      canvas.appendChild(plan);
    }
    map.tables.forEach(function (table, index) {
      var node = el('div', 'map-table');
      node.appendChild(el('span', 'map-table-label', t('table') + ' ' + (index + 1)));
      node.dataset.table = table.id;
      node.setAttribute('aria-label', t('table') + ' ' + (index + 1));
      if (editing) {
        node.tabIndex = 0;
        var handle = el('span', 'map-table-resize');
        handle.addEventListener('pointerdown', function (event) { startTableDrag(event, table.id, 'resize'); });
        node.appendChild(handle);
      }
      node.addEventListener('pointerdown', function (event) { if (event.target === node) { startTableDrag(event, table.id, 'move'); } });
      node.addEventListener('keydown', function (event) { tableKey(event, table.id); });
      node.addEventListener('focus', function () { if (editing) { selectTable(table.id); } });
      canvas.appendChild(node);
    });
    tray.textContent = '';
    ids().forEach(function (id) {
      var button = tabletButton(id);
      (map.placements[id] ? canvas : tray).appendChild(button);
    });
    empty.hidden = map.tables.length > 0;
    empty.textContent = t('empty');
    position();
    renderRooms();
    renderTableTools();
    applyHealth();
  }

  function position() {
    canvas.querySelectorAll('[data-table]').forEach(function (node) {
      var table = tableById(node.dataset.table);
      node.style.left = percent(table.x, W);
      node.style.top = percent(table.y, H);
      node.style.width = percent(table.w, W);
      node.style.height = percent(table.h, H);
      node.style.transform = 'rotate(' + table.rotation + 'deg)';
      node.classList.toggle('selected', editing && selectedTable === table.id);
    });
    var perTable = {};
    canvas.querySelectorAll('.map-tablet').forEach(function (button) {
      var place = map.placements[button.dataset.id];
      if (place && place.table) { (perTable[place.table] = perTable[place.table] || []).push(button); }
      else if (place) { button.style.left = percent(place.x, W); button.style.top = percent(place.y, H); }
    });
    canvas.querySelectorAll('[data-table]').forEach(function (node) { node.classList.toggle('occupied', Boolean(perTable[node.dataset.table])); });
    Object.keys(perTable).forEach(function (tableId) {
      var table = tableById(tableId);
      var group = perTable[tableId];
      group.forEach(function (button, index) {
        var x = table.x + table.w / 2 + (index - (group.length - 1) / 2) * 70;
        button.style.left = percent(Math.max(30, Math.min(W - 30, x)), W);
        button.style.top = percent(table.y + table.h / 2, H);
      });
    });
  }

  function renderRooms() {
    var chosen = roomsSelect.value || map.room_id || '';
    roomsSelect.textContent = '';
    if (!rooms.length) {
      var none = el('option', null, t('no_rooms'));
      none.value = '';
      roomsSelect.appendChild(none);
    }
    rooms.forEach(function (room) {
      var option = el('option', null, room.name);
      option.value = room.id;
      roomsSelect.appendChild(option);
    });
    if (rooms.some(function (room) { return room.id === chosen; })) { roomsSelect.value = chosen; }
    $('live-map-use-room').disabled = !rooms.length;
    var source = rooms.filter(function (room) { return room.id === map.room_id; })[0];
    $('live-map-update-room').hidden = !source;
  }

  // -- Editing ------------------------------------------------------------------------------------------------------
  function changed() {
    dirty = true;
    say(t('unsaved'));
  }

  function setEditing(on) {
    editing = on;
    root.classList.toggle('editing', on);
    editBar.hidden = !on;
    $('live-map-edit').setAttribute('aria-pressed', String(on));
    $('live-map-edit').textContent = on ? t('done') : $('live-map-edit').getAttribute('data-label');
    if (!on) { selectedTable = null; }
    render();
    if (selectedId) { renderDetails(); }
  }

  function selectTable(id) {
    selectedTable = id;
    position();
    renderTableTools();
  }

  function renderTableTools() {
    tableTools.textContent = '';
    tableTools.hidden = !(editing && selectedTable && tableById(selectedTable));
    if (tableTools.hidden) { return; }
    [['rotate', function (table) { table.rotation = (table.rotation + 15) % 360; }],
     ['bigger', function (table) { resize(table, 1.15); }],
     ['smaller', function (table) { resize(table, 1 / 1.15); }],
     ['duplicate', function (table) { addTable(table); }],
     ['remove_table', function (table) { removeTable(table.id); }]].forEach(function (tool) {
      var button = el('button', 'button compact', t(tool[0]));
      button.type = 'button';
      button.addEventListener('click', function () {
        var table = tableById(selectedTable);
        if (!table) { return; }
        tool[1](table);
        changed();
        render();
      });
      tableTools.appendChild(button);
    });
  }

  function clampTable(table) {
    table.w = Math.max(20, Math.min(600, Math.round(table.w)));
    table.h = Math.max(20, Math.min(500, Math.round(table.h)));
    table.x = Math.max(0, Math.min(W - table.w, Math.round(table.x)));
    table.y = Math.max(0, Math.min(H - table.h, Math.round(table.y)));
  }
  function resize(table, factor) {
    var cx = table.x + table.w / 2, cy = table.y + table.h / 2;
    table.w *= factor; table.h *= factor;
    table.x = cx - table.w / 2; table.y = cy - table.h / 2;
    clampTable(table);
  }
  function newId() { return 't' + Math.random().toString(36).slice(2, 10); }
  function addTable(from) {
    var table = from ? { id: newId(), x: from.x + 30, y: from.y + 30, w: from.w, h: from.h, rotation: from.rotation }
                     : { id: newId(), x: 440 + (map.tables.length % 6) * 12, y: 300 + (map.tables.length % 6) * 12, w: 120, h: 80, rotation: 0 };
    clampTable(table);
    map.tables.push(table);
    selectedTable = table.id;
  }
  function removeTable(id) {
    map.tables = map.tables.filter(function (table) { return table.id !== id; });
    Object.keys(map.placements).forEach(function (pid) { if (map.placements[pid].table === id) { delete map.placements[pid]; } });
    selectedTable = null;
  }

  function point(event) {
    var box = canvas.getBoundingClientRect();
    return { x: (event.clientX - box.left) / box.width * W, y: (event.clientY - box.top) / box.height * H, inside:
      event.clientX >= box.left && event.clientX <= box.right && event.clientY >= box.top && event.clientY <= box.bottom };
  }

  function startTableDrag(event, id, mode) {
    if (!editing || event.button > 0) { return; }
    event.preventDefault();
    event.stopPropagation();
    selectTable(id);
    var table = tableById(id), start = point(event);
    drag = { kind: 'table', mode: mode, id: id, from: { x: table.x, y: table.y, w: table.w, h: table.h }, start: start, moved: false };
    canvas.setPointerCapture(event.pointerId);
  }

  function startTabletDrag(event, id, button) {
    if (!editing || event.button > 0) { return; }
    event.preventDefault();
    drag = { kind: 'tablet', id: id, button: button, moved: false, startX: event.clientX, startY: event.clientY };
    button.setPointerCapture(event.pointerId);
    button.addEventListener('pointermove', moveTablet);
    button.addEventListener('pointerup', dropTablet, { once: true });
    button.addEventListener('pointercancel', cancelTablet, { once: true });
  }

  canvas.addEventListener('pointermove', function (event) {
    if (!drag || drag.kind !== 'table') { return; }
    var now = point(event), table = tableById(drag.id);
    var dx = now.x - drag.start.x, dy = now.y - drag.start.y;
    if (Math.abs(dx) + Math.abs(dy) > 2) { drag.moved = true; }
    if (drag.mode === 'move') { table.x = drag.from.x + dx; table.y = drag.from.y + dy; }
    else { table.w = drag.from.w + dx; table.h = drag.from.h + dy; }
    clampTable(table);
    position();
  });
  canvas.addEventListener('pointerup', function () {
    if (drag && drag.kind === 'table') {
      if (drag.moved) { changed(); }
      drag = null;
    }
  });

  function dropTargets(event) {
    var found = { table: null, tray: false };
    document.elementsFromPoint(event.clientX, event.clientY).forEach(function (node) {
      if (!found.table && node.dataset && node.dataset.table) { found.table = node.dataset.table; }
      if (node === tray || tray.contains(node)) { found.tray = true; }
    });
    return found;
  }
  function moveTablet(event) {
    if (!drag || drag.kind !== 'tablet') { return; }
    var dx = event.clientX - drag.startX, dy = event.clientY - drag.startY;
    if (Math.abs(dx) + Math.abs(dy) > 4) { drag.moved = true; }
    drag.button.classList.add('dragging');
    drag.button.style.translate = dx + 'px ' + dy + 'px';
    var targets = dropTargets(event);
    canvas.querySelectorAll('[data-table]').forEach(function (node) { node.classList.toggle('drop-target', node.dataset.table === targets.table); });
    tray.classList.toggle('drop-target', targets.tray);
  }
  function dropTablet(event) {
    var current = drag;
    drag.button.removeEventListener('pointermove', moveTablet);
    if (current.moved) {
      var targets = dropTargets(event), spot = point(event);
      if (targets.table) { map.placements[current.id] = { table: targets.table }; }
      else if (targets.tray) { delete map.placements[current.id]; }
      else if (spot.inside) { map.placements[current.id] = { x: Math.round(Math.max(30, Math.min(W - 30, spot.x))), y: Math.round(Math.max(30, Math.min(H - 30, spot.y))) }; }
      changed();
      render();
    } else {
      current.button.style.translate = '';
      current.button.classList.remove('dragging');
    }
    window.setTimeout(function () { drag = null; }, 0);
  }
  function cancelTablet() {
    if (drag && drag.button) { drag.button.style.translate = ''; drag.button.classList.remove('dragging'); }
    drag = null;
    render();
  }

  function tableKey(event, id) {
    if (!editing) { return; }
    var step = event.shiftKey ? 50 : 10, table = tableById(id);
    var moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (!moves[event.key]) { return; }
    event.preventDefault();
    table.x += moves[event.key][0];
    table.y += moves[event.key][1];
    clampTable(table);
    changed();
    position();
  }

  // -- Saving and rooms ---------------------------------------------------------------------------------------------
  function post(url, fields) {
    var body = new URLSearchParams();
    body.set('csrf', csrf);
    Object.keys(fields).forEach(function (name) { body.set(name, fields[name]); });
    return fetch(url, { method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json' }, body: body })
      .then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (data) { return { status: response.status, data: data }; });
      });
  }

  function received(reply) {
    if (reply.data.csrf) { csrf = reply.data.csrf; }
    if (reply.data.rooms) { rooms = reply.data.rooms; }
    if (reply.data.map) { map = reply.data.map; }
  }

  function saveMap() {
    return post(root.getAttribute('data-save-url'), {
      revision: map.revision,
      map: JSON.stringify({ tables: map.tables, image: map.image, placements: map.placements, room_id: map.room_id })
    }).then(function (reply) {
      if (reply.status === 200) { received(reply); dirty = false; say(t('saved')); render(); return true; }
      if (reply.status === 409) { received(reply); dirty = false; say(t('conflict'), true); render(); return false; }
      say(t('save_failed'), true);
      return false;
    }).catch(function () { say(t('save_failed'), true); return false; });
  }

  function savedFirst() { return dirty ? saveMap() : Promise.resolve(true); }

  $('live-map-save').addEventListener('click', function () { void saveMap(); });
  $('live-map-edit').setAttribute('data-label', $('live-map-edit').textContent);
  $('live-map-edit').addEventListener('click', function () { setEditing(!editing); });
  $('live-map-add-table').addEventListener('click', function () { addTable(null); changed(); render(); });
  $('live-map-remove-plan').addEventListener('click', function () { map.image = null; changed(); render(); });
  $('live-map-plan').addEventListener('change', function (event) {
    var file = event.target.files && event.target.files[0];
    if (!file) { return; }
    var form = new FormData();
    form.append('csrf', csrf);
    form.append('image', file);
    fetch(root.getAttribute('data-image-upload-url'), { method: 'POST', credentials: 'same-origin', body: form, headers: { Accept: 'application/json' } })
      .then(function (response) { return response.json().then(function (data) { return { ok: response.ok, data: data }; }); })
      .then(function (reply) {
        if (!reply.ok) { say(t('plan_invalid'), true); return; }
        map.image = reply.data.image;
        changed();
        render();
      }).catch(function () { say(t('plan_invalid'), true); })
      .then(function () { event.target.value = ''; });
  });

  $('live-map-use-room').addEventListener('click', function () {
    var room = rooms.filter(function (item) { return item.id === roomsSelect.value; })[0];
    if (!room) { return; }
    if ((map.tables.length || Object.keys(map.placements).length) && !window.confirm(t('use_room_confirm', { name: room.name }))) { return; }
    post(root.getAttribute('data-room-url'), { revision: map.revision, room_id: room.id }).then(function (reply) {
      received(reply);
      dirty = false;
      say(reply.status === 200 ? t('saved') : reply.status === 409 ? t('conflict') : t('save_failed'), reply.status !== 200);
      render();
    }).catch(function () { say(t('save_failed'), true); });
  });

  $('live-map-save-room').addEventListener('click', function () {
    var name = window.prompt(t('room_name'));
    if (!name || !name.trim()) { return; }
    savedFirst().then(function (ok) {
      if (!ok) { return null; }
      return post(root.getAttribute('data-rooms-url'), { name: name.trim(), session_id: root.getAttribute('data-session-id') });
    }).then(function (reply) {
      if (!reply) { return; }
      if (reply.status !== 200) { say(t('save_failed'), true); return; }
      rooms = reply.data.rooms;
      say(t('room_saved'));
      renderRooms();
      roomsSelect.value = reply.data.room.id;
    }).catch(function () { say(t('save_failed'), true); });
  });

  $('live-map-update-room').addEventListener('click', function () {
    var room = rooms.filter(function (item) { return item.id === map.room_id; })[0];
    if (!room || !window.confirm(t('update_room_confirm', { name: room.name }))) { return; }
    savedFirst().then(function (ok) {
      if (!ok) { return null; }
      return post(root.getAttribute('data-room-update-url').replace('ROOM', encodeURIComponent(room.id)),
                  { revision: room.revision, session_id: root.getAttribute('data-session-id') });
    }).then(function (reply) {
      if (!reply) { return; }
      if (reply.status !== 200) { say(reply.status === 409 ? t('conflict') : t('save_failed'), true); return; }
      rooms = reply.data.rooms;
      say(t('room_saved'));
      renderRooms();
    }).catch(function () { say(t('save_failed'), true); });
  });

  window.addEventListener('beforeunload', function (event) {
    if (dirty) { event.preventDefault(); event.returnValue = ''; }
  });

  // -- Health ---------------------------------------------------------------------------------------------------------
  function tabletOf(id) { return health && health.tablets[id] ? health.tablets[id] : null; }
  function statusOf(id) { var tablet = tabletOf(id); return tablet ? tablet.status : 'grey'; }
  function shortText(id) {
    var tablet = tabletOf(id);
    if (!tablet || !tablet.connected) { return t('not_connected'); }
    return tablet.reasons.length ? t('r_' + tablet.reasons[0].code) : t('ok');
  }

  function applyHealth() {
    var notCurrent = stale || signedOut;
    root.classList.toggle('monitor-stale', notCurrent);
    if (signedOut) { monitorLine.textContent = t('signed_out'); }
    else if (!health) { monitorLine.textContent = t('checking'); }
    else if (!health.available) { monitorLine.textContent = t('unavailable'); }
    else if (stale) { monitorLine.textContent = t('stale', { clock: healthGoodAt ? clock(healthGoodAt) : '—' }); }
    else { monitorLine.textContent = t('live', { clock: health.clock }); }
    monitorLine.classList.toggle('live-map-problem', notCurrent && Boolean(health || signedOut));
    document.querySelectorAll('#live-map [data-id]').forEach(function (button) {
      var id = button.dataset.id, status = statusOf(id), tablet = tabletOf(id);
      button.classList.remove('map-grey', 'map-green', 'map-amber', 'map-red');
      button.classList.add('map-' + status);
      button.classList.toggle('selected', selectedId === id);
      button.querySelector('.map-tablet-icon').textContent = { red: '!', amber: '!', green: '✓', grey: '?' }[status];
      var reason = button.querySelector('.map-tablet-reason');
      reason.textContent = status === 'green' ? '' : shortText(id);
      // In the tray a grey circle needs no words: "not connected yet" is the tray's ordinary state.
      reason.hidden = status === 'green' || (status === 'grey' && tray.contains(button));
      button.setAttribute('aria-label', 'ID ' + id + ': ' + shortText(id) + (tablet && tablet.reasons.length > 1 ? ' (+' + (tablet.reasons.length - 1) + ')' : ''));
    });
    document.querySelectorAll('[data-monitor-for]').forEach(function (chip) {
      var id = chip.getAttribute('data-monitor-for'), status = statusOf(id);
      chip.hidden = !health;
      chip.className = 'badge live-monitor map-' + status;
      chip.textContent = shortText(id);
    });
    renderProblems();
    if (selectedId) { renderDetails(); }
  }

  function renderProblems() {
    problems.textContent = '';
    if (!health) { return; }
    var list = ids().filter(function (id) { var status = statusOf(id); return status === 'red' || status === 'amber'; });
    list.sort(function (a, b) { return (statusOf(a) === 'red' ? 0 : 1) - (statusOf(b) === 'red' ? 0 : 1) || numeric(a, b); });
    problems.appendChild(el('span', null, list.length === 0 ? t('problems_none') : list.length === 1 ? t('problem_one') : t('problems', { n: list.length })));
    list.forEach(function (id) {
      var button = el('button', 'map-' + statusOf(id), id + ' · ' + shortText(id));
      button.type = 'button';
      button.addEventListener('click', function () { select(id, true); });
      problems.appendChild(button);
    });
  }

  function select(id, reveal) {
    selectedId = id;
    setView('map');
    applyHealth();
    renderDetails();
    var button = Array.prototype.filter.call(document.querySelectorAll('#live-map [data-id]'), function (node) { return node.dataset.id === id; })[0];
    if (button && reveal) { button.scrollIntoView({ block: 'nearest', inline: 'nearest' }); button.focus(); }
  }

  function row(id) {
    return Array.prototype.filter.call(document.querySelectorAll('#live-children [data-child]'), function (node) {
      return node.getAttribute('data-child') === id;
    })[0] || null;
  }

  function addFact(list, label, value) {
    list.appendChild(el('dt', null, label));
    list.appendChild(el('dd', null, value));
  }

  function renderDetails() {
    var id = selectedId, tablet = tabletOf(id);
    details.hidden = false;
    detailsId.textContent = 'ID ' + id;
    detailsBody.textContent = '';
    var now = health ? health.now : Date.now() / 1000;
    detailsBody.appendChild(el('h4', null, t('d_problems')));
    var current = el('ul');
    if (!tablet || !tablet.connected) { current.appendChild(el('li', null, t('not_connected'))); }
    else if (!tablet.reasons.length) { current.appendChild(el('li', null, t('ok'))); }
    (tablet ? tablet.reasons : []).forEach(function (reason) {
      var since = reason.since ? duration(now - reason.since) : '—';
      var item = el('li', 'map-reason-' + reason.severity, t('r_' + reason.code) + ': ');
      item.appendChild(el('span', null, t('x_' + reason.code, { s: since, reason: t('reason_' + (reason.reason || 'unconfirmed')) })));
      current.appendChild(item);
    });
    detailsBody.appendChild(current);
    var facts = el('dl');
    addFact(facts, t('d_last_contact'), tablet && tablet.age !== null ? t('d_ago', { s: duration(tablet.age) }) : t('d_never'));
    if (tablet && tablet.connected) {
      addFact(facts, t('d_stage'), t('stage_' + tablet.stage));
      addFact(facts, t('d_page'), tablet.visible === false ? t('d_hidden') : t('d_visible'));
      var fs = tablet.fullscreen;
      addFact(facts, t('d_fullscreen'), fs.capable === null ? t('fs_unknown') : fs.capable === false ? t('fs_unavailable') : fs.active ? t('fs_on') : t('fs_off'));
      addFact(facts, t('d_last_save'), tablet.last_save ? clock(tablet.last_save) : '—');
    }
    var progress = row(id);
    var started = progress && !progress.classList.contains('live-not_started');
    addFact(facts, t('d_progress'), started ? Array.prototype.map.call(progress.querySelectorAll('.live-child-fact'), function (node) {
      return node.textContent.trim();
    }).join(' · ') : t('d_no_run'));
    detailsBody.appendChild(facts);
    detailsBody.appendChild(el('h4', null, t('d_history')));
    var history = el('ul');
    (tablet ? tablet.history : []).forEach(function (entry) {
      history.appendChild(el('li', null, clock(entry.at) + ' · ' + t('r_' + entry.code) + ' · ' +
        (entry.event === 'start' ? t('h_start') : t('h_recovered', { s: duration(entry.seconds || 0) }))));
    });
    if (!history.children.length) { history.appendChild(el('li', null, t('d_no_history'))); }
    detailsBody.appendChild(history);
    if (editing) {
      var place = el('label', null, t('place_on') + ' ');
      var choose = el('select');
      choose.appendChild(el('option', null, '—'));
      map.tables.forEach(function (table, index) {
        var option = el('option', null, t('table') + ' ' + (index + 1));
        option.value = table.id;
        choose.appendChild(option);
      });
      var placed = map.placements[id];
      choose.value = placed && placed.table ? placed.table : '—';
      choose.addEventListener('change', function () {
        if (tableById(choose.value)) { map.placements[id] = { table: choose.value }; changed(); render(); }
      });
      place.appendChild(choose);
      detailsBody.appendChild(place);
      var back = el('button', 'button compact', t('to_tray'));
      back.type = 'button';
      back.addEventListener('click', function () { delete map.placements[id]; changed(); render(); });
      detailsBody.appendChild(back);
    }
    var actions = el('p');
    var showList = el('button', 'button compact', t('d_open_list'));
    showList.type = 'button';
    showList.addEventListener('click', function () {
      setView('list');
      var target = row(id);
      if (target) { target.open = true; target.scrollIntoView({ block: 'nearest' }); target.querySelector('summary').focus(); }
    });
    actions.appendChild(showList);
    detailsBody.appendChild(actions);
  }

  $('live-map-details-close').addEventListener('click', function () {
    selectedId = null;
    details.hidden = true;
    applyHealth();
  });

  function noticeNewProblems() {
    var keys = {};
    Object.keys(health.tablets).forEach(function (id) {
      health.tablets[id].reasons.forEach(function (reason) {
        if (ACTIONABLE.indexOf(reason.code) >= 0) { keys[id + '|' + reason.code + '|' + (reason.since || '')] = true; }
      });
    });
    if (seen === null) { seen = keys; return; }  // What was already wrong when the page opened does not beep.
    var fresh = Object.keys(keys).some(function (key) { return !seen[key]; });
    seen = keys;
    if (fresh && sound && !stale && Date.now() - lastBeep > BEEP_GAP_MS) { beep(); }
  }

  function beep() {
    try {
      lastBeep = Date.now();
      var oscillator = audio.createOscillator(), gain = audio.createGain();
      oscillator.frequency.value = 880;
      gain.gain.setValueAtTime(0.2, audio.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.3);
      oscillator.connect(gain).connect(audio.destination);
      oscillator.start();
      oscillator.stop(audio.currentTime + 0.3);
    } catch (_) { /* No sound on this browser: the circles still show everything. */ }
  }

  $('live-map-sound').addEventListener('click', function () {
    sound = !sound;
    $('live-map-sound').setAttribute('aria-pressed', String(sound));
    if (sound && !audio && (window.AudioContext || window.webkitAudioContext)) {
      audio = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (sound && audio && audio.state === 'suspended') { void audio.resume(); }
  });

  function scheduleHealth(delay) {
    window.clearTimeout(healthTimer);
    if (!signedOut && document.visibilityState === 'visible') { healthTimer = window.setTimeout(checkHealth, Math.max(0, delay)); }
  }

  function checkHealth() {
    if (healthInFlight || signedOut) { return; }
    healthInFlight = true;
    var started = Date.now();
    var controller = window.AbortController ? new AbortController() : null;
    var abort = window.setTimeout(function () { if (controller) { controller.abort(); } }, HEALTH_TIMEOUT_MS);
    fetch(root.getAttribute('data-health-url'), { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' },
                                                   signal: controller ? controller.signal : undefined })
      .then(function (response) {
        if (response.status === 401) { signedOut = true; return null; }
        if (!response.ok) { throw new Error('status ' + response.status); }
        return response.json();
      })
      .then(function (data) {
        if (!data) { applyHealth(); return; }
        var firstTime = !health;
        health = data;
        stale = !data.available;
        if (data.available) { healthGoodAt = data.now; }
        if (firstTime) { render(); } else if (missingButtons()) { render(); } else { applyHealth(); }
        if (data.available) { noticeNewProblems(); }
      })
      .catch(function () { stale = true; applyHealth(); })
      .then(function () {
        window.clearTimeout(abort);
        healthInFlight = false;
        scheduleHealth(HEALTH_MS - (Date.now() - started));
      });
  }

  // A tablet registered with an ID the map has not drawn yet (an ID outside the roster) gets its circle.
  function missingButtons() {
    if (!map || drag || dirty) { return false; }
    var drawn = {};
    document.querySelectorAll('#live-map [data-id]').forEach(function (node) { drawn[node.dataset.id] = true; });
    return ids().some(function (id) { return !drawn[id]; });
  }

  // Others' saves reach this page too, as long as nothing here is being edited.
  function refreshMap() {
    if (dirty || editing || drag) { return; }
    fetch(root.getAttribute('data-map-url'), { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (data) {
        if (!data || dirty || editing || drag) { return; }
        csrf = data.csrf;
        var changedRooms = JSON.stringify(data.rooms) !== JSON.stringify(rooms);
        rooms = data.rooms;
        if (!map || data.map.revision !== map.revision) { map = data.map; render(); } else if (changedRooms) { renderRooms(); }
      }).catch(function () { /* The next refresh tries again. */ });
  }

  document.addEventListener('visibilitychange', function () {
    window.clearTimeout(healthTimer);
    if (document.visibilityState === 'visible') {
      stale = true;  // Until a fresh answer comes, what is on screen is not current.
      applyHealth();
      checkHealth();
      refreshMap();
    }
  });

  // -- Map / List ----------------------------------------------------------------------------------------------------
  function setView(view) {
    showView(view);
    remembered = view;
    try { window.localStorage.setItem('solLiveView', view); } catch (_) { /* A per-browser convenience only. */ }
  }
  document.querySelectorAll('[data-live-view]').forEach(function (button) {
    button.addEventListener('click', function () { setView(button.getAttribute('data-live-view')); });
  });
  // The researcher's last choice in this browser; otherwise the map once the session has a layout, else the list.
  var remembered = null;
  try { remembered = window.localStorage.getItem('solLiveView'); } catch (_) { remembered = null; }
  function showView(view) {
    root.hidden = view !== 'map';
    if (listView) { listView.hidden = view !== 'list'; }
    document.querySelectorAll('[data-live-view]').forEach(function (button) {
      button.setAttribute('aria-pressed', String(button.getAttribute('data-live-view') === view));
    });
  }
  showView(remembered === 'map' ? 'map' : 'list');

  fetch(root.getAttribute('data-map-url'), { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    .then(function (response) {
      if (response.status === 401) { signedOut = true; throw new Error('signed out'); }
      return response.json();
    })
    .then(function (data) {
      csrf = data.csrf;
      rooms = data.rooms;
      map = data.map;
      render();
      if (!remembered) { showView(map.tables.length ? 'map' : 'list'); }
      checkHealth();
      window.setInterval(refreshMap, MAP_REFRESH_MS);
    })
    .catch(function () { applyHealth(); });
}());
