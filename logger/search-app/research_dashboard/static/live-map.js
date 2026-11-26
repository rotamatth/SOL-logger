/*
 * The live view's classroom map: the session's copy of a room drawn to scale, one circle per tablet (its sticker's
 * ID) on its desk, and each tablet's health.
 *
 * The room comes from classroom.json and changes only on the Rooms page or by bringing its new version in here;
 * this page only places IDs, one at a time, by tapping an empty spot or dragging an ID from the strip. The health
 * comes from health.json every two seconds and only repaints the circles. When the health feed fails, the whole map
 * says it is not current instead of blaming the tablets. Sound is off until the researcher turns it on, and then
 * beeps once per new problem, never per poll. Tapping a tablet opens its details; moving it is a deliberate action.
 */
(function () {
  'use strict';
  var root = document.getElementById('live-map');
  if (!root || !window.SolRoomDrawing) { return; }

  var HEALTH_MS = 2000, HEALTH_TIMEOUT_MS = 2000, MAP_REFRESH_MS = 15000, BEEP_GAP_MS = 4000;
  var ACTIONABLE = ['no_contact', 'search_failed', 'save_failed', 'save_unconfirmed', 'page_hidden', 'fullscreen_off',
                    'search_waiting', 'two_tablets'];
  var ICON = { red: '✕', amber: '!', green: '✓', grey: '?' };
  var strings = JSON.parse(root.getAttribute('data-strings') || '{}');
  var drawing = window.SolRoomDrawing.create(JSON.parse(root.getAttribute('data-config')), JSON.parse(root.getAttribute('data-room-strings')));
  var make = drawing.make;
  var $ = function (id) { return document.getElementById(id); };
  var svg = $('live-map-floor'), tray = $('live-map-tray'), roomsSelect = $('live-map-rooms');
  var message = $('live-map-message'), monitorLine = $('live-map-monitor'), problems = $('live-map-problems');
  var details = $('live-map-details'), detailsBody = $('live-map-details-body'), detailsId = $('live-map-details-id');
  var picker = $('live-map-picker'), stage = $('live-map-stage'), floorCard = $('live-map-floor-card');
  var workspace = $('live-workspace'), listView = $('live-list-view');

  var map = null, rooms = [], csrf = '', roomChanged = false, layers = null;
  var selectedId = null, moving = null, pickerSpot = null, drag = null;
  var health = null, healthGoodAt = null, stale = true, signedOut = false;
  var sound = false, audio = null, seen = null, lastBeep = 0;
  var healthTimer = null, healthInFlight = false, view = 'list';

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
  function hasRoom() { return Boolean(map && map.revision > 0 && map.width); }

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
  function spots() { return hasRoom() ? drawing.allSpots(map) : []; }
  function spotById(id) { return spots().filter(function (spot) { return spot.id === id; })[0] || null; }
  function placeOf(id) { return map && map.placements[id] ? spotById(map.placements[id]) : null; }
  function occupant(spotId) {
    var found = null;
    Object.keys(map.placements).forEach(function (id) { if (map.placements[id] === spotId) { found = id; } });
    return found;
  }
  function unplaced() { return ids().filter(function (id) { return !placeOf(id); }); }

  function tabletOf(id) { return health && health.tablets[id] ? health.tablets[id] : null; }
  function statusOf(id) { var tablet = tabletOf(id); return tablet ? tablet.status : 'grey'; }
  function shortText(id) {
    var tablet = tabletOf(id);
    if (!tablet || !tablet.connected) { return t('not_connected'); }
    return tablet.reasons.length ? t('r_' + tablet.reasons[0].code) : t('ok');
  }

  // -- Drawing: the room once per change, the circles on every poll ----------------------------------------------
  function renderRoom() {
    var empty = $('live-map-empty');
    renderRooms();
    renderRoomChanged();
    if (!hasRoom()) {
      svg.textContent = '';
      svg.hidden = true;
      empty.hidden = false;
      $('live-map-empty-text').textContent = rooms.length ? t('no_room') : t('no_rooms_saved');
      $('live-map-empty-link').textContent = t('open_rooms');
      layers = null;
      renderMarks();
      return;
    }
    svg.hidden = false;
    empty.hidden = true;
    layers = drawing.draw(svg, map, { grid: 100 });
    renderMarks();
  }

  function renderMarks() {
    var focused = document.activeElement, focusKey = null;
    if (focused && focused.closest) {
      var holder = focused.closest('[data-id], [data-spot]');
      if (holder && root.contains(holder)) { focusKey = holder.getAttribute('data-id') ? 'id:' + holder.getAttribute('data-id') : 'spot:' + holder.getAttribute('data-spot'); }
    }
    if (layers) {
      layers.overlay.textContent = '';
      layers.pieces.querySelectorAll('.room-desk').forEach(function (desk) { desk.classList.remove('room-desk-red', 'room-desk-amber'); });
      spots().forEach(function (spot) {
        var id = occupant(spot.id);
        var group;
        if (id) {
          var status = statusOf(id);
          group = make('g', { 'class': 'map-node map-' + status + (selectedId === id ? ' selected' : '') + (moving === id ? ' moving' : ''),
                              'data-id': id, tabindex: '0', role: 'button', transform: 'translate(' + spot.x + ' ' + spot.y + ')',
                              'aria-label': 'ID ' + id + ': ' + shortText(id) }, layers.overlay);
          if (status === 'red' || status === 'amber') { make('circle', { 'class': 'map-pulse', r: 22 }, group); }
          if (selectedId === id) { make('circle', { 'class': 'map-focus-ring', r: 31 }, group); }
          make('circle', { 'class': 'map-ring', r: 21 }, group);
          make('text', { 'class': 'map-id', y: 1 }, group, id);
          make('circle', { 'class': 'map-badge', cx: 17, cy: -16, r: 9 }, group);
          make('text', { 'class': 'map-badge-icon', x: 17, y: -15.5 }, group, ICON[status]);
          if (status === 'red' || status === 'amber') {
            var desk = layers.pieces.querySelector('[data-piece="' + spot.piece.id + '"] [data-desk="' + spot.desk + '"]');
            if (desk && !desk.classList.contains('room-desk-red')) { desk.classList.add('room-desk-' + status); }
          }
        } else {
          group = make('g', { 'class': 'map-spot' + (moving || drag ? ' target' : '') + (pickerSpot === spot.id ? ' open' : ''),
                              'data-spot': spot.id, tabindex: '0', role: 'button', transform: 'translate(' + spot.x + ' ' + spot.y + ')',
                              'aria-label': t('empty_spot', { place: drawing.spotLabel(map, spot) }) }, layers.overlay);
          make('circle', { 'class': 'map-spot-circle', r: 18 }, group);
          make('text', { 'class': 'map-spot-plus', y: 1 }, group, '+');
        }
      });
    }
    renderTray();
    applyChips();
    renderProblems();
    if (selectedId) { renderDetails(); }
    if (focusKey) {
      var again = focusKey.indexOf('id:') === 0 ? root.querySelector('[data-id="' + cssEscape(focusKey.slice(3)) + '"]')
                                                 : root.querySelector('[data-spot="' + cssEscape(focusKey.slice(5)) + '"]');
      if (again && again !== document.activeElement) { again.focus({ preventScroll: true }); }
    }
    var notCurrent = stale || signedOut;
    root.classList.toggle('monitor-stale', notCurrent);
  }
  function cssEscape(value) { return window.CSS && CSS.escape ? CSS.escape(value) : value.replace(/["\\]/g, '\\$&'); }

  function renderTray() {
    tray.textContent = '';
    var waiting = unplaced();
    waiting.forEach(function (id) {
      var status = statusOf(id);
      var button = el('button', 'map-chip map-' + status + (selectedId === id ? ' selected' : ''));
      button.type = 'button';
      button.dataset.id = id;
      button.appendChild(el('span', 'map-chip-id', id));
      button.appendChild(el('span', 'map-chip-icon', ICON[status]));
      button.setAttribute('aria-label', 'ID ' + id + ': ' + shortText(id));
      tray.appendChild(button);
    });
    $('live-map-tray-hint').textContent = !hasRoom() ? '' : waiting.length ? t('tray_hint') : t('tray_empty');
  }

  function renderRooms() {
    roomsSelect.textContent = '';
    var placeholder = el('option', null, t('choose_room'));
    placeholder.value = '';
    roomsSelect.appendChild(placeholder);
    rooms.forEach(function (room) {
      var option = el('option', null, room.name);
      option.value = room.id;
      roomsSelect.appendChild(option);
    });
    var known = map && rooms.some(function (room) { return room.id === map.room_id; });
    roomsSelect.value = known ? map.room_id : '';
    if (map && map.room_id && !known) {
      var gone = el('option', null, '—');
      gone.value = map.room_id;
      gone.disabled = true;
      roomsSelect.appendChild(gone);
      roomsSelect.value = map.room_id;
    }
  }

  function renderRoomChanged() {
    var box = $('live-map-room-changed'), room = map && rooms.filter(function (item) { return item.id === map.room_id; })[0];
    box.hidden = !(roomChanged && room) && !(map && map.room_id && !room);
    if (box.hidden) { return; }
    $('live-map-room-changed-text').textContent = room ? t('room_changed', { name: room.name }) : t('room_gone');
    $('live-map-room-update').hidden = !room;
    $('live-map-room-update').textContent = t('room_update');
  }

  // -- Health -----------------------------------------------------------------------------------------------------
  function applyMonitorLine() {
    var notCurrent = stale || signedOut;
    if (signedOut) { monitorLine.textContent = t('signed_out'); }
    else if (!health) { monitorLine.textContent = t('checking'); }
    else if (!health.available) { monitorLine.textContent = t('unavailable'); }
    else if (stale) { monitorLine.textContent = t('stale', { clock: healthGoodAt ? clock(healthGoodAt) : '—' }); }
    else { monitorLine.textContent = t('live', { clock: health.clock }); }
    monitorLine.classList.toggle('live-map-problem', notCurrent && Boolean(health || signedOut));
    monitorLine.classList.toggle('live-map-ok', !notCurrent);
  }

  function applyChips() {
    document.querySelectorAll('[data-monitor-for]').forEach(function (chip) {
      var id = chip.getAttribute('data-monitor-for'), status = statusOf(id);
      chip.hidden = !health;
      chip.className = 'badge live-monitor map-' + status;
      chip.textContent = shortText(id);
    });
  }

  function renderProblems() {
    problems.textContent = '';
    problems.className = 'live-map-problems';
    if (!health) { return; }
    var list = ids().filter(function (id) { var status = statusOf(id); return status === 'red' || status === 'amber'; });
    list.sort(function (a, b) { return (statusOf(a) === 'red' ? 0 : 1) - (statusOf(b) === 'red' ? 0 : 1) || numeric(a, b); });
    var worst = list.length ? statusOf(list[0]) : 'green';
    problems.classList.add('live-map-problems-' + worst);
    problems.appendChild(el('h3', null, list.length === 0 ? t('problems_none') : list.length === 1 ? t('problem_one') : t('problems', { n: list.length })));
    var now = health.now;
    list.forEach(function (id) {
      var status = statusOf(id), tablet = tabletOf(id), reason = tablet && tablet.reasons[0];
      var button = el('button', 'map-problem map-' + status + (selectedId === id ? ' selected' : ''));
      button.type = 'button';
      button.appendChild(el('span', 'map-problem-icon', ICON[status]));
      button.appendChild(document.createTextNode(id + ' · ' + shortText(id)));
      if (reason && reason.since) { button.appendChild(el('small', null, ' ' + duration(now - reason.since))); }
      button.addEventListener('click', function () { select(id, true); });
      problems.appendChild(button);
    });
  }

  function select(id, reveal) {
    selectedId = id;
    moving = null;
    closePicker();
    setView('map');
    renderMarks();
    var target = root.querySelector('[data-id="' + cssEscape(id) + '"]');
    if (target && reveal) {
      if (target.scrollIntoView) { target.scrollIntoView({ block: 'nearest', inline: 'nearest' }); }
      target.focus({ preventScroll: true });
    }
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

  function action(label, handler, primary) {
    var button = el('button', 'button compact' + (primary ? ' primary' : ''), label);
    button.type = 'button';
    button.addEventListener('click', handler);
    return button;
  }

  function renderDetails() {
    var id = selectedId, tablet = tabletOf(id), status = statusOf(id), place = placeOf(id);
    details.hidden = false;
    stage.classList.add('with-details');
    details.className = 'live-map-details map-' + status;
    detailsId.textContent = 'ID ' + id;
    $('live-map-details-place').textContent = place ? drawing.spotLabel(map, place) : t('not_placed');
    detailsBody.textContent = '';
    var now = health ? health.now : Date.now() / 1000;
    var current = el('div', 'live-map-now');
    if (!tablet || !tablet.connected) { current.appendChild(el('strong', null, t('not_connected'))); }
    else if (!tablet.reasons.length) { current.appendChild(el('strong', null, ICON.green + ' ' + t('ok'))); }
    (tablet ? tablet.reasons : []).forEach(function (reason) {
      var since = reason.since ? duration(now - reason.since) : '—';
      var item = el('p', 'map-reason-' + reason.severity);
      item.appendChild(el('strong', null, ICON[reason.severity === 'red' ? 'red' : 'amber'] + ' ' + t('r_' + reason.code)));
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

    var actions = $('live-map-details-actions');
    actions.textContent = '';
    actions.appendChild(action(t('d_open_list'), function () {
      setView('list');
      var target = row(id);
      if (target) { target.open = true; target.scrollIntoView({ block: 'nearest' }); target.querySelector('summary').focus(); }
    }));
    if (hasRoom()) {
      actions.appendChild(action(place ? t('move') : t('place'), function () { startMoving(id); }, !place));
      if (place) { actions.appendChild(action(t('unplace'), function () { place_(id, ''); })); }
    }
  }

  function closeDetails() {
    selectedId = null;
    moving = null;
    details.hidden = true;
    stage.classList.remove('with-details');
    say('');
    renderMarks();
  }
  $('live-map-details-close').addEventListener('click', closeDetails);

  // -- Placing IDs ------------------------------------------------------------------------------------------------
  function startMoving(id) {
    moving = id;
    closePicker();
    say(t('moving', { id: id }));
    renderMarks();
    var first = root.querySelector('.map-spot');
    if (first) { first.focus({ preventScroll: true }); }
  }

  function openPicker(spotId) {
    var spot = spotById(spotId);
    if (!spot) { return; }
    pickerSpot = spotId;
    $('live-map-picker-title').textContent = t('picker_title', { place: drawing.spotLabel(map, spot) });
    $('live-map-picker-hint').textContent = t('picker_hint');
    $('live-map-picker-cancel').textContent = t('cancel');
    var list = $('live-map-picker-ids');
    list.textContent = '';
    var waiting = unplaced();
    if (!waiting.length) { list.appendChild(el('p', 'small muted', t('picker_none'))); }
    waiting.forEach(function (id) {
      var button = el('button', 'map-chip map-' + statusOf(id));
      button.type = 'button';
      button.dataset.pick = id;
      button.appendChild(el('span', 'map-chip-id', id));
      button.appendChild(el('span', 'map-chip-icon', ICON[statusOf(id)]));
      button.setAttribute('aria-label', 'ID ' + id + ': ' + shortText(id));
      button.addEventListener('click', function () { place_(id, spotId); });
      list.appendChild(button);
    });
    picker.hidden = false;
    // Next to the spot, inside the map's card.
    var matrix = svg.getScreenCTM(), card = floorCard.getBoundingClientRect();
    if (matrix) {
      var at = new DOMPoint(spot.x, spot.y).matrixTransform(matrix);
      var left = at.x - card.left + 30, top = at.y - card.top - 30;
      var width = picker.offsetWidth, height = picker.offsetHeight;
      if (left + width > card.width - 8) { left = Math.max(8, at.x - card.left - 30 - width); }
      top = Math.max(8, Math.min(top, card.height - height - 8));
      picker.style.left = left + 'px';
      picker.style.top = top + 'px';
    }
    renderMarks();
    var first = list.querySelector('button');
    if (first) { first.focus({ preventScroll: true }); } else { $('live-map-picker-cancel').focus(); }
  }
  function closePicker() {
    if (picker.hidden) { return; }
    var spotId = pickerSpot;
    picker.hidden = true;
    pickerSpot = null;
    renderMarks();
    var back = spotId && root.querySelector('[data-spot="' + cssEscape(spotId) + '"]');
    if (back) { back.focus({ preventScroll: true }); }
  }
  $('live-map-picker-cancel').addEventListener('click', closePicker);

  function post(url, fields) {
    var body = new URLSearchParams();
    body.set('csrf', csrf);
    Object.keys(fields).forEach(function (name) { body.set(name, fields[name]); });
    return fetch(url, { method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json' }, body: body })
      .then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (data) { return { status: response.status, data: data }; });
      });
  }
  function received(data) {
    if (data.csrf) { csrf = data.csrf; }
    if (data.rooms) { rooms = data.rooms; }
    if (data.map) { map = data.map; }
    if (data.room_changed !== undefined) { roomChanged = data.room_changed; }
  }

  function place_(id, spotId) {
    picker.hidden = true;
    pickerSpot = null;
    moving = null;
    post(root.getAttribute('data-place-url'), { participant: id, spot: spotId }).then(function (reply) {
      received(reply.data);
      if (reply.status === 200) { say(''); }
      else if (reply.status === 409) { say(t('spot_taken'), true); }
      else { say(t('save_failed'), true); }
      renderRoom();
    }).catch(function () { say(t('save_failed'), true); renderMarks(); });
  }

  function useRoom(roomId) {
    post(root.getAttribute('data-room-url'), { room_id: roomId, revision: map ? map.revision : 0 }).then(function (reply) {
      received(reply.data);
      say(reply.status === 200 ? '' : reply.status === 409 ? t('conflict') : t('save_failed'), reply.status !== 200);
      renderRoom();
      if (reply.status === 200 && hasRoom()) { setView('map'); }
    }).catch(function () { say(t('save_failed'), true); renderRooms(); });
  }

  roomsSelect.addEventListener('change', function () {
    var room = rooms.filter(function (item) { return item.id === roomsSelect.value; })[0];
    if (!room) { renderRooms(); return; }
    if (map && Object.keys(map.placements).length && !window.confirm(t('use_room_confirm', { name: room.name }))) { renderRooms(); return; }
    useRoom(room.id);
  });
  $('live-map-room-update').addEventListener('click', function () { if (map && map.room_id) { useRoom(map.room_id); } });

  // Taps on the map: a tablet opens its details; an empty spot opens the picker, or takes the ID being moved.
  function activate(target) {
    var node = target.closest('[data-id]'), spot = target.closest('[data-spot]');
    if (node && root.contains(node)) {
      if (node.closest('#live-map-picker')) { return; }
      if (selectedId === node.getAttribute('data-id') && !moving) { closeDetails(); return; }
      select(node.getAttribute('data-id'), false);
      var again = root.querySelector('[data-id="' + cssEscape(node.getAttribute('data-id')) + '"]');
      if (again) { again.focus({ preventScroll: true }); }
    } else if (spot) {
      if (moving) { place_(moving, spot.getAttribute('data-spot')); } else { openPicker(spot.getAttribute('data-spot')); }
    }
  }
  root.addEventListener('click', function (event) {
    if (drag && drag.moved) { return; }
    if (event.target.closest('#live-map-picker, #live-map-details, #live-map-problems')) { return; }
    activate(event.target);
  });
  root.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      if (!picker.hidden) { closePicker(); event.preventDefault(); return; }
      if (moving) { moving = null; say(''); renderMarks(); event.preventDefault(); return; }
      if (selectedId) { closeDetails(); event.preventDefault(); }
      return;
    }
    if ((event.key === 'Enter' || event.key === ' ') && event.target.closest && event.target.closest('svg [data-id], svg [data-spot]')) {
      event.preventDefault();
      activate(event.target);
    }
  });
  document.addEventListener('pointerdown', function (event) {
    if (!picker.hidden && !event.target.closest('#live-map-picker') && !event.target.closest('[data-spot]')) { closePicker(); }
  });

  // Dragging an ID from the strip onto an empty spot. A simple tap on it opens its details instead (the click).
  function spotAt(x, y) {
    var found = null;
    document.elementsFromPoint(x, y).forEach(function (node) { if (!found && node.closest) { found = node.closest('[data-spot]'); } });
    return found;
  }
  tray.addEventListener('pointerdown', function (event) {
    var chip = event.target.closest('[data-id]');
    if (!chip || event.button > 0 || !hasRoom()) { return; }
    drag = { id: chip.dataset.id, startX: event.clientX, startY: event.clientY, moved: false, ghost: null };
    document.addEventListener('pointermove', dragMove);
    document.addEventListener('pointerup', dragEnd);
    document.addEventListener('pointercancel', dragCancel);
  });
  function dragMove(event) {
    if (!drag) { return; }
    if (!drag.moved && Math.abs(event.clientX - drag.startX) + Math.abs(event.clientY - drag.startY) < 6) { return; }
    if (!drag.moved) {
      drag.moved = true;
      drag.ghost = el('div', 'map-ghost', drag.id);
      document.body.appendChild(drag.ghost);
      root.querySelectorAll('.map-spot').forEach(function (node) { node.classList.add('target'); });
    }
    event.preventDefault();
    drag.ghost.style.left = event.clientX + 'px';
    drag.ghost.style.top = event.clientY + 'px';
    var over = spotAt(event.clientX, event.clientY);
    root.querySelectorAll('.map-spot').forEach(function (node) { node.classList.toggle('hover', node === over); });
  }
  function finishDrag(event, cancelled) {
    document.removeEventListener('pointermove', dragMove);
    document.removeEventListener('pointerup', dragEnd);
    document.removeEventListener('pointercancel', dragCancel);
    if (!drag) { return; }
    var current = drag;
    if (current.ghost) { current.ghost.remove(); }
    var spot = !cancelled && current.moved ? spotAt(event.clientX, event.clientY) : null;
    // The click that follows a real drag must not also open the details: forget the drag only after it.
    window.setTimeout(function () { drag = null; if (current.moved && !spot) { renderMarks(); } }, 0);
    if (spot) { place_(current.id, spot.getAttribute('data-spot')); }
  }
  function dragEnd(event) { finishDrag(event, false); }
  function dragCancel(event) { finishDrag(event, true); }

  // -- Sound --------------------------------------------------------------------------------------------------------
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

  // -- Polling --------------------------------------------------------------------------------------------------------
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
        if (data) {
          health = data;
          stale = !data.available;
          if (data.available) { healthGoodAt = data.now; }
        }
        applyMonitorLine();
        if (!drag) { renderMarks(); }
        if (data && data.available) { noticeNewProblems(); }
      })
      .catch(function () { stale = true; applyMonitorLine(); if (!drag) { renderMarks(); } })
      .then(function () {
        window.clearTimeout(abort);
        healthInFlight = false;
        scheduleHealth(HEALTH_MS - (Date.now() - started));
      });
  }

  // Others' changes reach this page too, unless an ID is being placed here right now.
  function refreshMap() {
    if (drag || moving || !picker.hidden) { return; }
    fetch(root.getAttribute('data-map-url'), { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (data) {
        if (!data || drag || moving || !picker.hidden) { return; }
        var before = JSON.stringify([map, rooms, roomChanged]);
        received(data);
        if (JSON.stringify([map, rooms, roomChanged]) !== before) { renderRoom(); }
      }).catch(function () { /* The next refresh tries again. */ });
  }

  document.addEventListener('visibilitychange', function () {
    window.clearTimeout(healthTimer);
    if (document.visibilityState === 'visible') {
      stale = true;  // Until a fresh answer comes, what is on screen is not current.
      applyMonitorLine();
      renderMarks();
      checkHealth();
      refreshMap();
    }
  });

  // -- Map / List ------------------------------------------------------------------------------------------------------
  function showView(next) {
    view = next;
    root.hidden = view !== 'map';
    if (listView) { listView.hidden = view !== 'list'; }
    if (workspace) { workspace.classList.toggle('live-mode-map', view === 'map'); }
    document.querySelectorAll('.live-map-only').forEach(function (node) { node.hidden = view !== 'map'; });
    document.querySelectorAll('[data-live-view]').forEach(function (button) {
      button.setAttribute('aria-pressed', String(button.getAttribute('data-live-view') === view));
    });
  }
  function setView(next) {
    showView(next);
    remembered = next;
    try { window.localStorage.setItem('solLiveView', next); } catch (_) { /* A per-browser convenience only. */ }
  }
  document.querySelectorAll('[data-live-view]').forEach(function (button) {
    button.addEventListener('click', function () { setView(button.getAttribute('data-live-view')); });
  });
  // The researcher's last choice in this browser; otherwise the map once the session has a room, else the list.
  var remembered = null;
  try { remembered = window.localStorage.getItem('solLiveView'); } catch (_) { remembered = null; }
  showView(remembered === 'map' ? 'map' : 'list');
  applyMonitorLine();

  fetch(root.getAttribute('data-map-url'), { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    .then(function (response) {
      if (response.status === 401) { signedOut = true; throw new Error('signed out'); }
      return response.json();
    })
    .then(function (data) {
      received(data);
      renderRoom();
      if (!remembered) { showView(hasRoom() ? 'map' : 'list'); }
      checkHealth();
      window.setInterval(refreshMap, MAP_REFRESH_MS);
    })
    .catch(function () { applyMonitorLine(); renderMarks(); });
}());
