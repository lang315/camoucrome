// CPU pin (C3): a claim of N cores below the host's is enforced by affinity, so timing on the host cannot show more.
// Playwright runs in this process, so this process spawns Chrome: it is pinned to N of its allowed CPUs right
// before the launch call and restored right after; Chrome and its children inherit the mask. A mutex serialises
// pin-launch-restore, because two overlapping launches would restore each other's mask. Masks are Sets of CPU numbers.
'use strict';
const { execFileSync } = require('child_process');
const fs = require('fs');
const crypto = require('crypto');

const toSet = (big) => new Set([...Array(64).keys()].filter((i) => (big >> BigInt(i)) & 1n));
const toBig = (cpus) => [...cpus].reduce((m, c) => m | (1n << BigInt(c)), 0n);
// "0-3,8" <-> Set: the Linux list form has no 64-CPU limit, unlike a hex mask
const fromList = (l) => new Set(l.split(',').flatMap((r) => {
  const [a, b = a] = r.split('-').map(Number);
  return Array.from({ length: b - a + 1 }, (_, i) => a + i);
}));
const toList = (cpus) => [...cpus].sort((a, b) => a - b).join(',');
const run = (cmd, args) => execFileSync(cmd, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
const ps = (script) => run('powershell', ['-NoProfile', '-NonInteractive', '-Command', script]);

// The OS calls, replaceable by tests. get returns null where the platform has no affinity API.
const io = {
  get(pid) {
    if (process.platform === 'linux') {
      const m = /^Cpus_allowed_list:\s*(\S+)/m.exec(fs.readFileSync(`/proc/${Number(pid)}/status`, 'utf8'));
      if (!m) throw new Error(`no Cpus_allowed_list in /proc/${pid}/status`);
      return fromList(m[1]);
    }
    if (process.platform === 'win32') {
      // shortcut: one processor group, so at most 64 CPUs; upgrade for a bigger host
      return toSet(BigInt(ps(`(Get-Process -Id ${Number(pid)}).ProcessorAffinity.ToInt64()`).trim()));
    }
    // shortcut: macOS has no CPU affinity API, so a claim below the host's cores is not enforced there; revisit if a macOS host is supported
    return null;
  },
  set(pid, cpus) {
    if (process.platform === 'linux') run('taskset', ['-a', '-c', '-p', toList(cpus), String(pid)]);
    else if (process.platform === 'win32') ps(`(Get-Process -Id ${Number(pid)}).ProcessorAffinity = ${toBig(cpus)}`);
  },
};

const sample = (cpus, n) => {
  const a = [...cpus].sort((x, y) => x - y);
  for (let i = a.length - 1; i > 0; i--) { // Fisher-Yates
    const j = crypto.randomInt(i + 1);
    [a[i], a[j]] = [a[j], a[i]];
  }
  return new Set(a.slice(0, n));
};

let tail = Promise.resolve();

// Runs call() with this process pinned to n of its allowed CPUs when n is below them, then restores the mask
// (also when call throws). A pin that cannot be set or restored throws, naming the pid. A restore that fails after a
// good launch closes the context first, so no browser runs unowned.
async function pinned(n, call) {
  const prev = tail;
  let done;
  tail = new Promise((r) => { done = r; });
  await prev;
  try {
    const pid = process.pid;
    let allowed;
    try {
      allowed = io.get(pid);
    } catch (e) {
      throw new Error(`cannot read the CPU mask of pid ${pid}: ${e.message}`);
    }
    if (!allowed || n >= allowed.size) return await call();
    try {
      io.set(pid, sample(allowed, n));
    } catch (e) {
      try { io.set(pid, allowed); } catch (_) { /* best effort: a half-applied pin */ }
      throw new Error(`cannot pin pid ${pid} to ${n} CPUs: ${e.message}`);
    }
    let ctx;
    try {
      ctx = await call();
    } catch (e) {
      try { io.set(pid, allowed); } catch (_) { /* the launch error is the one to report */ }
      throw e;
    }
    try {
      io.set(pid, allowed);
    } catch (e) {
      try { await ctx.close(); } catch (_) { /* already failing */ }
      throw new Error(`cannot restore pid ${pid} to its ${allowed.size} CPUs: ${e.message}`);
    }
    return ctx;
  } finally {
    done();
  }
}

module.exports = { io, pinned, fromList, toList };
