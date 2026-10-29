'use strict';
const assert = require('node:assert/strict');
const childProcess = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { test } = require('node:test');

// A driver package whose chromium hands back a context that fails on the first
// page call. It records the profile dir it was given and whether close() ran.
function fakeDriver(root) {
  fs.writeFileSync(path.join(root, 'index.js'), `
const fs = require('fs');
const log = ${JSON.stringify(path.join(root, 'log.json'))};
const note = (o) => fs.writeFileSync(log, JSON.stringify({ ...(fs.existsSync(log) ? JSON.parse(fs.readFileSync(log)) : {}), ...o }));
exports.chromium = { launchPersistentContext: async (dir) => {
  fs.mkdirSync(dir, { recursive: true });
  note({ dir });
  return {
    on() {},
    pages: () => [{ addInitScript: async () => { throw new Error('page gone'); } }],
    close: async () => note({ closed: true }),
  };
} };`);
}

test('a probe that fails after the launch still closes the context and removes the temp profile', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'probe-test-'));
  try {
    fakeDriver(root);
    const r = childProcess.spawnSync(process.execPath, [path.join(__dirname, '..', 'probe.js'),
      '--driver', root, '--executable', '/x/chrome', '--url', 'about:blank'], { encoding: 'utf8' });
    assert.equal(r.status, 1, r.stderr);
    assert.match(r.stderr, /page gone/);
    const log = JSON.parse(fs.readFileSync(path.join(root, 'log.json'), 'utf8'));
    assert.equal(log.closed, true, 'close() never ran: the launch\'s temp profile and crash dir leak');
    assert.equal(fs.existsSync(log.dir), false, `${log.dir} left behind`);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
