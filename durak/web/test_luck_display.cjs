// Execute the actual browser script; keep its initial fetch pending so these
// tests can exercise the display calculation without a server or a DOM library.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

function loadApp() {
  const context = vm.createContext({
    document: {
      getElementById: () => ({addEventListener() {}}),
      querySelectorAll: () => [],
    },
    fetch: () => new Promise(() => {}),
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'static/app.js'), 'utf8'), context);
  return context;
}

const app = loadApp();
const present = (total, model = 'chance-v1') => app.luckPresentation({model, total});

for (const model of ['chance-v1', 'chance-v2']) {
test('reference is fixed, sorted and includes each player symmetrically', () => {
  const reference = vm.runInContext(`luckReferences['${model}']`, app);
  assert.equal(reference.games, 200);
  assert.equal(reference.magnitudes.length, 200);
  assert.ok(Object.isFrozen(reference) && Object.isFrozen(reference.magnitudes));
  assert.ok(reference.magnitudes.every((v, i, a) => v >= 0 && (!i || v >= a[i - 1])));
  assert.equal(present(0, model).percentile, 50);
  let previous = 0;
  for (let i = -100; i <= 100; i++) {
    const score = i / 100;
    const p = present(score, model).percentile;
    assert.ok(p >= previous);
    assert.ok(Math.abs(p + present(-score, model).percentile - 100) < 1e-12);
    previous = p;
  }
});

test('ties receive midpoint ranks', () => {
  const reference = vm.runInContext(`luckReferences['${model}']`, app);
  const values = reference.magnitudes.flatMap(v => [-v, v]).sort((a, b) => a - b);
  for (const value of new Set(values)) {
    const first = values.indexOf(value);
    const after = values.lastIndexOf(value) + 1;
    const expected = 100 * ((first + after) / 2 + 0.5) / (values.length + 1);
    assert.ok(Math.abs(present(value, model).percentile - expected) < 1e-12);
  }
});
}

test('the audited last draw is favourable to Dummy under the recalibrated model', () => {
  const display = present(0.29687140584490673, 'chance-v2');
  assert.ok(display.percentile > 90);
  assert.match(display.verdict, /^Very lucky/);
  assert.equal(display.reference, 'chance-v2-sr3-dummy-202614000-100');
});

test('the six-trump game is very lucky, around the 95th percentile', () => {
  const report = Object.freeze({model: 'chance-v1', total: 0.2737591034243385});
  const display = app.luckPresentation(report);
  assert.ok(display.percentile > 95 && display.percentile < 96);
  assert.equal(display.verdict, 'Very lucky — top 5%');
  assert.equal(report.total, 0.2737591034243385);
  assert.equal(present(-report.total).verdict, 'Very unlucky — bottom 5%');
});

test('extreme finite scores never pretend to be zero or perfect luck', () => {
  const lucky = present(1000), unlucky = present(-1000);
  assert.ok(lucky.percentile < 100 && lucky.percentile > 99);
  assert.ok(unlucky.percentile > 0 && unlucky.percentile < 1);
  assert.equal(lucky.verdict, 'Very lucky — top 1%');
  assert.equal(unlucky.verdict, 'Very unlucky — bottom 1%');
  assert.equal(present(0).verdict, 'Fairly even — near the middle');
  assert.ok(present(0.3795).percentile > 99); // Six high opening trumps.
});

test('missing, nonfinite and uncalibrated models do not get a guessed percentile', () => {
  for (const total of [NaN, Infinity, -Infinity, '0.2', null, undefined]) {
    assert.equal(present(total), null);
  }
  assert.equal(app.luckPresentation(null), null);
  assert.equal(app.luckPresentation({model: 'chance-v3', total: 0.2}), null);
  assert.equal(app.luckPresentation({model: '__proto__', total: 0.2}), null);
});

test('actual renderer uses percentiles, preserves raw luck and hides it during play', () => {
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.attributes = {}; this.style = {setProperty() {}}; }
    append(...elements) { this.children.push(...elements); }
    replaceChildren() { this.children = []; }
    setAttribute(key, value) { this.attributes[key] = value; }
  }
  const panels = {'luck-result': new Element('section'), 'luck-sidebar': new Element('section')};
  const context = loadApp();
  context.document.getElementById = id => panels[id];
  context.document.createElement = tag => new Element(tag);
  const luck = {model: 'chance-v1', total: 0.2737591034243385, opening: 0.19175,
    refills: 0.08200910342433854, components: {trumps: 0.229, ranks: -0.007, answers: 0.123, pairs: -0.023, suits: -0.048}};
  const original = JSON.stringify(luck);
  context.fixture = {game_over: true, luck, winner: 'you', revision: 10};
  vm.runInContext('state = fixture; renderLuck()', context);
  for (const panel of Object.values(panels)) {
    assert.equal(panel.hidden, false);
    const meter = panel.children.find(c => c.tag === 'meter');
    assert.equal(meter.min, 0);
    assert.equal(meter.max, 100);
    assert.ok(meter.value > 95 && meter.value < 96);
    assert.match(meter.attributes['aria-valuetext'], /top 5%.*reference/);
    assert.ok(panel.children.some(c => c.textContent === 'Very lucky — top 5%'));
  }
  assert.equal(JSON.stringify(luck), original);
  context.fixture.luck = {...luck, total: -luck.total};
  context.fixture.revision++;
  vm.runInContext('renderLuck()', context);
  assert.ok(panels['luck-result'].children.some(c => c.textContent === 'Won against the cards'));
  context.fixture.luck = {...luck, model: 'chance-v2', total: 0.29687140584490673,
    components: {...luck.components, endgame: 0.35714285714285715}};
  context.fixture.revision++;
  vm.runInContext('renderLuck()', context);
  const details = panels['luck-result'].children.find(c => c.tag === 'details');
  const rows = details.children.find(c => c.tag === 'dl');
  assert.ok(rows.children.some(c => c.textContent === 'Endgame draws'));
  assert.match(details.children.find(c => c.tag === 'p').textContent, /who attacks next/);
  context.fixture.game_over = false;
  vm.runInContext('renderLuck()', context);
  assert.ok(panels['luck-result'].hidden && panels['luck-sidebar'].hidden);
});
