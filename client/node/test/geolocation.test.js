'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const c = require('..');

const ctx = { on: () => {}, close: async () => {} };
const run = async (opts) => {
  let seen;
  const said = [];
  await c.launch({ launchPersistentContext: async (_dir, o) => { seen = o; return ctx; } }, '/x/chrome', { warn: (m) => said.push(m), ...opts });
  return { seen, said };
};
const both = { 'geolocation:latitude': 1.5, 'geolocation:longitude': 2.5 };

test('the geolocation permission is granted only with both coordinates', async () => {
  assert.deepEqual((await run({ config: both })).seen.permissions, ['geolocation']);
  assert.deepEqual((await run({ config: JSON.stringify(both) })).seen.permissions, ['geolocation']);
  for (const config of [{ 'geolocation:latitude': 1.5 }, { 'geolocation:longitude': 2.5 }, { a: 1 }]) {
    assert.equal((await run({ config })).seen.permissions, undefined);
  }
});

test('the permission merges with the callers list without a duplicate', async () => {
  assert.deepEqual((await run({ config: both, permissions: ['notifications'] })).seen.permissions, ['notifications', 'geolocation']);
  assert.deepEqual((await run({ config: both, permissions: ['geolocation', 'notifications'] })).seen.permissions, ['geolocation', 'notifications']);
  assert.deepEqual((await run({ config: { a: 1 }, permissions: ['notifications'] })).seen.permissions, ['notifications']);
});

test('a proxy without geoip warns; no proxy, or geoip given, does not', async () => {
  const words = 'a proxy without geoip: timezone, locale and geolocation are not checked against the exit IP';
  const proxy = { server: 'http://p.example:8080' };
  assert.deepEqual((await run({ config: { a: 1 }, proxy })).said, [words]);
  assert.deepEqual((await run({ config: { a: 1 } })).said, []);
  const withGeoip = await run({ config: { a: 1 }, proxy, geoip: '/db', exitIp: '192.0.2.5', python: 'camoucrome-no-such-python' });
  assert.ok(!withGeoip.said.includes(words));
});
