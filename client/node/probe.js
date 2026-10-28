#!/usr/bin/env node
// Probe command for scripts/verify_sp6b_driver.py, the Node twin of
// python -m camoucrome.probe: launch through this package with the driver
// package given (patchright-core or playwright-core, both expose chromium),
// load a URL, print the page's own report (#o text) and the browser argv.
// The caller sets DEBUG=pw:protocol and reads the protocol log from stderr.
'use strict';
const childProcess = require('child_process');
const fs = require('fs');
const path = require('path');
const camoucrome = require('.');

const args = Object.fromEntries(process.argv.slice(2).map((a, i, all) =>
  a.startsWith('--') ? [a.slice(2), all[i + 1] && !all[i + 1].startsWith('--') ? all[i + 1] : true] : null).filter(Boolean));

function procArgv(executable) {
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

// Windows: Win32_Process has each process's command line as one string, and
// CommandLineToArgvW splits it the way the process itself did. Node cannot
// call it, so PowerShell does (sent -EncodedCommand: no quoting to survive).
// A null CommandLine (access denied) must not reach CommandLineToArgvW, which
// would return PowerShell's own argv.
const WINDOWS_ARGV = `
Add-Type -Namespace Camou -Name Shell -MemberDefinition '
[DllImport("shell32.dll")] public static extern System.IntPtr CommandLineToArgvW([MarshalAs(UnmanagedType.LPWStr)] string c, out int n);
[DllImport("kernel32.dll")] public static extern System.IntPtr LocalFree(System.IntPtr p);'
$out = @(foreach ($p in Get-CimInstance Win32_Process -Filter "Name='NAME'") {
  if (-not $p.CommandLine) { continue }
  $n = 0; $ptr = [Camou.Shell]::CommandLineToArgvW($p.CommandLine, [ref]$n)
  $argv = @(for ($i = 0; $i -lt $n; $i++) {
    [Runtime.InteropServices.Marshal]::PtrToStringUni([Runtime.InteropServices.Marshal]::ReadIntPtr($ptr, $i * [IntPtr]::Size)) })
  [void][Camou.Shell]::LocalFree($ptr)
  @{ path = $p.ExecutablePath; argv = $argv }
})
ConvertTo-Json -Compress -Depth 3 -InputObject $out
`;

function windowsArgv(executable) {
  const script = WINDOWS_ARGV.replace('NAME', path.basename(executable));
  const out = childProcess.spawnSync('powershell', ['-NoProfile', '-EncodedCommand',
    Buffer.from(script, 'utf16le').toString('base64')], { encoding: 'utf8' }).stdout.trim();
  const want = path.resolve(executable).toLowerCase();
  for (const p of out ? [].concat(JSON.parse(out)) : []) {
    const argv = [].concat(p.argv);
    if ((p.path || '').toLowerCase() === want && !argv.some((a) => a.startsWith('--type='))) return argv;
  }
  return [];
}

const browserArgv = (executable) => (process.platform === 'win32' ? windowsArgv(executable) : procArgv(executable));

// A generated identity is ~37 KB (Windows) to ~140 KB (macOS): past Windows'
// 32767-char command line and Linux's 128 KiB single argument, so @path reads a file.
const fromFile = (v) => (typeof v === 'string' && v.startsWith('@') ? fs.readFileSync(v.slice(1), 'utf8') : v);

// scripts/verify_human_click_clients.py row args.scenario -> {log, extra}: the
// page's own #o, plus what the page cannot see (error messages, a second context's log).
async function runScenario(chromium, config) {
  const n = args.scenario;
  const kw = { headless: args.headed !== true, args: ['--no-sandbox'] };
  const errOf = async (fn) => { try { await fn(); return null; } catch (e) { return String(e.message || e); } };
  if (n === 'B4') {  // launch must refuse humanClick without humanize, before any browser
    const extra = {};
    for (const [key, cfg] of [['nohumanize', undefined], ['false', JSON.stringify({ 'humanize:enabled': false })]]) {
      extra[key] = await errOf(async () => (await camoucrome.launch(chromium, args.executable, { config: cfg, humanClick: true, ...kw })).close());
    }
    return { log: {}, extra };
  }
  if (!['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'stock-missing', 'B1', 'B2', 'B3'].includes(n)) {
    throw new Error(`unknown scenario ${n}`);
  }
  const logOf = async (page) => { await page.waitForTimeout(500); return JSON.parse(await page.locator('#o').textContent()); };
  const open = async (c) => { const p = c.pages()[0] || await c.newPage(); await p.goto(args.url, { waitUntil: 'load' }); return p; };
  const ctx = await camoucrome.launch(chromium, args.executable, { config, humanClick: n.startsWith('B'), ...kw });
  const others = [];
  let extra = null, log;
  try {
    const page = await open(ctx);
    const loc = page.locator('#t');
    if (n === 'A1' || n === 'A7') {
      for (let i = 0; i < (n === 'A1' ? 20 : 5); i++) await camoucrome.humanClick(loc);
    } else if (['A2', 'A3', 'A4', 'A5'].includes(n)) {
      await camoucrome.humanClick(loc);
    } else if (n === 'A6') {
      await camoucrome.humanClick(page.locator('#late'));
      extra = { missing: await errOf(() => camoucrome.humanClick(page.locator('#nope'), { timeout: 500 })),
        strict: await errOf(() => camoucrome.humanClick(page.locator('.dup'), { timeout: 500 })),
        hidden: await errOf(() => camoucrome.humanClick(page.locator('#hid'), { timeout: 500 })) };
    } else if (n === 'stock-missing') {
      extra = { missing: await errOf(() => page.locator('#nope').click({ timeout: 500 })),
        strict: await errOf(() => page.locator('.dup').click({ timeout: 500 })),
        hidden: await errOf(() => page.locator('#hid').click({ timeout: 500 })) };
    } else if (n === 'B1') {
      for (let i = 0; i < 10; i++) { await loc.click(); await page.click('#t'); }
    } else if (n === 'B3') {
      const hitsAfter = [];
      await page.click('#t', { position: { x: 5, y: 5 } });
      hitsAfter.push(require('./human_click').wrapperHits());
      await page.click('#t', { force: true });
      hitsAfter.push(require('./human_click').wrapperHits());
      await loc.click({ trial: true });
      hitsAfter.push(require('./human_click').wrapperHits());
      extra = { hits_after: hitsAfter };
    } else if (n === 'B2') {  // contexts launch() did not flag: a direct one, and a launch() without the flag
      const direct = await chromium.launchPersistentContext(fs.mkdtempSync(path.join(require('os').tmpdir(), 'camoucrome-b2-')),
        { executablePath: args.executable, ...kw });
      others.push(direct);
      const plain = await camoucrome.launch(chromium, args.executable, { config, humanClick: false, ...kw });
      others.push(plain);
      extra = {};
      for (const [key, c] of [['direct', direct], ['plain', plain]]) {
        const p = await open(c);
        for (let i = 0; i < 3; i++) await p.click('#t');
        extra[key] = await logOf(p);
      }
    }
    log = await logOf(page);
  } finally {
    for (const c of [ctx, ...others]) await c.close();
  }
  return { log, extra };
}

(async () => {
  const { chromium } = require(args.driver); // absolute path of the package dir
  const config = fromFile(args.config);
  if (args.scenario) {
    let out;
    try { out = { ...(await runScenario(chromium, config)), error: null }; } catch (e) { out = { log: null, extra: null, error: String(e.message || e) }; }
    process.stdout.write(JSON.stringify({ ...out, wrapper_hits: require('./human_click').wrapperHits() }));
    return;
  }
  // B (launch({humanClick})) needs humanize:enabled in the config.
  const humanize = !!config && JSON.parse(config)['humanize:enabled'] === true;
  const ctx = await camoucrome.launch(chromium, args.executable, {
    config, humanClick: humanize, preset: fromFile(args.preset), strict: args.strict === true,
    // Windows: the sandbox strips CAMOU_* from a renderer unless the
    // windows-sandbox-env patch lets it through, and --no-sandbox hides that.
    headless: args.headed !== true, args: args.sandbox === true ? [] : ['--no-sandbox'],
    window: args.window ? args.window.split(',').map(Number) : undefined,
    dpr: args.dpr ? Number(args.dpr) : undefined,
    proxy: args.proxy ? { server: args.proxy, bypass: args['proxy-bypass'], username: args['proxy-user'], password: args['proxy-pass'] } : undefined,
  });
  const page = ctx.pages()[0] || await ctx.newPage();
  // SP2 4.2 item, same as the other probes: the page reports typeof __camou_init.
  await page.addInitScript('window.__camou_init = 1');
  await page.goto(args.url, { waitUntil: 'load' });
  // SP2d: exercise A (the helper) and B (page.click) before reporting.
  if (humanize) {
    if (!await page.locator('#camou-click').count()) throw new Error('humanize on but the page has no #camou-click');
    await camoucrome.humanClick(page.locator('#camou-click'));
    await page.click('#camou-click');
  }
  const text = await page.locator('#o').textContent();
  const argv = browserArgv(args.executable);
  await ctx.close();
  process.stdout.write(JSON.stringify({ driver: args.label || 'node', report: JSON.parse(text), argv }));
})().catch((e) => { console.error(String(e)); process.exit(1); });
