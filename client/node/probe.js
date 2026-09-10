#!/usr/bin/env node
// Probe command for scripts/verify_sp6b_driver.py, the Node twin of
// python -m camoucrome.probe: launch through this package with the driver
// package given (patchright-core or playwright-core, both expose chromium),
// load a URL, print the page's own report (#o text) and the browser argv.
// The caller sets DEBUG=pw:protocol and reads the protocol log from stderr.
'use strict';
const fs = require('fs');
const camoucrome = require('.');

const args = Object.fromEntries(process.argv.slice(2).map((a, i, all) =>
  a.startsWith('--') ? [a.slice(2), all[i + 1] && !all[i + 1].startsWith('--') ? all[i + 1] : true] : null).filter(Boolean));

function browserArgv(executable) {
  for (const pid of fs.readdirSync('/proc')) {
    if (!/^\d+$/.test(pid)) continue;
    let raw;
    try { raw = fs.readFileSync(`/proc/${pid}/cmdline`); } catch { continue; }
    let parts = raw.toString('binary').replace(/\0$/, '').split('\0');
    if (parts.length === 1) parts = parts[0].split(' '); // Chromium rewrites its cmdline into one string
    if (parts[0] === executable && !parts.some((p) => p.startsWith('--type='))) return parts;
  }
  return [];
}

(async () => {
  const { chromium } = require(args.driver); // absolute path of the package dir
  const ctx = await camoucrome.launch(chromium, args.executable, {
    config: args.config, preset: args.preset, strict: args.strict === true,
    headless: args.headed !== true, args: ['--no-sandbox'],
    window: args.window ? args.window.split(',').map(Number) : undefined,
    dpr: args.dpr ? Number(args.dpr) : undefined,
  });
  const page = ctx.pages()[0] || await ctx.newPage();
  // SP2 4.2 item, same as the other probes: the page reports typeof __camou_init.
  await page.addInitScript('window.__camou_init = 1');
  await page.goto(args.url, { waitUntil: 'load' });
  const text = await page.locator('#o').textContent();
  const argv = browserArgv(args.executable);
  await ctx.close();
  process.stdout.write(JSON.stringify({ driver: args.label || 'node', report: JSON.parse(text), argv }));
})().catch((e) => { console.error(String(e)); process.exit(1); });
