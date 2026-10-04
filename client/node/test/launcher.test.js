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

const scratch = () => fs.mkdtempSync(path.join(require('os').tmpdir(), 'camou-seeds-'));

test('profile seeds are drawn once and read back', (t) => {
  const root = scratch();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const profile = path.join(root, 'profile'); // the first launch makes it
  const first = c.profileSeeds(profile);
  assert.deepEqual(Object.keys(first).sort(), [...c.SEED_KEYS].sort());
  for (const k of c.SEED_KEYS) assert.ok(first[k] >= 1 && first[k] <= 0xffffffff, k);
  const stored = JSON.parse(fs.readFileSync(path.join(profile, CONTRACT.per_instance_seeds.profile_file)));
  assert.deepEqual(stored, first);
  assert.deepEqual(c.profileSeeds(profile), first);
});

// The file the Python and Go clients write must read the same here.
test("profile seeds read another client's file and draw only the missing keys", (t) => {
  const dir = scratch();
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, CONTRACT.per_instance_seeds.profile_file);
  fs.writeFileSync(file, '{"canvas:seed": 5, "audio:seed": 4294967295}');
  const seeds = c.profileSeeds(dir);
  assert.equal(seeds['canvas:seed'], 5);
  assert.equal(seeds['audio:seed'], 0xffffffff);
  assert.deepEqual(JSON.parse(fs.readFileSync(file)), seeds);
});

// A redraw would silently give the profile a different canvas, audio and
// device-ID fingerprint than every earlier session showed.
test('profile seeds refuse a damaged file rather than redraw', (t) => {
  for (const damaged of ['{"canvas:seed"', '[1, 2]', '{"audio:seed": 0}', '{"audio:seed": 4294967296}',
    '{"audio:seed": "7"}', '{"audio:seed": true}', '{"audio:seed": 1.5}']) {
    const dir = scratch();
    t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
    const file = path.join(dir, CONTRACT.per_instance_seeds.profile_file);
    fs.writeFileSync(file, damaged);
    assert.throws(() => c.profileSeeds(dir), /camoucrome-seeds\.json/, damaged);
    assert.equal(fs.readFileSync(file, 'utf8'), damaged);
  }
});

test('launch refuses forbidden options and uses a persistent context without viewport emulation', async () => {
  const calls = [];
  const ctx = { on: (e, fn) => { ctx.fn = fn; }, close: async () => {} };
  const chromium = { launchPersistentContext: async (dir, opts) => { calls.push([dir, opts]); return ctx; } };
  await assert.rejects(c.launch(chromium, '/x/chrome', { timezoneId: 'UTC' }), /timezoneId/);
  assert.equal(await c.launch(chromium, '/x/chrome', { config: { a: 1 }, userDataDir: '/tmp/p', window: [800, 600] }), ctx);
  await ctx.fn(); // the crash-dump dir
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
  assert.ok(c.fontconfigFor({ preset: { os: 'macOS' }, fontsDir: path.join(root, 'fonts') }).endsWith(path.join('settings', 'fontconfig', 'macos.conf')));
  fs.writeFileSync(path.join(root, 'chrome'), '');
  assert.equal(c.fontconfigFor({ config: { 'ua:platform': 'Windows' }, executablePath: path.join(root, 'chrome') }), want);
  assert.equal(c.buildEnv({ fontconfig: want }, {}).FONTCONFIG_FILE, want);
  assert.equal('FONTCONFIG_FILE' in c.buildEnv({}, {}), false);
  fs.rmSync(root, { recursive: true });
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
  fs.rmSync(root, { recursive: true });
});

test('touch and mobile emulation are forbidden; a temp profile is removed on close and on failure', async () => {
  const ok = { launchPersistentContext: async (dir) => { ok.dir = dir; return { on: (e, fn) => { ok.ev = e; ok.fn = fn; }, close: async () => {} }; } };
  await assert.rejects(c.launch(ok, '/x/chrome', { hasTouch: true }), /hasTouch/);
  await assert.rejects(c.launch(ok, '/x/chrome', { isMobile: true }), /isMobile/);
  await c.launch(ok, '/x/chrome');
  assert.ok(fs.existsSync(ok.dir));
  assert.equal(ok.ev, 'close');
  await ok.fn();
  assert.equal(fs.existsSync(ok.dir), false);
  const bad = { launchPersistentContext: async (dir) => { bad.dir = dir; throw new Error('spawn failed'); } };
  await assert.rejects(c.launch(bad, '/x/chrome'), /spawn failed/);
  assert.equal(fs.existsSync(bad.dir), false);
});

// A crash's minidump holds the whole environment block, CAMOU_CONFIG verbatim
// (measured 2026-10-03 on Windows). Every launch, a kept profile included,
// points BREAKPAD_DUMP_LOCATION at a temp dir removed on close or on failure.
test('crash dumps go to a dir the launcher deletes; the parent\'s is never inherited', async () => {
  assert.equal(L.crash_dumps.env, c.CRASH_DUMPS_ENV);
  assert.equal(c.CRASH_DUMPS_ENV, 'BREAKPAD_DUMP_LOCATION');
  assert.equal(c.CRASH_DUMPS_ENV in c.buildEnv({}, { BREAKPAD_DUMP_LOCATION: '/host/dumps' }), false);
  assert.equal(c.buildEnv({ crashDir: '/c' }, {}).BREAKPAD_DUMP_LOCATION, '/c');
  const kept = fs.mkdtempSync(path.join(require('os').tmpdir(), 'camou-kept-'));
  const ok = { launchPersistentContext: async (dir, o) => { ok.o = o; return { on: (e, fn) => { ok.ev = e; ok.fn = fn; }, close: async () => {} }; } };
  await c.launch(ok, '/x/chrome', { userDataDir: kept });
  const crash = ok.o.env.BREAKPAD_DUMP_LOCATION;
  assert.ok(fs.existsSync(crash) && !crash.startsWith(kept));
  assert.equal(ok.ev, 'close');
  await ok.fn();
  assert.equal(fs.existsSync(crash), false);
  assert.ok(fs.existsSync(kept));
  const bad = { launchPersistentContext: async (dir, o) => { bad.o = o; throw new Error('spawn failed'); } };
  await assert.rejects(c.launch(bad, '/x/chrome', { userDataDir: kept }), /spawn failed/);
  assert.equal(fs.existsSync(bad.o.env.BREAKPAD_DUMP_LOCATION), false);
  fs.rmSync(kept, { recursive: true });
});

// Linux: the close event fires while the browser is still shutting down, and
// it then writes its profile and crashpad re-creates the dump dir, after the
// event's removal (measured 2026-10-03: 518 such profiles in the box's /tmp).
// When close() resolves, no process names the profile.
test('what the browser writes while closing is removed once close() resolves', async () => {
  const sd = { launchPersistentContext: async (dir, o) => {
    sd.dirs = [dir, o.env.BREAKPAD_DUMP_LOCATION];
    const ctx = { on: (e, fn) => { ctx.fn = fn; },
      close: async () => {
        await ctx.fn();
        for (const d of sd.dirs) fs.mkdirSync(path.join(d, 'Default'), { recursive: true });
      } };
    return ctx;
  } };
  const ctx = await c.launch(sd, '/x/chrome');
  await ctx.close();
  assert.deepEqual(sd.dirs.map((d) => fs.existsSync(d)), [false, false]);
});

test('native host drops font aliases', () => {
  const cfg = { 'ua:platform': 'Windows', 'fonts:alias': { Arial: 'Liberation Sans' },
    'fonts:aliasLocal': { ArialMT: 'Liberation Sans' }, 'fonts:list': ['Arial'] };
  const decoded = (config, hostOs) => JSON.parse(c.buildEnv({ config, hostOs }, {}).CAMOU_CONFIG);
  const got = decoded(cfg, 'Windows');
  assert.deepEqual(got['fonts:list'], ['Arial']);
  assert.ok(!('fonts:alias' in got) && !('fonts:aliasLocal' in got));
  assert.deepEqual(decoded(JSON.stringify(cfg), 'Windows'), got);
  assert.deepEqual(decoded(cfg, 'Linux'), cfg);
  // nothing to drop, or no host OS: the original string reaches the env byte for byte
  const plain = '{"ua:platform":  "Windows", "fonts:list": ["Arial"], "x": 1.0}';
  assert.equal(c.buildEnv({ config: plain, hostOs: 'Windows' }, {}).CAMOU_CONFIG, plain);
  assert.equal(c.buildEnv({ config: JSON.stringify(cfg), hostOs: '' }, {}).CAMOU_CONFIG, JSON.stringify(cfg));
  assert.deepEqual(c.NATIVE_FONTS_DROP, L.native_fonts.drop);
});
