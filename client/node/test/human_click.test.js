'use strict';
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { test } = require('node:test');
const m = require('../human_math');
const hc = require('../human_click');
const c = require('..');

const VEC = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', '..', 'settings', 'human_click_vectors.json')));
const stream = (xs) => { const a = [...xs]; return () => a.shift(); };
const close = (a, b, tol = 1e-9) => Math.abs(a - b) <= tol * Math.max(1, Math.abs(b));
const GEO = { x: 100, y: 900, w: 120, h: 40, n: 1, bl: 1, bt: 1, t: false, vw: 1280, vh: 720, scroller: 'document' };
const noSleep = async () => {};

function fake(geos, errors = []) {
  const log = [];
  const q = [...geos];
  const errs = [...errors];
  let n = 0;
  const page = { mouse: { move: async (x, y) => log.push(['move', Math.round(x), Math.round(y)]),
    wheel: async (dx, dy) => log.push(['wheel', dx, dy]) } };
  const target = { evaluate: async () => (q.length > 1 ? q.shift() : q[0]) };
  const click = async (o) => {
    log.push(['click', o]);
    n += 1;
    if (errs.length) throw errs.shift();
    return `result-${n}`;
  };
  return { log, page, target, click };
}


const timeoutError = () => Object.assign(new Error('Timeout 2000ms exceeded'), { name: 'TimeoutError' });

test('vectors match the Python reference', () => {
  for (const [x, y] of VEC.splitmix64) assert.equal(m.splitmix64(BigInt('0x' + x)).toString(16).padStart(16, '0'), y.toLowerCase().padStart(16, '0'));
  for (const v of VEC.profile_scale) assert.ok(close(m.profileScale(v.seed, v.salt), v.scale, 1e-12));
  for (const v of VEC.sample_knots) assert.ok(close(m.sampleKnots(v.knots, v.u), v.value, 1e-12));
  for (const v of VEC.edge_entry) { const p = m.edgeEntry(v.w, v.h, ...v.u); assert.ok(close(p[0], v.point[0]) && close(p[1], v.point[1])); }
  for (const v of VEC.click_position) {
    const got = m.clickPosition(v.geo, v.last, v.model, v.scale, stream(v.rand));
    assert.equal(got === null, v.position === null);
    if (got) assert.ok(close(got[0], v.position[0]) && close(got[1], v.position[1]));
  }
  for (const v of VEC.next_burst) {
    const got = m.nextBurst(v.geo, v.landing, v.burst, v.pause, stream(v.rand));
    assert.equal(got === null, v.out === null);
    if (got) assert.ok(got[0] === v.out[0] && close(got[1], v.out[1]));
  }
});

// Ruling 1: humanize:seed counts only as a uint32; 0 is valid, bool is not.
test('humanize:seed is a uint32 or absent', () => {
  assert.notEqual(m.profileScale(0, 'offset'), 1.0);
  assert.equal(hc.seedOf({}), null);
  assert.equal(hc.seedOf({ 'humanize:seed': 0 }), 0);
  assert.equal(hc.seedOf({ 'humanize:seed': 4294967295 }), 4294967295);
  for (const bad of [-1, 2 ** 32, 1.5, '5', true]) {
    assert.equal(hc.seedOf({ 'humanize:seed': bad }), null);
    assert.equal(m.profileScale(hc.seedOf({ 'humanize:seed': bad }), 'offset'), 1.0);
  }
});

test('caller position passes through', async () => {
  const f = fake([GEO]);
  await hc.act(f.target, f.page, { position: { x: 1, y: 2 } }, null, () => 0.5, noSleep, f.click);
  assert.deepEqual(f.log, [['click', { position: { x: 1, y: 2 } }]]);
});

test('wheels into view, then clicks once with scroll none', async () => {
  const f = fake([GEO, GEO, { ...GEO, y: 200 }]);
  const result = await hc.act(f.target, f.page, { timeout: 9999 }, { scale: 1, windows: true }, () => 0.4, noSleep, f.click);
  assert.equal(f.log[0][0], 'move');
  assert.ok(f.log.some((e) => e[0] === 'wheel'));
  const clicks = f.log.filter((e) => e[0] === 'click');
  assert.equal(clicks.length, 1);
  assert.equal('trial' in clicks[0][1], false);
  // the first attempt never inherits the caller's timeout.
  assert.equal(clicks[0][1].timeout, 2000);
  assert.equal(clicks[0][1].scroll, 'none');
  assert.ok('position' in clicks[0][1] && !('delay' in clicks[0][1]));
  assert.equal(result, 'result-1');
});

test('one timeout earns one corrective burst and one retry', async () => {
  const f = fake([{ ...GEO, y: 100 }], [timeoutError()]);
  const result = await hc.act(f.target, f.page, {}, null, () => 0.5, noSleep, f.click);
  assert.deepEqual(f.log.map((e) => e[0]), ['click', 'wheel', 'click']);
  const clicks = f.log.filter((e) => e[0] === 'click').map((e) => e[1]);
  assert.deepEqual(clicks.map((o) => o.timeout), [2000, 2000]);
  assert.equal(result, 'result-2');
});

test('two timeouts fall back to the stock click', async () => {
  const f = fake([{ ...GEO, y: 100 }], [timeoutError(), timeoutError()]);
  await hc.act(f.target, f.page, { timeout: 5000 }, null, () => 0.5, noSleep, f.click);
  const clicks = f.log.filter((e) => e[0] === 'click').map((e) => e[1]);
  assert.equal(clicks.length, 3);
  assert.deepEqual(clicks.slice(0, 2).map((o) => o.timeout), [2000, 2000]);
  assert.ok(clicks.slice(0, 2).every((o) => !('trial' in o)));
  assert.deepEqual(clicks[2], { timeout: 5000 });
});

test('a non-timeout error is not retried or fallen back', async () => {
  const f = fake([{ ...GEO, y: 100 }], [new Error('Target closed')]);
  await assert.rejects(hc.act(f.target, f.page, {}, null, () => 0.5, noSleep, f.click), /Target closed/);
  assert.deepEqual(f.log.map((e) => e[0]), ['click']);
});

test('null geometry and nested scroller fall back unchanged', async () => {
  for (const g of [null, { ...GEO, scroller: 'nested' }]) {
    const f = fake([g]);
    await hc.act(f.target, f.page, { timeout: 1234 }, null, () => 0.5, noSleep, f.click);
    assert.deepEqual(f.log, [['click', { timeout: 1234 }]]);
  }
});

test('no progress falls back after two bursts', async () => {
  const f = fake([GEO]);
  await hc.act(f.target, f.page, {}, { scale: 1, windows: true }, () => 0.4, noSleep, f.click);
  assert.equal(f.log.filter((e) => e[0] === 'wheel').length, 2);
  assert.deepEqual(f.log.at(-1), ['click', {}]);
});

test('wheel continues past first visibility to the landing depth', async () => {
  // The final top must sit at the landing depth, not near the bottom of the
  // viewport, where the target first becomes fully visible.
  const log = [];
  const geo = { ...GEO, y: 3000, h: 40 };
  const tops = [];
  const page = { mouse: {
    move: async () => {},
    wheel: async (dx, dy) => { log.push(['wheel', dx, dy]); geo.y -= dy; tops.push(geo.y); },
  } };
  const target = { evaluate: async () => ({ ...geo }) };
  const click = async (o) => { log.push(['click', o]); return 'result-1'; };
  await hc.act(target, page, {}, { scale: 1, windows: true }, () => 0, noSleep, click);
  const first = tops.findIndex((y) => y >= 0 && y + geo.h <= geo.vh);
  assert.ok(first >= 0 && first < tops.length - 1, `stopped at the first fully visible position: ${tops}`);
  assert.ok(Math.abs(geo.y - 0.2 * geo.vh) < 100, `final top ${geo.y}`);
});

// The shipped landing knots top out at 0.2891, so a high rand cannot clamp
// L; pin the knots to the 0.95 the clamped-goal defect needs.
function pinnedLanding(fn) {
  const table = require('../click_tables');
  const saved = table.landing.slice();
  table.landing.fill(0.95);
  return Promise.resolve().then(fn).finally(() => table.landing.splice(0, saved.length, ...saved));
}

test('a clamped landing arrives within one notch', () => pinnedLanding(async () => {
  // L clamps to vh - h, so a notch cannot put a visible target inside a
  // 50 px window; it must still arrive, not oscillate to the notch budget.
  const log = [];
  const geo = { ...GEO, y: 1200 };
  const page = { mouse: {
    move: async () => {},
    wheel: async (dx, dy) => { log.push(['wheel', dx, dy]); geo.y -= dy; },
  } };
  const target = { evaluate: async () => ({ ...geo }) };
  const click = async (o) => { log.push(['click', o]); return 'result-1'; };
  await hc.act(target, page, {}, { scale: 1, windows: true }, () => 0.5, noSleep, click);
  const goal = Math.min(0.95 * geo.vh, geo.vh - geo.h);
  assert.ok(geo.y >= 0 && geo.y + geo.h <= geo.vh, `not visible: ${geo.y}`);
  assert.ok(Math.abs(geo.y - goal) < 100, `final top ${geo.y}, want within 100 of ${goal}`);
  const notches = log.filter((e) => e[0] === 'wheel').reduce((s, e) => s + Math.abs(e[2]) / 100, 0);
  assert.ok(notches < 10, `${notches} notches`);
  const clicks = log.filter((e) => e[0] === 'click').map((e) => e[1]);
  assert.equal(clicks.length, 1);
  assert.equal(clicks[0].scroll, 'none');
  assert.ok('position' in clicks[0]);
}));

test('a visible target at the page end is clicked, not fallen back', () => pinnedLanding(async () => {
  // The target cannot be brought to L=680; held visible at 380, it is
  // clicked where the page end left it, not handed to the stock click.
  const log = [];
  const geo = { ...GEO, y: -50 };
  const page = { mouse: {
    move: async () => {},
    wheel: async (dx, dy) => { log.push(['wheel', dx, dy]); geo.y = Math.min(geo.y - dy, 380); },
  } };
  const target = { evaluate: async () => ({ ...geo }) };
  const click = async (o) => { log.push(['click', o]); return 'result-1'; };
  await hc.act(target, page, {}, { scale: 1, windows: true }, () => 0.5, noSleep, click);
  assert.equal(geo.y, 380);
  const clicks = log.filter((e) => e[0] === 'click').map((e) => e[1]);
  assert.equal(clicks.length, 1);
  assert.equal(clicks[0].scroll, 'none');
  assert.ok('position' in clicks[0]);
}));

// Ruling 3: B counts the human path only; a pass-through or a missing context
// leaves the stock Frame.click handling the call untouched.
test('the B wrapper counts only the human path', async () => {
  const calls = [];
  const frameProto = { click: async function (selector, options) { calls.push([selector, options]); } };
  const ctx = {};
  const page = { mainFrame: () => Object.create(frameProto), context: () => ctx,
    mouse: { move: async () => {}, wheel: async () => {} } };
  ctx.pages = () => [page];
  const target = { evaluate: async () => null };
  const frame = Object.create(frameProto);
  frame.page = () => page;
  frame.locator = () => ({ first: () => target });
  await hc.install(ctx, { effectiveKeys: (config) => config, claimedOs: () => 'Linux' }, {}, undefined);
  const before = hc.wrapperHits();
  await frame.click('#a', { position: { x: 1, y: 2 } });
  assert.equal(hc.wrapperHits(), before);
  await frame.click('#b', {});
  assert.equal(hc.wrapperHits(), before + 1);
  assert.deepEqual(calls, [['#a', { position: { x: 1, y: 2 } }], ['#b', {}]]);
});

// B acts only for contexts launch() created with humanClick: true. The wrapper
// lives on the shared Frame.prototype, so an unflagged context (installState
// only) must still go straight to the stock click.
test('the B wrapper leaves contexts launched without the flag on the stock click', async () => {
  const calls = [];
  const frameProto = { click: async function (selector, options) { calls.push([selector, options]); } };
  const makeCtx = () => {
    let evaluated = 0;
    const target = { evaluate: async () => { evaluated += 1; return null; } };
    const ctx = {};
    const page = { mainFrame: () => Object.create(frameProto), context: () => ctx,
      mouse: { move: async () => {}, wheel: async () => {} } };
    const frame = Object.create(frameProto);
    frame.page = () => page;
    // Only the human path resolves a locator and reads geometry.
    frame.locator = () => { calls.push(['locator']); return { first: () => target }; };
    ctx.pages = () => [page];
    return { ctx, frame, calls: () => evaluated };
  };
  const flagged = makeCtx();
  const plain = makeCtx();
  const helpers = { effectiveKeys: (config) => config, claimedOs: () => 'Linux' };
  await hc.install(flagged.ctx, helpers, {}, undefined);
  hc.installState(plain.ctx, helpers, {}, undefined);
  const before = hc.wrapperHits();
  await plain.frame.click('#plain', {});
  assert.equal(hc.wrapperHits(), before);
  assert.equal(plain.calls(), 0);
  assert.deepEqual(calls, [['#plain', {}]]);
  await flagged.frame.click('#flagged', {});
  assert.equal(hc.wrapperHits(), before + 1);
  assert.equal(flagged.calls(), 1);
  assert.deepEqual(calls.at(-1), ['#flagged', {}]);
});

test('launch refuses humanClick without humanize:enabled', async () => {
  for (const config of [{}, { 'humanize:enabled': false }]) {
    await assert.rejects(c.launch({}, '/x', { config, humanClick: true }), /humanize:enabled/);
  }
});

// --- round 2: delivery, corrective notch, tall targets ----------------------

const driverTimeout = (message) =>
  Object.assign(new Error(message), { name: 'TimeoutError' });
const DELIVERED = 'Timeout 2000ms exceeded.\n  - <header> intercepts pointer events\n'
  + '  - retrying click action\n  - performing click action';
const NOT_DELIVERED = 'Timeout 2000ms exceeded.\n  - <header> intercepts pointer events\n'
  + '  - retrying click action';
const PERFORMING_BEFORE_RETRY = 'Timeout 2000ms exceeded.\n  - performing click action\n'
  + '  - <header> intercepts pointer events\n  - retrying click action\n  - waiting for element to be visible';

test('a timeout after delivery started is not retried', async () => {
  const f = fake([{ ...GEO, y: 100 }], [driverTimeout(DELIVERED)]);
  await assert.rejects(hc.act(f.target, f.page, {}, null, () => 0.5, noSleep, f.click),
    /Timeout 2000ms exceeded/);
  assert.deepEqual(f.log.map((e) => e[0]), ['click']);
});

test('a timeout before delivery still retries', async () => {
  const f = fake([{ ...GEO, y: 100 }], [driverTimeout(NOT_DELIVERED)]);
  const result = await hc.act(f.target, f.page, {}, null, () => 0.5, noSleep, f.click);
  assert.deepEqual(f.log.map((e) => e[0]), ['click', 'wheel', 'click']);
  assert.equal(result, 'result-2');
});

// An earlier 'performing' line (before the last retry) means the press was not
// dispatched for the attempt that timed out: retry.
test('performing before the last retry is not delivery', async () => {
  const f = fake([{ ...GEO, y: 100 }], [driverTimeout(PERFORMING_BEFORE_RETRY)]);
  const result = await hc.act(f.target, f.page, {}, null, () => 0.5, noSleep, f.click);
  assert.deepEqual(f.log.map((e) => e[0]), ['click', 'wheel', 'click']);
  assert.equal(result, 'result-2');
});

test('the corrective notch moves away from the cover', async () => {
  for (const [y, delta] of [[100, -100], [600, 100]]) {
    const f = fake([{ ...GEO, y }], [driverTimeout(NOT_DELIVERED)]);
    await hc.act(f.target, f.page, {}, null, () => 0.5, noSleep, f.click);
    assert.deepEqual(f.log.filter((e) => e[0] === 'wheel'), [['wheel', 0, delta]]);
  }
});

test('the second attempt records the point after the corrective notch', async () => {
  for (const [y, direction] of [[100, -1], [600, 1]]) {
    const f = fake([{ ...GEO, y }], [driverTimeout(NOT_DELIVERED)]);
    await hc.act(f.target, f.page, {}, null, () => 0.5, noSleep, f.click);
    const pos = f.log.filter((e) => e[0] === 'click')[1][1].position;
    assert.deepEqual(hc.lastPoint(f.page),
      [GEO.x + GEO.bl + pos.x, y + GEO.bt + pos.y - 100 * direction]);
  }
});

test('a bouncing tall target stops at the stuck limit', async () => {
  const log = [];
  let i = 0;
  const ys = [70, -30];
  const page = { mouse: { move: async () => {}, wheel: async (dx, dy) => log.push(['wheel', dx, dy]) } };
  const target = { evaluate: async () => ({ ...GEO, y: ys[i++ % 2], h: 700 }) };
  const click = async (o) => { log.push(['click', o]); return 'result'; };
  await hc.act(target, page, {}, { scale: 1, windows: true }, () => 0.5, noSleep, click);
  const wheels = log.filter((e) => e[0] === 'wheel');
  assert.ok(wheels.length > 0 && wheels.length <= 4, `${wheels.length} wheels`);
  assert.deepEqual(log.at(-1), ['click', {}]);  // the stock fallback
});
