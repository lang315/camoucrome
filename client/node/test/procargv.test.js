'use strict';
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { test } = require('node:test');
const { procCandidates } = require('../procargv');

const EXE = '/opt/x/chrome';

function fakeProc(procs) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'procargv-'));
  for (const [pid, argv] of Object.entries(procs)) {
    fs.mkdirSync(path.join(root, pid));
    fs.writeFileSync(path.join(root, pid, 'cmdline'), `${argv.join('\0')}\0`);
  }
  fs.mkdirSync(path.join(root, 'self'));
  return root;
}

test('one browser is one candidate; its children and other programs are ignored', () => {
  const root = fakeProc({ 10: [EXE, '--headless=new'], 11: [EXE, '--type=renderer'], 12: ['/usr/bin/node', 'probe.js'] });
  assert.deepEqual(procCandidates(root, EXE), [[EXE, '--headless=new']]);
});

test('a stray main process is a second candidate', () => {
  const root = fakeProc({ 10: [EXE, '--headless', '--remote-debugging-port=0', 'about:blank'], 20: [EXE, '--headless=new'] });
  assert.equal(procCandidates(root, EXE).length, 2);
});

test('chromium\'s space-joined title is split; a missing proc dir is no candidate', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'procargv-'));
  fs.mkdirSync(path.join(root, '7'));
  fs.writeFileSync(path.join(root, '7', 'cmdline'), `${EXE} --headless=new --no-sandbox\0`);
  assert.deepEqual(procCandidates(root, EXE), [[EXE, '--headless=new', '--no-sandbox']]);
  assert.deepEqual(procCandidates(path.join(root, 'missing'), EXE), []);
});
