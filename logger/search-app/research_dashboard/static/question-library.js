(function () {
  'use strict';

  var source = document.querySelector('[data-library-data]');
  if (!source) { return; }
  var sets, questions, labels;
  try {
    sets = JSON.parse(source.getAttribute('data-library-sets'));
    questions = JSON.parse(source.getAttribute('data-library-questions'));
    labels = JSON.parse(source.getAttribute('data-library-labels'));
  } catch (error) { return; }

  function element(tag, className, content) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (content !== undefined) { node.textContent = content; }
    return node;
  }

  function metadata(parent, values, title) {
    var keys = Object.keys(values || {});
    if (!keys.length) { return; }
    var details = element('details', 'library-metadata');
    details.appendChild(element('summary', '', title));
    var list = element('dl');
    keys.forEach(function (key) {
      list.appendChild(element('dt', '', key.replace(/_/g, ' ')));
      var value = values[key];
      list.appendChild(element('dd', '', typeof value === 'object' ? JSON.stringify(value) : String(value)));
    });
    details.appendChild(list);
    parent.appendChild(details);
  }

  function preview(item, kind, compact) {
    var card = element('div', 'library-card-content');
    if (kind === 'sets') {
      card.appendChild(element('h4', '', item.label));
      metadata(card, item.question_set.metadata, labels.condition);
      var list = element('ol', 'library-question-list');
      item.question_set.questions.forEach(function (question) {
        var row = element('li');
        row.appendChild(element('strong', '', question.topic));
        if (!compact) {
          row.appendChild(element('p', '', question.question));
          metadata(row, question.metadata, labels.details);
        }
        list.appendChild(row);
      });
      card.appendChild(list);
    } else {
      card.appendChild(element('h4', '', item.topic));
      card.appendChild(element('p', '', item.question));
      if (item.has_variants) { card.appendChild(element('p', 'library-variant-note', labels.variants)); }
      var sources = element('details', 'library-metadata');
      sources.appendChild(element('summary', '', labels.source + ' (' + item.sources.length + ')'));
      item.sources.forEach(function (entry) {
        var row = element('div', 'library-source');
        row.appendChild(element('p', '', entry.label));
        metadata(row, entry.set_metadata, labels.condition);
        metadata(row, entry.question_data.metadata, labels.details);
        sources.appendChild(row);
      });
      card.appendChild(sources);
    }
    return card;
  }

  function searchableMetadata(values) {
    // Content identifiers are opaque hashes; including them makes an ordinary
    // number search match unrelated questions just because a hash contains it.
    return Object.keys(values || {}).filter(function (key) {
      return key !== 'id' && !/_id$/.test(key);
    }).map(function (key) { return key.replace(/_/g, ' ') + ' ' + JSON.stringify(values[key]); }).join(' ');
  }

  function searchText(item, kind) {
    if (kind === 'sets') {
      return [item.label, searchableMetadata(item.question_set.metadata)].concat(
        item.question_set.questions.map(function (question) {
          return question.topic + ' ' + question.question + ' ' + searchableMetadata(question.metadata);
        })
      ).join(' ').toLocaleLowerCase();
    }
    return [item.topic, item.question].concat(item.sources.map(function (entry) {
      return entry.label + ' ' + searchableMetadata(entry.set_metadata) + ' ' +
        searchableMetadata(entry.question_data.metadata);
    })).join(' ').toLocaleLowerCase();
  }

  document.querySelectorAll('[data-library-kind]').forEach(function (container) {
    var kind = container.getAttribute('data-library-kind');
    var items = kind === 'sets' ? sets : questions;
    var select = container.querySelector('select');
    if (!select || !Array.isArray(items)) { return; }
    var enhancement = element('div', 'library-browser');
    var searchId = select.id + '-search';
    var label = element('label', '', labels.search);
    label.htmlFor = searchId;
    var search = element('input');
    search.type = 'search';
    search.id = searchId;
    search.autocomplete = 'off';
    search.setAttribute('data-library-search', '');
    var count = element('p', 'small muted');
    count.setAttribute('role', 'status');
    count.setAttribute('aria-live', 'polite');
    var results = element('ul', 'library-results');
    results.id = select.id + '-results';
    results.setAttribute('aria-label', labels.results);
    search.setAttribute('aria-controls', results.id);
    var selected = element('section', 'library-selected');
    selected.setAttribute('aria-label', labels.preview);
    selected.hidden = true;
    var more = element('button', 'quiet');
    more.type = 'button';
    more.hidden = true;
    more.setAttribute('data-library-more', '');
    enhancement.appendChild(label);
    enhancement.appendChild(search);
    enhancement.appendChild(count);
    enhancement.appendChild(results);
    enhancement.appendChild(more);
    enhancement.appendChild(selected);
    select.insertAdjacentElement('afterend', enhancement);
    var rendered = false;
    var limit = 20;
    var searchable = null;

    function showSelected() {
      selected.replaceChildren();
      var item = items.find(function (entry) { return entry.id === select.value; });
      selected.hidden = !item;
      if (item) {
        selected.appendChild(element('h3', '', labels.preview));
        selected.appendChild(preview(item, kind));
      }
      results.querySelectorAll('[data-library-choice]').forEach(function (button) {
        var active = button.getAttribute('data-library-choice') === select.value;
        button.textContent = active ? labels.selected : labels.choose;
        button.setAttribute('aria-pressed', String(active));
      });
    }

    function render() {
      if (!container.open) { return; }
      if (!searchable) { searchable = items.map(function (item) { return searchText(item, kind); }); }
      rendered = true;
      var words = search.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
      var matching = items.filter(function (item, index) {
        var text = searchable[index];
        return words.every(function (word) { return text.indexOf(word) !== -1; });
      });
      count.textContent = labels.results + ': ' + matching.length + ' / ' + items.length;
      results.replaceChildren();
      if (!matching.length) { results.appendChild(element('li', 'library-empty', labels.empty)); }
      matching.slice(0, limit).forEach(function (item) {
        var row = element('li', 'library-card');
        row.appendChild(preview(item, kind, kind === 'sets'));
        var choose = element('button', 'quiet', labels.choose);
        choose.type = 'button';
        choose.setAttribute('data-library-choice', item.id);
        choose.addEventListener('click', function () {
          select.value = item.id;
          select.dispatchEvent(new Event('change', { bubbles: true }));
        });
        row.appendChild(choose);
        results.appendChild(row);
      });
      more.hidden = matching.length <= limit;
      more.textContent = labels.more + ' (' + Math.min(limit, matching.length) + ' / ' + matching.length + ')';
      showSelected();
    }

    search.addEventListener('input', function () { limit = 20; render(); });
    more.addEventListener('click', function () { limit += 20; render(); });
    container.addEventListener('toggle', function (event) {
      if (event.target === container && container.open && !rendered) { render(); }
    });
    // Search and preview never replace editor text. The existing explicit POST
    // actions remain responsible for applying a set or individual selections.
    select.addEventListener('change', function () { if (container.open && rendered) { showSelected(); } });
    if (container.open) { render(); }
  });
}());
