// What a launch leaves on disk, and what its error text carries (the #272
// audit's three client-side holes). Mirrors client/python/tests/test_at_rest.py.
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const cp = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const root = fs.mkdtempSync(path.join(os.tmpdir(), 'camou-atrest-test-'));
process.env.TMPDIR = root; process.env.TEMP = root; process.env.TMP = root; // os.tmpdir() of this test process
const camoucrome = require('..');
const atrest = require('../atrest');

const posix = process.platform !== 'win32';
const mode = (p) => (fs.statSync(p).mode & 0o777).toString(8);
const fresh = (name) => { const d = path.join(root, name); fs.mkdirSync(d); return d; };
const ctx = () => ({ on() {}, close: async () => {} });
function chromium(error) {
  const c = { async launchPersistentContext(dir, o) { c.dir = dir; c.o = o; if (error) throw error; return ctx(); } };
  return c;
}

// 1. Profile dir mode.

test('profileSeeds creates every missing dir owner-only', { skip: !posix }, () => {
  const old = process.umask(0o022);
  try {
    const base = fresh('seeds-new');
    const udd = path.join(base, 'a', 'b', 'udd');
    camoucrome.profileSeeds(udd);
    for (const d of [path.join(base, 'a'), path.join(base, 'a', 'b'), udd]) assert.strictEqual(mode(d), '700', d);
  } finally { process.umask(old); }
});

test('profileSeeds leaves an existing dir mode alone', { skip: !posix }, () => {
  const old = process.umask(0o022);
  try {
    const udd = fresh('seeds-kept');
    fs.chmodSync(udd, 0o755);
    camoucrome.profileSeeds(udd);
    assert.strictEqual(mode(udd), '755');
  } finally { process.umask(old); }
});

test('launch temp dirs are owner-only and carry the client pid', async () => {
  const c = chromium();
  await camoucrome.launch(c, '/x/chrome');
  const crash = c.o.env.BREAKPAD_DUMP_LOCATION;
  assert.ok(path.basename(c.dir).startsWith(`camoucrome-${process.pid}-`), c.dir);
  assert.ok(path.basename(crash).startsWith(`camoucrome-crash-${process.pid}-`), crash);
  if (posix) for (const d of [c.dir, crash]) assert.strictEqual(mode(d), '700', d);
});

// 2. Stale temp dirs of a killed client.

function deadPid() {
  const r = cp.spawnSync(process.execPath, ['-e', '']); // reaped: the pid names no process
  return r.pid;
}

function made(name, { age = 7200, lockPid } = {}) {
  const d = fresh(name);
  fs.writeFileSync(path.join(d, 'Preferences'), '{"intl":{"accept_languages":"xx-YY"}}');
  if (lockPid !== undefined) fs.symlinkSync(`somehost-${lockPid}`, path.join(d, 'SingletonLock'));
  const t = Date.now() / 1000 - age;
  fs.utimesSync(d, t, t);
  return d;
}

test('launch sweeps only a dead client\'s old temp dirs', async () => {
  const dead = deadPid();
  const gone = [made(`camoucrome-${dead}-abcd12`), made(`camoucrome-crash-${dead}-abcd12`)];
  const kept = [made(`camoucrome-${process.pid}-live`), made(`camoucrome-${dead}-young`, { age: 60 }),
    made('camoucrome-verify-abcd12'), made('camoucrome-abcd12'), made(`camoucrome-${dead}-caller`)];
  if (posix) {
    kept.push(made(`camoucrome-${dead}-locked`, { lockPid: process.pid }));
    const target = made('elsewhere');
    fs.symlinkSync(target, path.join(root, `camoucrome-${dead}-link`));
    kept.push(target);
  }
  fs.writeFileSync(path.join(root, `camoucrome-${dead}-file`), 'x');
  await camoucrome.launch(chromium(), '/x/chrome', { userDataDir: path.join(root, `camoucrome-${dead}-caller`) });
  assert.deepStrictEqual(gone.filter((d) => fs.existsSync(d)).map((d) => path.basename(d)), []);
  assert.deepStrictEqual(kept.filter((d) => !fs.existsSync(path.join(d, 'Preferences'))).map((d) => path.basename(d)), []);
  assert.ok(fs.existsSync(path.join(root, `camoucrome-${dead}-file`)));
  if (posix) assert.ok(fs.lstatSync(path.join(root, `camoucrome-${dead}-link`)).isSymbolicLink());
});

test('a failure to remove is ignored', async (t) => {
  made(`camoucrome-${deadPid()}-busy`);
  t.mock.method(fs, 'rmSync', () => { throw new Error('busy'); });
  await camoucrome.launch(chromium(), '/x/chrome'); // no throw
});

test('sweep spares the caller\'s dir however it is spelled', { skip: !posix }, () => {
  const dead = deadPid();
  const alias = path.join(fs.mkdtempSync(path.join(path.dirname(root), 'camou-alias-')), 'alias');
  fs.symlinkSync(root, alias); // another spelling of the temp root (/var vs /private/var)
  try {
    const swept = [];
    for (const [name, below] of [['caller', []], ['outer', ['profile']], ['unborn', ['not', 'yet']]]) {
      const d = made(`camoucrome-${dead}-${name}`);
      if (name === 'outer') { // the caller's dir inside a candidate
        fs.mkdirSync(path.join(d, 'profile'));
        const t = Date.now() / 1000 - 7200; // the child's mkdir made it young
        fs.utimesSync(d, t, t);
      }
      atrest.sweep(path.join(alias, path.basename(d), ...below)); // 'unborn': not created yet, the sweep runs first
      if (!fs.existsSync(path.join(d, 'Preferences'))) swept.push(name);
    }
    assert.deepStrictEqual(swept, []);
  } finally {
    fs.rmSync(path.dirname(alias), { recursive: true, force: true });
  }
});

test('sweep removes nothing when the caller\'s dir cannot be resolved', { skip: !posix }, () => {
  const stale = made(`camoucrome-${deadPid()}-unresolved`);
  fs.symlinkSync('loop', path.join(root, 'loop')); // ELOOP: neither found nor missing
  atrest.sweep(path.join(root, 'loop', 'profile'));
  assert.ok(fs.existsSync(stale));
});

// 3. Browser stderr in the launch error.

const CONFIG = { 'navigator.platform': 'Win32', 'timezone:id': 'Asia/Secretville',
  'navigator.hardwareConcurrency': 8, 'ua:fullVersion': '157.0.8103.51', 'navigator.languages': ['xq-ZZ', 'xq'] };
const PRESET = { os: 'Windows', gpu: 'ANGLE (Secret GPU 9000)' };
const STDERR = [
  'browserType.launchPersistentContext: Target page, context or browser has been closed',
  'Browser logs:',
  '<launching> /x/chrome --accept-lang=xq-ZZ,xq --user-data-dir=/p',
  "[pid=7][err] [7:7:ERROR:coherence_validator.cc(726)] camoucfg: invariant 'inv-1' violated. "
    + "'navigator.platform' is 'Win32', which disagrees with 'ua:osInfo'. It should be 'MacIntel'. Not repaired: x",
  "[pid=7][err] [7:7:ERROR:coherence_validator.cc(707)] camoucfg: invariant 'inv-2' violated. "
    + "'ua:fullVersion' is set but 'x.y' is not. It should be Mozilla/5.0 (Derived 1.2). Not repaired: x",
  "[pid=7][err] [7:7:ERROR:coherence_validator.cc(743)] camoucfg: 'navigator.hardwareConcurrency' is '8', out of range",
  "[pid=7][err] [7:7:WARNING:tz.cc(1)] camoucfg: timezone:id 'Asia/Secretville' invalid; falling back to UTC",
  '[pid=7][err] [7:7:WARNING:gpu.cc(1)] renderer ANGLE (Secret GPU 9000) chosen',
  "[pid=7][err] [7:7:WARNING:ua.cc(1)] camoucfg: 'ua:osInfo' is set but 'ua:platform' is not, so x",
].join('\n');
const SECRETS = ['Win32', 'MacIntel', 'Mozilla/5.0 (Derived 1.2)', "'8'", 'Asia/Secretville', '157.0.8103.51',
  'xq-ZZ', 'Secret GPU 9000'];
const KEPT = ["invariant 'inv-1' violated", "but 'x.y' is not", "camoucfg: 'ua:osInfo' is set but 'ua:platform' is not, so x",
  "'navigator.hardwareConcurrency' is '<redacted>', out of range", 'coherence_validator.cc(743)']; // public names stay

test('the launch error has the configured values redacted, line by line', async () => {
  const env = camoucrome.buildEnv({ config: CONFIG, preset: PRESET });
  const err = new Error(STDERR + '\n' + env.CAMOU_CONFIG);
  // A Windows claim on a Linux host needs a fonts dir with its fontconfig beside it: give one, so the launch reaches the driver.
  const fontsRoot = fs.mkdtempSync(path.join(root, 'fonts-'));
  fs.mkdirSync(path.join(fontsRoot, 'fonts'));
  const conf = path.resolve(fontsRoot, camoucrome.FONTCONFIG_FILES.Windows);
  fs.mkdirSync(path.dirname(conf), { recursive: true });
  fs.writeFileSync(conf, '<fontconfig/>');
  const opts = { config: CONFIG, preset: PRESET, fontsDir: path.join(fontsRoot, 'fonts'), pinCpuCores: false }; // fake driver: no pid to pin
  await assert.rejects(camoucrome.launch(chromium(err), '/x/chrome', opts), (e) => {
    assert.strictEqual(e, err); // the driver's own error object
    for (const text of [e.message, e.stack]) {
      assert.deepStrictEqual([...SECRETS, env.CAMOU_CONFIG].filter((s) => text.includes(s)), []);
    }
    assert.strictEqual(e.message.split('\n').length, STDERR.split('\n').length + 1);
    assert.deepStrictEqual(KEPT.filter((k) => !e.message.includes(k)), []);
    return true;
  });
});

test('redact drops chunked config and preset strings', () => {
  const env = camoucrome.buildEnv({ config: { 'k:big': 'Q'.repeat(70000) }, preset: { os: 'Windows', pad: 'P'.repeat(70000) } });
  assert.ok(env.CAMOU_CONFIG_1 && env.CAMOU_PRESET_1);
  const out = atrest.redact(env.CAMOU_CONFIG_1 + '\n' + env.CAMOU_PRESET_2 + '\nQQQ', env);
  assert.ok(!out.includes('Q'.repeat(100)) && !out.includes('P'.repeat(100)));
});

test.after(() => fs.rmSync(root, { recursive: true, force: true }));
