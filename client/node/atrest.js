// What a launch leaves behind: owner-only profile dirs, the sweep of a killed
// client's temp dirs, and the browser stderr redacted out of an error. The
// Python (camoucrome/atrest.py) and Go (atrest.go, core/atrest.go) clients do
// the same.
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');

const STALE_AFTER_MS = 3600 * 1000; // since the dir last changed
const REDACTED = '<redacted>';
// camoucrome-<pid>-<rand> (a temp profile) and camoucrome-crash-<pid>-<rand>, <pid> the launching client's.
// The scripts' own camoucrome-<word>- dirs and the pid-less names of older clients never match.
const OWNED = /^camoucrome-(?:crash-)?([0-9]+)-[^/\\]+$/;
// A quoted segment shaped like a key name (every settings/keys.json name is) is kept on a camoucfg: line unless
// it is a configured value, and so is an invariant id: both are public constants the operator needs.
const KEY_SHAPED = /^[A-Za-z][A-Za-z0-9_]*(?:[.:][A-Za-z0-9_]+)+$/;

// mkdirSync recursive with every directory it creates owner-only (0700); an
// existing one keeps its mode. Windows ignores the mode.
function makedirs(dir) {
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
}

// A temp dir named for this process (kind '' for a profile, 'crash-' for crash
// dumps), so sweep() can tell a killed client's leftovers from a live one's.
// mkdtemp makes it 0700.
function mkdtemp(kind = '') {
  return fs.mkdtempSync(path.join(os.tmpdir(), `camoucrome-${kind}${process.pid}-`));
}

function alive(pid) {
  try {
    process.kill(pid, 0); // signal 0 tests existence, on Windows too
    return true;
  } catch (e) {
    return e.code !== 'ESRCH'; // EPERM: another user's live process
  }
}

function browserRunning(dir) {
  if (process.platform === 'win32') {
    // Chrome holds <profile>/lockfile open without delete sharing while it runs: the remove fails then.
    try {
      fs.unlinkSync(path.join(dir, 'lockfile'));
    } catch (e) {
      return e.code !== 'ENOENT';
    }
    return false;
  }
  let link;
  try {
    link = fs.readlinkSync(path.join(dir, 'SingletonLock')); // "<host>-<pid>", left behind by a killed browser
  } catch {
    return false;
  }
  const pid = link.slice(link.lastIndexOf('-') + 1);
  return !/^[0-9]+$/.test(pid) || alive(Number(pid));
}

// Removes the temp profiles and crash dirs a killed client left (a profile
// holds Preferences with the identity's languages; a crash dir, minidumps with
// CAMOU_CONFIG). Only this client family's names; never `keep` (the caller's
// profile). Liveness: the client's pid is in the name, so one kill(0) per
// candidate, no file to open, and a pid that names any live process keeps the
// dir; a profile is kept too while its SingletonLock / lockfile says a browser
// outlived the client. Failures are ignored.
function sweep(keep) {
  const root = os.tmpdir();
  const kept = keep ? path.resolve(keep) : null;
  let names;
  try {
    names = fs.readdirSync(root);
  } catch {
    return;
  }
  for (const name of names) {
    const m = OWNED.exec(name);
    const dir = path.join(root, name);
    if (!m || dir === kept) continue;
    try {
      const st = fs.lstatSync(dir);
      if (!st.isDirectory() || Date.now() - st.mtimeMs < STALE_AFTER_MS
          || (process.getuid && st.uid !== process.getuid())
          || alive(Number(m[1])) || browserRunning(dir)) continue;
      fs.rmSync(dir, { recursive: true, force: true }); // one pass: a locked dir must not stall the launch
    } catch {
      // a sweep failure is never fatal
    }
  }
}

function joined(env, name) {
  if (name in env) return env[name];
  let s = '';
  for (let n = 1; `${name}_${n}` in env; n++) s += env[`${name}_${n}`];
  return s;
}

function leaves(v, out) {
  if (Array.isArray(v)) v.forEach((x) => leaves(x, out));
  else if (v !== null && typeof v === 'object') Object.values(v).forEach((x) => leaves(x, out));
  else if (v !== null && v !== undefined) out.add(String(v));
}

const WORD = /[A-Za-z0-9_]/;

// line with every whole-token w replaced (a literal scan: one regex of every
// leaf outgrows V8's limit on a large identity).
function replaceToken(line, w) {
  let out = '';
  let from = 0;
  for (let i = line.indexOf(w); i !== -1; i = line.indexOf(w, i + 1)) {
    if (i < from || (i > 0 && WORD.test(line[i - 1])) || WORD.test(line[i + w.length] || '')) continue;
    out += line.slice(from, i) + REDACTED;
    from = i + w.length;
  }
  return out + line.slice(from);
}

// text (the browser's stderr, or an error that carries it) with the identity
// taken out, line structure kept: every CAMOU_CONFIG* / CAMOU_PRESET* string of
// env; every config and preset value of 3+ characters where it stands as a
// whole token; and on a camoucfg: log line, every quoted segment that is
// neither a key name nor an invariant id, plus a validator's unquoted "It
// should be <value>." (a derived value no config leaf holds).
function redact(text, env) {
  const raws = [...new Set(Object.entries(env)
    .filter(([k, v]) => /^CAMOU_(CONFIG|PRESET)(_[0-9]+)?$/.test(k) && v).map(([, v]) => v))]
    .sort((a, b) => b.length - a.length);
  const keys = new Set();
  const vals = new Set();
  for (const name of ['CAMOU_CONFIG', 'CAMOU_PRESET']) {
    let doc;
    try {
      doc = JSON.parse(joined(env, name) || 'null');
    } catch {
      continue;
    }
    if (doc !== null && typeof doc === 'object' && !Array.isArray(doc)) Object.keys(doc).forEach((k) => keys.add(k));
    leaves(doc, vals);
  }
  const words = [...vals].filter((v) => v.length >= 3 && !keys.has(v)).sort((a, b) => b.length - a.length);
  return String(text).split('\n').map((line) => {
    for (const r of raws) line = line.split(r).join(REDACTED);
    if (line.includes('camoucfg:')) {
      line = line.replace(/(It should be ).+?(\. Not repaired)/g, `$1${REDACTED}$2`);
      line = line.replace(/(invariant )?'([^'\n]*)'/g, (all, inv, v) => (inv || keys.has(v)
        || (KEY_SHAPED.test(v) && !vals.has(v)) ? all : `'${REDACTED}'`));
    }
    for (const w of words) line = replaceToken(line, w);
    return line;
  }).join('\n');
}

// Redacts e's message and stack in place and returns it, so the caller still
// gets the driver's own error object.
function redactError(e, env) {
  try {
    if (e && typeof e.message === 'string') e.message = redact(e.message, env);
    if (e && typeof e.stack === 'string') e.stack = redact(e.stack, env);
  } catch {
    // the launch error is what the caller must see
  }
  return e;
}

module.exports = { STALE_AFTER_MS, makedirs, mkdtemp, sweep, redact, redactError };
