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
  'hasTouch', 'isMobile',
]);
const BASE_ARGS = ['--no-first-run', '--no-default-browser-check'];
const SEED_KEYS = ['canvas:seed', 'audio:seed', 'mediaDevices:seed'];

const asJson = (v) => (typeof v === 'string' ? v : JSON.stringify(v));

function asObject(v) {
  const d = v == null ? {} : typeof v === 'string' ? JSON.parse(v) : v;
  if (d === null || typeof d !== 'object' || Array.isArray(d)) throw new Error('config and preset must be JSON objects');
  return d;
}

// derive.cc kForms: [ua:osInfo marker, UA-CH platform] in its match order --
// Android and CrOS before Linux, whose marker their osInfo also contains.
const OS_INFO_MARKERS = [['Android', 'Android'], ['CrOS', 'Chrome OS'], ['Windows NT', 'Windows'],
  ['Macintosh', 'macOS'], ['Linux', 'Linux']];

// The keys the browser ends up with for what the launcher reads: the preset's
// os and locale expanded as preset_loader.cc does, under the explicit config
// (explicit wins). Throws on a shape the browser would silently drop.
function effectiveKeys(config, preset) {
  const p = asObject(preset);
  const c = asObject(config);
  const out = {};
  const setOs = (plat) => {
    const form = OS_INFO_MARKERS.find(([, pl]) => pl === plat);
    if (form) Object.assign(out, { 'ua:osInfo': form[0], 'ua:platform': plat });
  };
  const setLocale = (tag) => {
    const primary = tag.split('-')[0];
    Object.assign(out, { 'locale:tag': tag, 'navigator.language': tag,
      'navigator.languages': primary === tag ? [tag] : [tag, primary] });
  };
  setOs(p.os);
  if (typeof p.locale === 'string') setLocale(p.locale);
  // preset_loader.cc OverridePresetGroups: an explicit member of the preset's
  // OS pair or locale triple re-derives the whole group from it.
  const info = c['ua:osInfo'];
  let fam = typeof info === 'string' ? OS_INFO_MARKERS.find(([m]) => info.includes(m))?.[1] : undefined;
  if (!fam && OS_INFO_MARKERS.some(([, pl]) => pl === c['ua:platform'])) fam = c['ua:platform'];
  if (fam && 'ua:osInfo' in out) setOs(fam);
  const cLangs = c['navigator.languages'];
  const head = Array.isArray(cLangs) && typeof cLangs[0] === 'string' ? cLangs[0]
    : ['navigator.language', 'locale:tag'].map((k) => c[k]).find((v) => typeof v === 'string');
  if (head && 'locale:tag' in out) setLocale(head);
  Object.assign(out, c);
  const langs = out['navigator.languages'];
  if (langs !== undefined && !(Array.isArray(langs) && langs.every((l) => typeof l === 'string'))) {
    throw new Error(`navigator.languages must be a list of strings, got ${JSON.stringify(langs)}`);
  }
  return out;
}

// derive.cc ClaimedOs over the effective keys: a recognised ua:osInfo, else
// ua:platform, else null.
function claimedOs(config, preset) {
  const k = effectiveKeys(config, preset);
  const info = k['ua:osInfo'];
  const form = typeof info === 'string' && OS_INFO_MARKERS.find(([m]) => info.includes(m));
  return form ? form[1] : (k['ua:platform'] ?? null);
}

// Linux caps one environment string at 128 KiB (settings/launcher.json
// launch.env.why_chunks): a large value goes out as NAME_1..N in order.
// Chunked by code point, as the Python and Go clients do, so no chunk ends
// in half a surrogate pair.
const CONFIG_CHUNK_CHARS = 30000;
function chunkEnv(raw, name) {
  const cps = [...raw];
  if (cps.length <= CONFIG_CHUNK_CHARS) return { [name]: raw };
  const out = {};
  for (let i = 0, n = 1; i < cps.length; i += CONFIG_CHUNK_CHARS, n++) {
    out[`${name}_${n}`] = cps.slice(i, i + CONFIG_CHUNK_CHARS).join('');
  }
  return out;
}

// Every CAMOU_* of the parent dropped first (a stale CAMOU_CONFIG_1 would
// otherwise win) and its FONTCONFIG_FILE (a host conf under a Windows claim is
// a tell), then config/preset/strict set.
function buildEnv({ config, preset, strict, fontconfig } = {}, base = process.env) {
  effectiveKeys(config, preset);
  const env = {};
  for (const [k, v] of Object.entries(base)) if (!k.startsWith('CAMOU_') && k !== 'FONTCONFIG_FILE') env[k] = v;
  if (config != null) Object.assign(env, chunkEnv(asJson(config), 'CAMOU_CONFIG'));
  if (preset != null) Object.assign(env, chunkEnv(asJson(preset), 'CAMOU_PRESET'));
  if (strict) env.CAMOU_CONFIG_STRICT = '1';
  if (fontconfig) env.FONTCONFIG_FILE = fontconfig;
  return env;
}

// Mirrors settings/launcher.json launch.fontconfig.files.
const FONTCONFIG_FILES = { Windows: 'settings/fontconfig/windows.conf', macOS: 'settings/fontconfig/macos.conf' };

// The FONTCONFIG_FILE for the claimed OS: the generated conf beside the
// bundled fonts dir (default: `fonts` beside the executable when present).
// Linux claim or no fonts dir: null. A fonts dir without its conf throws.
function fontconfigFor({ config, preset, fontsDir, executablePath } = {}) {
  const file = FONTCONFIG_FILES[claimedOs(config, preset)];
  if (!file) return null;
  let dir = fontsDir;
  if (!dir && executablePath) {
    const cand = path.join(path.dirname(path.resolve(String(executablePath))), 'fonts');
    if (fs.existsSync(cand) && fs.statSync(cand).isDirectory()) dir = cand;
  }
  if (!dir) return null;
  const conf = path.resolve(dir, '..', file);
  if (!fs.existsSync(conf)) throw new Error(`fonts dir ${dir} has no fontconfig ${file} beside it: ${conf}`);
  return conf;
}

// --accept-lang the effective keys imply (navigator.languages joined, else
// locale:tag; a preset's locale counts): without it a French config still
// sends en-US (measured).
function acceptLangOf(config, preset) {
  const c = effectiveKeys(config, preset);
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
  args = [], extensions = [], spkiList = [], fontsDir, ...options
} = {}) {
  const bad = Object.keys(options).filter((k) => FORBIDDEN_OPTIONS.has(k));
  if (bad.length) {
    throw new Error(`${JSON.stringify(bad)} must come through CAMOU_CONFIG, not the driver: `
      + 'a second emulation of the same surface fights the fork\'s value');
  }
  // A temp profile lives as long as the context; a failed launch removes it too.
  const dir = userDataDir || fs.mkdtempSync(path.join(os.tmpdir(), 'camoucrome-'));
  const remove = () => { if (!userDataDir) fs.rmSync(dir, { recursive: true, force: true }); };
  let ctx;
  try {
    ctx = await chromium.launchPersistentContext(dir, {
      executablePath: String(executablePath),
      headless,
      ignoreDefaultArgs: true,
      env: buildEnv({ config, preset, strict,
        fontconfig: fontconfigFor({ config, preset, fontsDir, executablePath }) }),
      args: buildArgs({ window, dpr, extra: args, headless, userDataDir: dir,
        acceptLang: acceptLangOf(config, preset), extensions, spkiList }),
      // Otherwise a 1280x720 viewport is emulated, fighting screen.* and the
      // window size.
      viewport: null,
      ...options,
    });
  } catch (e) {
    remove();
    throw e;
  }
  if (!userDataDir) ctx.on('close', remove);
  return ctx;
}

module.exports = { FORBIDDEN_OPTIONS, BASE_ARGS, SEED_KEYS, FONTCONFIG_FILES, buildEnv, buildArgs,
  acceptLangOf, claimedOs, fontconfigFor, perInstanceConfig, launch };
