/*
 * Draws a classroom to scale in an SVG whose units are centimetres: the walls, the floor's squares, double desks,
 * islands of desks pushed together, landmarks (teacher's desk, board, doors, windows) and each desk's tablet spots.
 * Shared by the Rooms page's editor and the live view's map. Every size comes from the server (rooms.py) as data,
 * so the two drawings and the server's checks cannot disagree.
 */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';

  function make(tag, attrs, parent, text) {
    var node = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (name) { node.setAttribute(name, attrs[name]); });
    if (text !== undefined && text !== null) { node.textContent = text; }
    if (parent) { parent.appendChild(node); }
    return node;
  }

  function rotate(x, y, degrees) {
    var r = degrees * Math.PI / 180;
    return [x * Math.cos(r) - y * Math.sin(r), x * Math.sin(r) + y * Math.cos(r)];
  }

  function create(config, strings) {
    var desk = config.desk, seat = config.seat;
    function t(key, values) {
      var text = strings[key] || key;
      Object.keys(values || {}).forEach(function (name) { text = text.split('{' + name + '}').join(values[name]); });
      return text;
    }

    // Where a piece's desks sit, from its centre and before it turns.
    function desksOf(piece) {
      if (piece.kind === 'desk') { return [[0, 0]]; }
      if (piece.kind === 'island') { return config.islands[String(piece.desks)] || []; }
      return [];
    }

    function sizeOf(piece) {
      if (piece.kind === 'desk') { return [desk[0], desk[1]]; }
      if (piece.kind === 'island') {
        var spots = desksOf(piece), xs = spots.map(function (d) { return d[0]; }), ys = spots.map(function (d) { return d[1]; });
        return [Math.max.apply(null, xs) - Math.min.apply(null, xs) + desk[0], Math.max.apply(null, ys) - Math.min.apply(null, ys) + desk[1]];
      }
      return config.landmarks[piece.kind] || [50, 50];
    }

    // Every tablet spot, named piece.desk.seat as on the server, at its place in the room.
    function spotsOf(piece) {
      var found = [];
      desksOf(piece).forEach(function (offset, index) {
        var count = piece.tablets || 0;
        for (var s = 0; s < count; s += 1) {
          var along = count === 2 ? (s === 0 ? -seat : seat) : 0;
          var turned = rotate(offset[0] + along, offset[1], piece.rotation || 0);
          found.push({ id: piece.id + '.' + index + '.' + s, piece: piece, desk: index, seat: s,
                       x: piece.x + turned[0], y: piece.y + turned[1] });
        }
      });
      return found;
    }

    function allSpots(geometry) {
      var found = [];
      geometry.pieces.forEach(function (piece) { found = found.concat(spotsOf(piece)); });
      return found;
    }

    // Desks and islands are numbered in the order they were added, for the details panel and the editor.
    function labels(geometry) {
      var found = {}, desks = 0, islands = 0;
      geometry.pieces.forEach(function (piece) {
        if (piece.kind === 'desk') { desks += 1; found[piece.id] = t('rooms_label_desk', { n: desks }); }
        if (piece.kind === 'island') { islands += 1; found[piece.id] = t('rooms_label_island', { n: islands }); }
      });
      return found;
    }
    function spotLabel(geometry, spot) {
      var names = labels(geometry), piece = spot.piece;
      if (piece.kind === 'island') {
        return t('rooms_label_island_desk', { n: names[piece.id].replace(/\D+/g, ''), d: spot.desk + 1 });
      }
      return names[piece.id] || '';
    }

    function drawPiece(layer, piece, options, names) {
      var size = sizeOf(piece);
      var group = make('g', { 'class': 'room-piece room-kind-' + piece.kind, 'data-piece': piece.id,
                              transform: 'translate(' + piece.x + ' ' + piece.y + ') rotate(' + (piece.rotation || 0) + ')' }, layer);
      var hitH = Math.max(size[1], 36);
      make('rect', { 'class': 'room-hit', x: -size[0] / 2 - 4, y: -hitH / 2 - 4, width: size[0] + 8, height: hitH + 8 }, group);
      if (piece.kind === 'desk' || piece.kind === 'island') {
        if (piece.kind === 'island') {
          make('rect', { 'class': 'room-island', x: -size[0] / 2 - 8, y: -size[1] / 2 - 8, width: size[0] + 16, height: size[1] + 16, rx: 10 }, group);
        }
        desksOf(piece).forEach(function (offset, index) {
          make('rect', { 'class': 'room-desk', 'data-desk': index, x: offset[0] - desk[0] / 2, y: offset[1] - desk[1] / 2,
                         width: desk[0], height: desk[1], rx: 5 }, group);
        });
        if (options.labels && names[piece.id]) {
          make('text', { 'class': 'room-desk-label', x: -size[0] / 2 + 6, y: -size[1] / 2 + 14 }, group, names[piece.id]);
        }
        if (options.spots) {
          desksOf(piece).forEach(function (offset) {
            var count = piece.tablets || 0;
            for (var s = 0; s < count; s += 1) {
              var along = count === 2 ? (s === 0 ? -seat : seat) : 0;
              make('circle', { 'class': 'room-spot-outline', cx: offset[0] + along, cy: offset[1], r: 16 }, group);
            }
          });
        }
      } else if (piece.kind === 'door') {
        make('rect', { 'class': 'room-door-gap', x: -size[0] / 2, y: -size[1] / 2, width: size[0], height: size[1] }, group);
        make('path', { 'class': 'room-door-swing', d: 'M ' + (-size[0] / 2) + ' ' + (size[1] / 2) + ' L ' + (-size[0] / 2) + ' ' + (size[1] / 2 + size[0]) +
                       ' A ' + size[0] + ' ' + size[0] + ' 0 0 0 ' + (size[0] / 2) + ' ' + (size[1] / 2) }, group);
        make('text', { 'class': 'room-mark', x: 0, y: size[1] / 2 + 26, 'text-anchor': 'middle' }, group, t('rooms_mark_door'));
      } else {
        make('rect', { 'class': 'room-landmark room-landmark-' + piece.kind, x: -size[0] / 2, y: -size[1] / 2, width: size[0], height: size[1],
                       rx: piece.kind === 'teacher' ? 6 : 2 }, group);
        var labelY = piece.kind === 'teacher' ? 5 : size[1] / 2 + 22;
        make('text', { 'class': 'room-mark', x: 0, y: labelY, 'text-anchor': 'middle' }, group, t('rooms_mark_' + piece.kind));
      }
      return group;
    }

    /*
     * Draws the room into the svg and returns its layers. options: grid (cm between lines), rulers (metre marks
     * along two walls), labels (desk and island names), spots (faint circles where tablets go).
     */
    function draw(svg, geometry, options) {
      options = options || {};
      var pad = options.rulers ? 44 : 16;
      var width = geometry.width, depth = geometry.depth;
      svg.setAttribute('viewBox', [-pad, -pad, width + pad * 2, depth + pad * 2].join(' '));
      svg.textContent = '';
      var base = make('g', { 'class': 'room-base' }, svg);
      make('rect', { 'class': 'room-floor-area', x: 0, y: 0, width: width, height: depth }, base);
      var step = options.grid || config.grid;
      for (var x = step; x < width; x += step) {
        make('line', { 'class': 'room-grid' + (x % 100 ? '' : ' room-grid-metre'), x1: x, y1: 0, x2: x, y2: depth }, base);
      }
      for (var y = step; y < depth; y += step) {
        make('line', { 'class': 'room-grid' + (y % 100 ? '' : ' room-grid-metre'), x1: 0, y1: y, x2: width, y2: y }, base);
      }
      if (options.rulers) {
        for (var mx = 0; mx <= width; mx += 100) { make('text', { 'class': 'room-ruler', x: mx, y: -14, 'text-anchor': 'middle' }, base, (mx / 100) + ' m'); }
        for (var my = 100; my <= depth; my += 100) { make('text', { 'class': 'room-ruler', x: -12, y: my + 4, 'text-anchor': 'end' }, base, String(my / 100)); }
      }
      var pieces = make('g', { 'class': 'room-pieces' }, svg);
      var names = labels(geometry);
      // Landmarks first, so desks and their tablets are never hidden under a board or a door's swing.
      geometry.pieces.filter(function (p) { return p.kind !== 'desk' && p.kind !== 'island'; }).forEach(function (piece) { drawPiece(pieces, piece, options, names); });
      geometry.pieces.filter(function (p) { return p.kind === 'desk' || p.kind === 'island'; }).forEach(function (piece) { drawPiece(pieces, piece, options, names); });
      make('rect', { 'class': 'room-walls', x: 0, y: 0, width: width, height: depth }, base);
      var overlay = make('g', { 'class': 'room-overlay' }, svg);
      return { base: base, pieces: pieces, overlay: overlay };
    }

    // Client coordinates to centimetres in the room.
    function toRoom(svg, clientX, clientY) {
      var matrix = svg.getScreenCTM();
      if (!matrix) { return { x: 0, y: 0 }; }
      var point = new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse());
      return { x: point.x, y: point.y };
    }

    return { make: make, rotate: rotate, desksOf: desksOf, sizeOf: sizeOf, spotsOf: spotsOf, allSpots: allSpots,
             labels: labels, spotLabel: spotLabel, draw: draw, toRoom: toRoom, t: t };
  }

  window.SolRoomDrawing = { create: create };
}());
