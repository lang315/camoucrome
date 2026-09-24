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

test('fontconfig follows the claimed OS and the contract', () => {
  assert.deepEqual(c.FONTCONFIG_FILES, L.fontconfig.files);
  assert.equal(L.fontconfig.env, 'FONTCONFIG_FILE');
  const root = fs.mkdtempSync(path.join(require('os').tmpdir(), 'camou-fc-'));
  fs.mkdirSync(path.join(root, 'fonts'));
  fs.mkdirSync(path.join(root, 'settings', 'fontconfig'), { recursive: true });
  fs.writeFileSync(path.join(root, 'settings', 'fontconfig', 'windows.conf'), '<fontconfig/>');
  fs.writeFileSync(path.join(root, 'settings', 'fontconfig', 'macos.conf'), '<fontconfig/>');
  const want = path.join(root, 'settings', 'fontconfig', 'windows.conf');
  assert.equal(c.fontconfigFor({ config: { 'ua:platform': 'Windows' }, fontsDir: path.join(root, 'fonts') }), want);
  assert.equal(c.fontconfigFor({ config: { 'ua:platform': 'Linux' }, fontsDir: path.join(root, 'fonts') }), null);
  assert.ok(c.fontconfigFor({ preset: { os: 'macOS' }, fontsDir: path.join(root, 'fonts') }).endsWith('settings/fontconfig/macos.conf'));
  fs.writeFileSync(path.join(root, 'chrome'), '');
  assert.equal(c.fontconfigFor({ config: { 'ua:platform': 'Windows' }, executablePath: path.join(root, 'chrome') }), want);
  assert.equal(c.buildEnv({ fontconfig: want }, {}).FONTCONFIG_FILE, want);
  assert.equal('FONTCONFIG_FILE' in c.buildEnv({}, {}), false);
});

test('a large config and preset are chunked into numbered env strings, never splitting a code point', () => {
  const big = { 'fonts:local': Array(700).fill('x'.repeat(100)) };
  const env = c.buildEnv({ config: big, preset: { fonts: Array(700).fill('x'.repeat(100)) } }, {});
  assert.equal('CAMOU_CONFIG' in env || 'CAMOU_PRESET' in env, false);
  assert.equal('CAMOU_CONFIG_4' in env, false);
  assert.deepEqual(JSON.parse(env.CAMOU_CONFIG_1 + env.CAMOU_CONFIG_2 + env.CAMOU_CONFIG_3), big);
  assert.ok(env.CAMOU_PRESET_3);
  const raw = `{"k":"${'a'.repeat(L.env.config_chunk_chars - 7)}${'😀'.repeat(20000)}"}`;
  const env2 = c.buildEnv({ config: raw }, {});
  const parts = Object.keys(env2).sort((a, b) => a.length - b.length || a.localeCompare(b)).map((k) => env2[k]);
  for (const p of parts) assert.ok(!/[\uD800-\uDBFF]$|^[\uDC00-\uDFFF]/.test(p), 'a chunk splits a surrogate pair');
  assert.equal(parts.join(''), raw);
});

test('accept-lang follows the preset locale under the config; bad shapes are rejected', () => {
  assert.equal(c.acceptLangOf(null, { locale: 'fr-FR' }), 'fr-FR,fr');
  assert.equal(c.acceptLangOf(null, '{"locale":"fr"}'), 'fr');
  assert.equal(c.acceptLangOf({ 'navigator.languages': ['de-DE'] }, { locale: 'fr-FR' }), 'de-DE');
  // An explicit member of the locale triple re-derives it (OverridePresetGroups).
  assert.equal(c.acceptLangOf({ 'locale:tag': 'de-DE' }, { locale: 'fr-FR' }), 'de-DE,de');
  assert.equal(c.acceptLangOf({ 'navigator.language': 'ja-JP' }, { locale: 'fr-FR' }), 'ja-JP,ja');
  for (const bad of ['{not json', '[1]', '"x"', { 'navigator.languages': 'fr' }, { 'navigator.languages': ['fr', 1] }]) {
    assert.throws(() => c.buildEnv({ config: bad }, {}));
    assert.throws(() => c.acceptLangOf(bad));
  }
});

test('claimed OS mirrors derive.cc ClaimedOs over the effective keys', () => {
  const k = (config, preset) => c.claimedOs(config, preset);
  assert.equal(k({ 'ua:osInfo': 'Windows NT 10.0; Win64; x64', 'ua:platform': 'macOS' }), 'Windows');
  assert.equal(k({ 'ua:osInfo': 'X11; Linux x86_64', 'ua:platform': 'Windows' }), 'Linux');
  assert.equal(k({ 'ua:osInfo': 'garbage', 'ua:platform': 'macOS' }), 'macOS');
  assert.equal(k({ 'ua:platform': 'Windows' }, { os: 'macOS' }), 'Windows');
  assert.equal(k({ 'ua:platform': 'Bogus' }, { os: 'macOS' }), 'macOS');
  assert.equal(k(null, { os: 'Windows' }), 'Windows');
  assert.equal(k(null, null), null);
});

test('FONTCONFIG_FILE is never inherited and the conf must exist', () => {
  assert.equal('FONTCONFIG_FILE' in c.buildEnv({}, { FONTCONFIG_FILE: '/host.conf' }), false);
  const root = fs.mkdtempSync(path.join(require('os').tmpdir(), 'camou-fc-'));
  fs.mkdirSync(path.join(root, 'fonts'));
  assert.throws(() => c.fontconfigFor({ config: { 'ua:platform': 'Windows' }, fontsDir: path.join(root, 'fonts') }), /fontconfig/);
});

test('touch and mobile emulation are forbidden; a temp profile is removed on close and on failure', async () => {
  const ok = { launchPersistentContext: async (dir) => { ok.dir = dir; return { on: (e, fn) => { ok.ev = e; ok.fn = fn; } }; } };
  await assert.rejects(c.launch(ok, '/x/chrome', { hasTouch: true }), /hasTouch/);
  await assert.rejects(c.launch(ok, '/x/chrome', { isMobile: true }), /isMobile/);
  await c.launch(ok, '/x/chrome');
  assert.ok(fs.existsSync(ok.dir));
  assert.equal(ok.ev, 'close');
  ok.fn();
  assert.equal(fs.existsSync(ok.dir), false);
  const bad = { launchPersistentContext: async (dir) => { bad.dir = dir; throw new Error('spawn failed'); } };
  await assert.rejects(c.launch(bad, '/x/chrome'), /spawn failed/);
  assert.equal(fs.existsSync(bad.dir), false);
});
