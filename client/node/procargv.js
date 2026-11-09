'use strict';
const fs = require('fs');

// argv of every browser (not renderer/gpu) process running `executable`, read from /proc. More than one means a stray
// earlier run is still alive: the probe reports that instead of trusting which one it read (2026-10-29: a stray headless
// chrome made all three patchright rows of verify_sp6b_driver compare a stock-style argv).
function procCandidates(procRoot, executable) {
  let pids;
  try { pids = fs.readdirSync(procRoot); } catch { return []; }
  const found = [];
  for (const pid of pids.filter((p) => /^\d+$/.test(p)).sort((a, b) => a - b)) {
    let raw;
    try { raw = fs.readFileSync(`${procRoot}/${pid}/cmdline`); } catch { continue; }
    let parts = raw.toString('binary').replace(/\0$/, '').split('\0');
    if (parts.length === 1) parts = parts[0].split(' '); // Chromium rewrites its cmdline into one string
    if (parts[0] === executable && !parts.some((p) => p.startsWith('--type='))) found.push(parts);
  }
  return found;
}

module.exports = { procCandidates };
