'use strict';
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { test } = require('node:test');
const c = require('..');

const CONTRACT = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', '..', 'settings', 'launcher.json')));
const camel = (s) => s.replace(/_([a-z])/g, (_, ch) => ch.toUpperCase()).replace('extraHttpHeaders', 'extraHTTPHeaders');
const L = CONTRACT.launch;

test('forbidden options match the contract (snake -> Playwright camelCase)', () => {
  assert.deepEqual(new Set(CONTRACT.forbidden_context_options.options.map(camel)), c.FORBIDDEN_OPTIONS);
});

test('args match the contract', () => {
  const pipe = ['--remote-debugging-pipe'];
  assert.deepEqual(c.buildArgs({ headless: false }), [...L.base_args, ...pipe]);
  assert.deepEqual(c.buildArgs(), [...L.base_args, L.headless_arg, ...pipe]);
  assert.deepEqual(
    c.buildArgs({ headless: false, userDataDir: '/p', window: [1920, 1040], dpr: 1.25,
      acceptLang: 'fr-FR,fr', extensions: ['/e1', '/e2'], spkiList: ['AAA=', 'BBB='] }),
    [...L.base_args, ...pipe, '--user-data-dir=/p',
      L.window_size_arg.replace('{width}', '1920').replace('{height}', '1040'),
      L.dpr_arg.replace('{dpr}', '1.25'),
      L.accept_lang_arg.replace('{languages}', 'fr-FR,fr'),
      ...L.extension_args.map((a) => a.replace('{paths}', '/e1,/e2')),
      L.spki_arg.replace('{hashes}', 'AAA=,BBB=')]);
  assert.equal(L.ignore_default_args, true);
});

test('env drops stale CAMOU vars and sets the transport', () => {
  assert.deepEqual(
    c.buildEnv({ config: { 'screen.width': 1 }, preset: '{"os":"Windows"}', strict: true },
      { CAMOU_CONFIG_1: 'stale', PATH: '/bin' }),
    { PATH: '/bin', CAMOU_CONFIG: '{"screen.width":1}', CAMOU_PRESET: '{"os":"Windows"}', CAMOU_CONFIG_STRICT: '1' });
});

test('accept-lang follows the config', () => {
  assert.equal(c.acceptLangOf({ 'navigator.languages': ['fr-FR', 'fr'] }), 'fr-FR,fr');
  assert.equal(c.acceptLangOf('{"locale:tag":"de-DE"}'), 'de-DE');
  assert.equal(c.acceptLangOf({ 'screen.width': 1 }), null);
});

test('per-instance seeds match the contract and are non-zero uint32', () => {
  assert.deepEqual(c.SEED_KEYS, CONTRACT.per_instance_seeds.keys);
  const cfg = c.perInstanceConfig();
  for (const k of c.SEED_KEYS) assert.ok(cfg[k] >= 1 && cfg[k] <= 0xffffffff, k);
});

test('launch refuses forbidden options and uses a persistent context without viewport emulation', async () => {
  const calls = [];
  const chromium = { launchPersistentContext: async (dir, opts) => { calls.push([dir, opts]); return 'ctx'; } };
  await assert.rejects(c.launch(chromium, '/x/chrome', { timezoneId: 'UTC' }), /timezoneId/);
  assert.equal(await c.launch(chromium, '/x/chrome', { config: { a: 1 }, userDataDir: '/tmp/p', window: [800, 600] }), 'ctx');
  const [dir, opts] = calls[0];
  assert.equal(dir, '/tmp/p');
  assert.equal(opts.viewport, null);
  assert.equal(opts.ignoreDefaultArgs, true);
  assert.equal(opts.env.CAMOU_CONFIG, '{"a":1}');
  assert.deepEqual(opts.args, ['--no-first-run', '--no-default-browser-check', '--headless=new',
    '--remote-debugging-pipe', '--user-data-dir=/tmp/p', '--window-size=800,600']);
});
