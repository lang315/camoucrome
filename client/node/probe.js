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

(async () => {
  const { chromium } = require(args.driver); // absolute path of the package dir
  const ctx = await camoucrome.launch(chromium, args.executable, {
    config: fromFile(args.config), preset: fromFile(args.preset), strict: args.strict === true,
    // Windows: the sandbox strips CAMOU_* from a renderer unless the
    // windows-sandbox-env patch lets it through, and --no-sandbox hides that.
    headless: args.headed !== true, args: args.sandbox === true ? [] : ['--no-sandbox'],
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
