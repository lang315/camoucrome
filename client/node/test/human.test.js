'use strict';
// human.js: click, hold and type on a patchright Page, against a fake page that records every call.
// Virtual clock: each recorded call carries the time the injected sleep has advanced to, so dwell, overlap and the
// "at most 2 keys down" rule are read from the timeline, not from the implementation.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const human = require('../human');
const P = require('../human_params');

const BOX = { x: 100, y: 200, width: 200, height: 40 };
const flat = { random: () => 0.99, gauss: () => 0 }; // every draw is the median: no rollover, pause or typo

class Boom extends Error {}

// failAt: throw Boom from the Nth sleep.
function fake(failAt) {
  const page = {
    t: 0, calls: [], sleeps: 0, pos: [0, 0],
    rec(name, ...args) { page.calls.push([page.t, name, args]); },
    sleep: async (ms) => {
      page.sleeps++;
      if (failAt !== undefined && page.sleeps >= failAt) throw new Boom('sleep failed');
      page.t += ms;
    },
    viewportSize: () => ({ width: 1280, height: 720 }),
    mouse: {
      move: async (x, y) => { page.pos = [x, y]; page.rec('move', x, y); },
      down: async () => page.rec('down', page.pos),
      up: async () => page.rec('up', page.pos),
    },
    keyboard: {
      down: async (k) => page.rec('kdown', k),
      up: async (k) => page.rec('kup', k),
      insertText: async (s) => page.rec('insert', s),
    },
    locator: (sel) => {
      const loc = {
        first: () => loc,
        scrollIntoViewIfNeeded: async () => page.rec('scroll', sel),
        boundingBox: async () => ({ ...BOX }),
        focus: async () => page.rec('focus', sel),
      };
      return loc;
    },
  };
  return page;
}

const names = (page, ...keep) => page.calls.filter(([, n]) => keep.includes(n)).map(([, n, a]) => [n, a[0]]);
const typed = (page, text, opts = {}) => human.type(page, '#f', text, { sleep: page.sleep, ...opts });
const keyEvents = (page) => page.calls.filter(([, n, a]) => (n === 'kdown' || n === 'kup') && a[0] !== 'Shift')
  .map(([t, n, a]) => [t, n, a[0]]);

function downCounts(page) {
  let n = 0; let worst = 0;
  for (const [, name, a] of page.calls) {
    if (name === 'kdown' && a[0] !== 'Shift') n++;
    else if (name === 'kup' && a[0] !== 'Shift') n--;
    worst = Math.max(worst, n);
  }
  return [worst, n];
}

function fieldValue(page) {
  let v = '';
  for (const [, n, a] of page.calls) {
    if (n === 'insert') v += a[0];
    else if (n === 'kdown') {
      const k = a[0];
      if (k === 'Backspace') v = [...v].slice(0, -1).join('');
      else if (k === 'Enter') v += '\n';
      else if (k === 'Tab') v += '\t';
      else if ([...k].length === 1) v += k;
    }
  }
  return v;
}

const sortedKeys = (page, name) => page.calls.filter(([, n]) => n === name).map(([, , a]) => a[0]).sort();

test('Hello, World! exact sequence', async () => {
  const page = fake();
  await human.type(page, '#f', 'Hello, World!', { rng: flat, sleep: page.sleep });
  const want = [['focus', '#f']];
  for (const ch of 'Hello, World!') {
    if (/[A-Z!]/.test(ch)) want.push(['kdown', 'Shift'], ['kdown', ch], ['kup', ch], ['kup', 'Shift']);
    else want.push(['kdown', ch], ['kup', ch]);
  }
  assert.deepEqual(names(page, 'focus', 'kdown', 'kup', 'insert'), want);
});

test('same seed, same trace', async () => {
  const a = fake(); const b = fake();
  await typed(a, 'The quick brown fox, Jumps!', { rng: human.makeRng(5) });
  await typed(b, 'The quick brown fox, Jumps!', { rng: human.makeRng(5) });
  assert.deepEqual(a.calls, b.calls);
});

test('every key has a positive dwell', async () => {
  const page = fake();
  await typed(page, 'dwell time matters, Really.', { rng: human.makeRng(1) });
  const downs = {}; let n = 0;
  for (const [t, name, key] of keyEvents(page)) {
    if (name === 'kdown') (downs[key] ||= []).push(t);
    else { const t0 = downs[key].shift(); assert.ok(t - t0 >= P.dwellMinMs - 1e-6, `${key} ${t - t0}`); n++; }
  }
  assert.ok(n > 20);
  assert.ok(Object.values(downs).every((v) => v.length === 0));
});

test('Shift brackets, consecutive shifted keys share one press', async () => {
  const page = fake();
  await typed(page, 'aBCd', { rng: flat });
  const seq = page.calls.filter(([, n]) => n === 'kdown' || n === 'kup').map(([t, n, a]) => [t, n, a[0]]);
  assert.deepEqual(seq.map(([, n, k]) => [n, k]), [['kdown', 'a'], ['kup', 'a'], ['kdown', 'Shift'], ['kdown', 'B'],
    ['kup', 'B'], ['kdown', 'C'], ['kup', 'C'], ['kup', 'Shift'], ['kdown', 'd'], ['kup', 'd']]);
  const at = (n, k) => seq.find(([, nn, kk]) => nn === n && kk === k)[0];
  assert.ok(at('kdown', 'B') - at('kdown', 'Shift') >= P.shiftLeadMedianMs - 1e-6);
  assert.ok(at('kup', 'Shift') > at('kup', 'C'));
});

test('off-layout rune is insertText without key events', async () => {
  const page = fake();
  await typed(page, 'aéb', { rng: flat });
  assert.deepEqual(names(page, 'kdown', 'insert'), [['kdown', 'a'], ['insert', 'é'], ['kdown', 'b']]);
});

test('CRLF is one Enter', async () => {
  const page = fake();
  await typed(page, 'a\r\nb', { rng: flat });
  assert.deepEqual(names(page, 'kdown'), [['kdown', 'a'], ['kdown', 'Enter'], ['kdown', 'b']]);
});

test('overlap rate matches the calibrated chance', async () => {
  const page = fake();
  const rnd = human.makeRng(11);
  let text = ''; let prev = '';
  while (text.length < 3000) { // no repeated letter: a physical key cannot go down twice
    const c = 'abcdefghijklmnopqrstuvwxyz'[Math.floor(rnd.random() * 26)];
    if (c !== prev) { text += c; prev = c; }
  }
  await typed(page, text, { rng: human.makeRng(3) });
  const order = keyEvents(page).map(([, n]) => n);
  let pairs = 0; let overlaps = 0;
  order.forEach((n, i) => { if (n === 'kdown' && i > 0) { pairs++; if (order[i - 1] === 'kdown') overlaps++; } });
  const rate = overlaps / pairs;
  assert.ok(Math.abs(rate - P.rolloverChance) < 0.04, `rate ${rate}`);
  assert.ok(rate > 0.05);
});

test('never three keys down, everything released', async () => {
  for (let seed = 0; seed < 20; seed++) {
    const page = fake();
    await typed(page, 'Rollover keys, Typed FAST; with: Shifted! pairs? (ok) '.repeat(4), { rng: human.makeRng(seed), typos: true });
    const [worst, left] = downCounts(page);
    assert.ok(worst <= 2, `seed ${seed} worst ${worst}`);
    assert.equal(left, 0);
    assert.deepEqual(sortedKeys(page, 'kup'), sortedKeys(page, 'kdown'));
  }
});

test('rollover keeps the next keyDown 10 ms after the previous keyDown', async () => {
  for (let seed = 0; seed < 10; seed++) {
    const page = fake();
    await typed(page, 'qwertyuiopasdfghjklzxcvbnm'.repeat(20), { rng: human.makeRng(seed) });
    const ds = keyEvents(page).filter(([, n]) => n === 'kdown').map(([t]) => t);
    for (let i = 1; i < ds.length; i++) assert.ok(ds[i] - ds[i - 1] >= 10 - 1e-6);
  }
});

test('typos are off by default: no Backspace', async () => {
  const page = fake();
  await typed(page, 'abcdefghijklmnopqrstuvwxyz '.repeat(30), { rng: human.makeRng(2) });
  assert.ok(!page.calls.some(([, n, a]) => n === 'kdown' && a[0] === 'Backspace'));
});

test('typos: final text exact, Backspace present', async () => {
  const text = 'The Quick brown fox, jumps over 13 lazy dogs! (really)\né and a tab\tend.\n';
  let bs = 0;
  for (let seed = 0; seed < 40; seed++) {
    const page = fake();
    await typed(page, text, { rng: human.makeRng(seed), typos: true });
    assert.equal(fieldValue(page), text, `seed ${seed}`);
    bs += names(page, 'kdown').filter(([, k]) => k === 'Backspace').length;
  }
  assert.ok(bs > 20);
});

test('Backspace is a real key with a dwell', async () => {
  const page = fake();
  await typed(page, 'abcdefghijklmnopqrstuvwxyz'.repeat(20), { rng: human.makeRng(4), typos: true });
  const ev = keyEvents(page).filter(([, , k]) => k === 'Backspace');
  assert.ok(ev.length > 0 && ev[0][1] === 'kdown');
  const d = ev.filter(([, n]) => n === 'kdown').map(([t]) => t);
  const u = ev.filter(([, n]) => n === 'kup').map(([t]) => t);
  assert.equal(d.length, u.length);
  d.forEach((t, i) => assert.ok(u[i] - t >= P.backspaceDwellMinMs - 1e-6));
});

test('a typo waits the notice delay before the first Backspace', async () => {
  const page = fake();
  await typed(page, 'abcdefghijklmnopqrstuvwxyz'.repeat(20), { rng: human.makeRng(4), typos: true });
  const ev = keyEvents(page);
  const i = ev.findIndex(([, n, k], j) => k === 'Backspace' && n === 'kdown' && ev[j - 1][2] !== 'Backspace' && ev[j - 1][1] === 'kup');
  assert.ok(i > 0, 'no first Backspace');
  assert.ok(ev[i][0] - ev[i - 1][0] >= P.typoNoticeMinMs - 1e-6);
});

test('releases everything on error', async () => {
  for (let failAt = 1; failAt < 12; failAt++) {
    const page = fake(failAt);
    await assert.rejects(typed(page, 'ABC def GHI', { rng: flat }), Boom);
    assert.deepEqual(sortedKeys(page, 'kup'), sortedKeys(page, 'kdown'), `failAt ${failAt}`);
  }
});

test('click: press point inside the inner 70%, settle, hold', async () => {
  const xs = new Set();
  let page;
  for (let seed = 0; seed < 200; seed++) {
    page = fake();
    await human.click(page, '#b', { rng: human.makeRng(seed), sleep: page.sleep });
    const moves = page.calls.filter(([, n]) => n === 'move');
    const down = page.calls.filter(([, n]) => n === 'down');
    const up = page.calls.filter(([, n]) => n === 'up');
    assert.equal(down.length, 1); assert.equal(up.length, 1);
    const [x, y] = moves.at(-1)[2];
    assert.deepEqual(down[0][2][0], [x, y]); assert.deepEqual(up[0][2][0], [x, y]);
    xs.add(x.toFixed(3));
    assert.ok(x >= BOX.x + 0.15 * BOX.width - 1e-9 && x <= BOX.x + 0.85 * BOX.width + 1e-9);
    assert.ok(y >= BOX.y + 0.15 * BOX.height - 1e-9 && y <= BOX.y + 0.85 * BOX.height + 1e-9);
    assert.ok(down[0][0] - moves.at(-1)[0] >= P.settleMinMs - 1e-6);
    const held = up[0][0] - down[0][0];
    assert.ok(held >= P.clickHoldMinMs - 1e-6 && held <= P.clickHoldMaxMs + 1e-6);
  }
  assert.ok(xs.size > 150);
  assert.ok(names(page, 'scroll').length > 0);
});

test('the first click seeds a first move, the second does not', async () => {
  const page = fake();
  await human.click(page, '#b', { rng: human.makeRng(1), sleep: page.sleep });
  const n1 = page.calls.filter(([, n]) => n === 'move').length;
  await human.click(page, '#b', { rng: human.makeRng(1), sleep: page.sleep });
  const n2 = page.calls.filter(([, n]) => n === 'move').length - n1;
  assert.deepEqual([n1, n2], [2, 1]);
});

test('hold: tremor while held, release at the last point', async () => {
  const page = fake();
  await human.hold(page, '#b', 1500, { rng: human.makeRng(9), sleep: page.sleep });
  assert.deepEqual(page.calls.filter(([, n]) => n === 'down' || n === 'up').map(([, n]) => n), ['down', 'up']);
  const [tdown, , [[px, py]]] = page.calls.find(([, n]) => n === 'down');
  const [tup, , [pup]] = page.calls.find(([, n]) => n === 'up');
  assert.ok(Math.abs(tup - tdown - 1500) < 1e-6);
  const held = page.calls.filter(([t, n]) => n === 'move' && t > tdown && t < tup).map(([, , a]) => a);
  assert.ok(held.length >= 3);
  for (const [x, y] of held) assert.ok(Math.abs(x - px) <= P.tremorPx + 1e-9 && Math.abs(y - py) <= P.tremorPx + 1e-9);
  assert.deepEqual(pup, held.at(-1));
});

test('hold releases the button on error', async () => {
  const page = fake();
  let n = 0;
  const sleeper = async (ms) => { if (++n === 3 && page.calls.some(([, k]) => k === 'down')) throw new Boom('x'); await page.sleep(ms); };
  await assert.rejects(human.hold(page, '#b', 5000, { rng: human.makeRng(9), sleep: sleeper }), Boom);
  assert.deepEqual(page.calls.filter(([, k]) => k === 'down' || k === 'up').map(([, k]) => k), ['down', 'up']);
});

test('index exports human', () => {
  assert.equal(require('..').human, human);
});
