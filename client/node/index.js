// Camoucrome Node client. Same contract as client/python and client/go
// (settings/launcher.json); the anti-detect property lives in patchright's
// driver and in the browser, this module only carries the configuration in.
//
//   const { chromium } = require('patchright');
//   const camoucrome = require('camoucrome');
//   const ctx = await camoucrome.launch(chromium, '/path/to/chrome', {
//     config: {...}, preset: presetJson, window: [1920, 1040], dpr: 1.25 });
//
// Never addInitScript anything a page could enumerate: the driver runs a
// user's init script in the MAIN world (measured 2026-09-10); evaluate runs
// in an isolated world, use that.
'use strict';
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');

// Mirrors settings/launcher.json; test/launcher.test.js asserts it.
const FORBIDDEN_OPTIONS = new Set([
  'locale', 'timezoneId', 'userAgent', 'viewport', 'screen',
  'deviceScaleFactor', 'geolocation', 'colorScheme', 'extraHTTPHeaders',
]);
const BASE_ARGS = ['--no-first-run', '--no-default-browser-check'];
const SEED_KEYS = ['canvas:seed', 'audio:seed', 'mediaDevices:seed'];

const asJson = (v) => (typeof v === 'string' ? v : JSON.stringify(v));

// Every CAMOU_* of the parent dropped first (a stale CAMOU_CONFIG_1 would
// otherwise win), then config/preset/strict set.
function buildEnv({ config, preset, strict } = {}, base = process.env) {
  const env = {};
  for (const [k, v] of Object.entries(base)) if (!k.startsWith('CAMOU_')) env[k] = v;
  if (config != null) env.CAMOU_CONFIG = asJson(config);
  if (preset != null) env.CAMOU_PRESET = asJson(preset);
  if (strict) env.CAMOU_CONFIG_STRICT = '1';
  return env;
}

// --accept-lang the config implies (navigator.languages joined, else
// locale:tag): without it a French config still sends en-US (measured).
function acceptLangOf(config) {
  if (config == null) return null;
  const c = typeof config === 'string' ? JSON.parse(config) : config;
  const langs = c['navigator.languages'] || (c['locale:tag'] ? [c['locale:tag']] : []);
  return langs.length ? langs.join(',') : null;
}

// The whole argv besides what the driver adds: launch() ignores Playwright's
// default args (they carry --disable-features=<18>, --blink-settings, ...).
function buildArgs({ window, dpr, extra = [], headless = true, userDataDir,
  acceptLang, extensions = [], spkiList = [] } = {}) {
  const args = [...BASE_ARGS];
  if (headless) args.push('--headless=new');
  args.push('--remote-debugging-pipe');
  if (userDataDir) args.push(`--user-data-dir=${userDataDir}`);
  if (window) args.push(`--window-size=${window[0]},${window[1]}`);
  if (dpr != null) args.push(`--force-device-scale-factor=${dpr}`);
  if (acceptLang) args.push(`--accept-lang=${acceptLang}`);
  if (extensions.length) {
    const paths = extensions.join(',');
    args.push(`--disable-extensions-except=${paths}`, `--load-extension=${paths}`);
  }
  if (spkiList.length) args.push(`--ignore-certificate-errors-spki-list=${spkiList.join(',')}`);
  return args.concat(extra);
}

// Fresh non-zero uint32 seeds; merge explicit keys over the result.
function perInstanceConfig() {
  const cfg = {};
  for (const k of SEED_KEYS) {
    let v = 0;
    while (v === 0) v = crypto.randomBytes(4).readUInt32LE(0);
    cfg[k] = v;
  }
  return cfg;
}

async function launch(chromium, executablePath, {
  config, preset, strict = false, userDataDir, window, dpr, headless = true,
  args = [], extensions = [], spkiList = [], ...options
} = {}) {
  const bad = Object.keys(options).filter((k) => FORBIDDEN_OPTIONS.has(k));
  if (bad.length) {
    throw new Error(`${JSON.stringify(bad)} must come through CAMOU_CONFIG, not the driver: `
      + 'a second emulation of the same surface fights the fork\'s value');
  }
  const dir = userDataDir || fs.mkdtempSync(path.join(os.tmpdir(), 'camoucrome-'));
  return chromium.launchPersistentContext(dir, {
    executablePath: String(executablePath),
    headless,
    ignoreDefaultArgs: true,
    env: buildEnv({ config, preset, strict }),
    args: buildArgs({ window, dpr, extra: args, headless, userDataDir: dir,
      acceptLang: acceptLangOf(config), extensions, spkiList }),
    // Otherwise a 1280x720 viewport is emulated, fighting screen.* and the
    // window size.
    viewport: null,
    ...options,
  });
}

module.exports = { FORBIDDEN_OPTIONS, BASE_ARGS, SEED_KEYS, buildEnv, buildArgs,
  acceptLangOf, perInstanceConfig, launch };
