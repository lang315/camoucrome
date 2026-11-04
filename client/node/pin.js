// CPU pin (C3): a claim of N cores below the host's is enforced by affinity, so timing on the host cannot show more.
// Playwright runs in this process, so this process spawns Chrome: it is pinned to N of its allowed CPUs right
// before the launch call and restored right after; Chrome and its children inherit the mask. A mutex serialises
// pin-launch-restore, because two overlapping launches would restore each other's mask. Masks are Sets of CPU numbers.
'use strict';
const { execFileSync } = require('child_process');
const crypto = require('crypto');

const toSet = (big) => new Set([...Array(64).keys()].filter((i) => (big >> BigInt(i)) & 1n));
const toBig = (cpus) => [...cpus].reduce((m, c) => m | (1n << BigInt(c)), 0n);
const run = (cmd, args) => execFileSync(cmd, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
const ps = (script) => run('powershell', ['-NoProfile', '-NonInteractive', '-Command', script]);

// The OS calls, replaceable by tests. get returns null where the platform has no affinity API.
const io = {
  get(pid) {
    if (process.platform === 'linux') {
      return toSet(BigInt('0x' + run('taskset', ['-p', String(pid)]).trim().split(/\s+/).pop()));
    }
    if (process.platform === 'win32') {
      // shortcut: one processor group, so at most 64 CPUs; upgrade for a bigger host
      return toSet(BigInt(ps(`(Get-Process -Id ${Number(pid)}).ProcessorAffinity.ToInt64()`).trim()));
    }
    // shortcut: macOS has no CPU affinity API, so a claim below the host's cores is not enforced there; revisit if a macOS host is supported
    return null;
  },
  set(pid, cpus) {
    const mask = toBig(cpus);
    if (process.platform === 'linux') run('taskset', ['-a', '-p', mask.toString(16), String(pid)]);
    else if (process.platform === 'win32') ps(`(Get-Process -Id ${Number(pid)}).ProcessorAffinity = ${mask}`);
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
// (also when call throws). A pin that cannot be set or restored throws, naming the pid.
async function pinned(n, call) {
  const prev = tail;
  let done;
  tail = new Promise((r) => { done = r; });
  await prev;
  try {
    const pid = process.pid;
    let allowed = null;
    let pinnedNow = false;
    try {
      allowed = io.get(pid);
      if (allowed && n < allowed.size) {
        io.set(pid, sample(allowed, n));
        pinnedNow = true;
      }
    } catch (e) {
      throw new Error(`cannot pin pid ${pid} to ${n} CPUs: ${e.message}`);
    }
    try {
      return await call();
    } finally {
      if (pinnedNow) {
        try {
          io.set(pid, allowed);
        } catch (e) {
          // eslint-disable-next-line no-unsafe-finally
          throw new Error(`cannot restore pid ${pid} to its ${allowed.size} CPUs: ${e.message}`);
        }
      }
    }
  } finally {
    done();
  }
}

module.exports = { io, pinned };
