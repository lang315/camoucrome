'use strict';
// pinCpuCores (C3): the process that spawns Chrome is pinned to N CPUs for the launch call, then restored.
// The affinity calls are replaced: this Mac has no affinity API, so no real pin is read back here.
const assert = require('node:assert/strict');
const { test, beforeEach, afterEach } = require('node:test');
const c = require('..');
const pin = require('../pin');

const ALLOWED = new Set([0, 1, 2, 3, 4, 5, 6, 7]);
const real = { ...pin.io };
let log;
let state;

beforeEach(() => {
  log = [];
  state = { mask: new Set(ALLOWED), fail: null };
  pin.io.get = () => new Set(state.mask);
  pin.io.set = (pid, cpus) => {
    if (state.fail) throw new Error(state.fail);
    if (state.failAfter !== undefined && log.length >= state.failAfter) throw new Error('restore denied');
    log.push([pid, new Set(cpus)]);
    state.mask = new Set(cpus);
  };
});
afterEach(() => Object.assign(pin.io, real));

const ctx = { on() {}, close: async () => {} };
const run = (n, chromium, opts = {}) =>
  c.launch(chromium, '/x/chrome', { config: n === undefined ? {} : { 'navigator.hardwareConcurrency': n }, ...opts });

test('pins this process to n of the allowed CPUs for the launch call, then restores', async () => {
  let during;
  await run(4, { launchPersistentContext: async () => { during = new Set(state.mask); return ctx; } });
  assert.equal(during.size, 4);
  assert.ok([...during].every((x) => ALLOWED.has(x)));
  assert.deepEqual(log, [[process.pid, during], [process.pid, ALLOWED]]);
});

for (const n of [8, 12]) {
  test(`no pin when the claim (${n}) reaches the allowed CPUs`, async () => {
    await run(n, { launchPersistentContext: async () => ctx });
    assert.deepEqual(log, []);
  });
}

test('no pin when disabled or when there is no claim', async () => {
  await run(2, { launchPersistentContext: async () => ctx }, { pinCpuCores: false });
  await run(undefined, { launchPersistentContext: async () => ctx });
  assert.deepEqual(log, []);
});

test('the mask is restored when the launch throws', async () => {
  await assert.rejects(run(2, { launchPersistentContext: async () => { throw new Error('no chrome'); } }), /no chrome/);
  assert.equal(log.length, 2);
  assert.deepEqual(log[1], [process.pid, ALLOWED]);
});

test('a pin that cannot be set throws with the pid and the error, and does not launch', async () => {
  state.fail = 'EPERM nope';
  await assert.rejects(
    run(2, { launchPersistentContext: async () => assert.fail('must not launch') }),
    new RegExp(`${process.pid}.*EPERM nope`));
});

test('overlapping launches are serialised: each restores what it pinned', async () => {
  const order = [];
  const slow = (name) => ({ launchPersistentContext: async () => {
    order.push(`start ${name}`);
    await new Promise((r) => setTimeout(r, 20));
    order.push(`end ${name}`);
    return ctx;
  } });
  await Promise.all([run(2, slow('a')), run(3, slow('b'))]);
  assert.deepEqual(order, ['start a', 'end a', 'start b', 'end b']);
  assert.deepEqual(state.mask, ALLOWED);
});

test('a restore that fails after a good launch closes the browser, then throws', async () => {
  let closed = 0;
  const ok = { on() {}, close: async () => { closed++; } };
  await assert.rejects(run(2, { launchPersistentContext: async () => { state.failAfter = 1; return ok; } }), /cannot restore/);
  assert.equal(closed, 1);
});

test('a pin that fails part-way puts the allowed mask back', async () => {
  const sets = [];
  pin.io.set = (pid, cpus) => { sets.push(new Set(cpus)); if (sets.length === 1) throw new Error('half'); };
  await assert.rejects(run(2, { launchPersistentContext: async () => assert.fail('must not launch') }), /half/);
  assert.equal(sets.length, 2);
  assert.deepEqual(sets[1], ALLOWED);
});

test('CPU lists are not limited to 64 CPUs', () => {
  assert.deepEqual([...pin.fromList('0-1,8,70-71')], [0, 1, 8, 70, 71]);
  assert.equal(pin.toList(new Set([70, 0, 8])), '0,8,70');
});
