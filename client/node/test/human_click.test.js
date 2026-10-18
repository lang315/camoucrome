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

function fake(geos) {
  const log = [];
  const q = [...geos];
  const page = { mouse: { move: async (x, y) => log.push(['move', Math.round(x), Math.round(y)]),
    wheel: async (dx, dy) => log.push(['wheel', dx, dy]) } };
  const target = { evaluate: async () => (q.length > 1 ? q.shift() : q[0]) };
  const click = async (o) => log.push(['click', o]);
  return { log, page, target, click };
}

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

test('wheels into view, then trial and click with scroll none', async () => {
  const f = fake([GEO, GEO, { ...GEO, y: 200 }]);
  await hc.act(f.target, f.page, { timeout: 9999 }, { scale: 1, windows: true }, () => 0.4, noSleep, f.click);
  assert.equal(f.log[0][0], 'move');
  assert.ok(f.log.some((e) => e[0] === 'wheel'));
  const clicks = f.log.filter((e) => e[0] === 'click');
  assert.equal(clicks.length, 2);
  assert.equal(clicks[0][1].trial, true);
  // Ruling 2: the trial never inherits the caller's timeout.
  assert.equal(clicks[0][1].timeout, 2000);
  assert.equal(clicks[1][1].timeout, 9999);
  assert.equal(clicks[1][1].scroll, 'none');
  assert.ok('position' in clicks[1][1] && !('delay' in clicks[1][1]));
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
