// client/node/human_click.js -- SP2d client side (spec §4): wheel into view,
// then click an off-centre point with scroll: 'none'. The dwell, hold and
// path are the browser's (humanize:enabled); this never passes `delay`.
'use strict';
const fs = require('fs');
const path = require('path');
const T = require('./click_tables');
const m = require('./human_math');

const state = new WeakMap();  // BrowserContext -> {scale, windows}
// Contexts launch() created with humanClick: true. The Frame.click wrapper is
// process-wide (one shared prototype); without this gate a single flagged
// launch would humanize every later context.
const bContexts = new WeakSet();
const last = new WeakMap();   // Page -> [x, y]
const PASS_THROUGH = ['position', 'force', 'trial'];
const GEOMETRY = new Function(`return ${T.geometryJS}`)();
const defaultSleep = (ms) => new Promise((r) => setTimeout(r, ms));

// B: human-path invocations, read by later tasks.
let hits = 0;
const wrapperHits = () => hits;

const UINT32_MAX = 2 ** 32 - 1;

// humanize:seed only when it is a real uint32: 0 is valid; bools, negatives,
// fractions, strings and anything else are treated as absent (scale 1.0).
function seedOf(eff) {
  const v = eff['humanize:seed'];
  return Number.isInteger(v) && v >= 0 && v <= UINT32_MAX ? v : null;
}

// The driver logs 'performing click action' once it dispatches the press;
// a retry after that line would double-click.
function maybeDelivered(text) {
  const performed = text.lastIndexOf('performing click action');
  if (performed < 0) return false;
  const retried = text.lastIndexOf('retrying click action');
  return retried < 0 || performed > retried;
}

// The first driver that honours Locator.evaluate's isolatedContext.
// patchright 1.62.1 ignores it and runs evaluate in the page's main world --
// a page-visible call the spec forbids.
const MIN_DRIVER = [1, 62, 3];
const versions = new WeakMap();  // driver Connection -> package version

// The driver's client objects share one Connection; a locator reaches it
// through its frame.
function connectionOf(obj) {
  if (!obj) return null;
  if (obj._connection) return obj._connection;
  if (obj._frame && obj._frame._connection) return obj._frame._connection;
  if (typeof obj.page === 'function') {
    try {
      const page = obj.page();
      if (page && page._connection) return page._connection;
    } catch (e) { /* a closed locator: nothing to gate */ }
  }
  return null;
}

// Version of the package that loaded the caller's client objects: the module
// in require.cache whose in-process Playwright root owns their connection.
function driverVersion(obj) {
  const conn = connectionOf(obj);
  if (!conn) return null;
  if (versions.has(conn)) return versions.get(conn);
  let version = null;
  for (const file of Object.keys(require.cache)) {
    const exp = require.cache[file].exports;
    const root = exp && exp.inprocess && exp.inprocess.playwright;
    if (root && root._connection === conn) { version = packageVersion(file); break; }
  }
  if (version !== null) versions.set(conn, version);
  return version;
}

// The nearest package.json above the defining module (patchright-core/lib/...).
function packageVersion(file) {
  for (let dir = path.dirname(file); ; dir = path.dirname(dir)) {
    try {
      const { version } = JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf8'));
      if (typeof version === 'string') return version;
    } catch (e) { /* no readable package.json here: keep walking */ }
    if (path.dirname(dir) === dir) return null;
  }
}

function atLeast(version, min) {
  const m = /^(\d+)\.(\d+)\.(\d+)/.exec(version);
  if (!m) return false;
  for (let i = 0; i < min.length; i++) {
    const n = Number(m[i + 1]);
    if (n !== min[i]) return n > min[i];
  }
  return true;
}

// An old or unidentifiable driver must not run the geometry; an object with no
// driver connection is not a driver object (a test double).
function supportsIsolation(obj) {
  if (!connectionOf(obj)) return true;
  const version = driverVersion(obj);
  return version !== null && atLeast(version, MIN_DRIVER);
}

async function geometry(target, timeout) {
  try {
    return await target.evaluate(GEOMETRY, undefined, { timeout, isolatedContext: true });
  } catch (e) {
    return null;  // any failure means: fall back to the stock click
  }
}

async function wheel(page, notches, windows, rand, sleep) {
  if (windows) return page.mouse.wheel(0, notches * 100);  // SP2c splits it into notches
  for (let i = 0; i < Math.abs(notches); i++) {
    await page.mouse.wheel(0, notches > 0 ? 100 : -100);
    await sleep(18 + 42 * rand());
  }
}

async function act(target, page, opts, st, rand, sleep, click) {
  if (PASS_THROUGH.some((k) => k in opts)) return click(opts);
  if (!supportsIsolation(target)) return click(opts);  // no evaluate on an old driver
  const timeout = opts.timeout;
  let geo = await geometry(target, timeout);
  if (!geo || geo.scroller !== 'document' || geo.x < 0 || geo.x + geo.w > geo.vw) return click(opts);
  st = st || { scale: 1, windows: false };
  if (!m.visible(geo)) {
    const pt = [geo.vw * (0.1 + 0.8 * rand()), geo.vh * (0.1 + 0.8 * rand())];
    await page.mouse.move(pt[0], pt[1]);
    last.set(page, pt);
    const landing = m.sampleKnots(T.landing, rand());
    let sent = 0, stuck = 0, prevSign = 0;
    while (true) {
      const burst = m.nextBurst(geo, landing, T.burst, T.pause, rand, T.maxNotches - sent);
      if (burst === null) break;
      if (sent >= T.maxNotches || stuck >= T.noProgressBursts) {
        if (m.visible(geo)) break;  // the page end: arrived as far as it can
        return click(opts);
      }
      await wheel(page, burst[0], st.windows, rand, sleep);
      sent += Math.abs(burst[0]);
      await sleep(burst[1]);
      const before = geo.y;
      geo = await geometry(target, timeout);
      if (!geo) return click(opts);
      const sign = burst[0] > 0 ? 1 : -1;
      if ((prevSign !== 0 && sign !== prevSign) || Math.abs(geo.y - before) < 1) {
        stuck += 1;  // a reversal is a bounce, not progress
      } else {
        stuck = 0;
      }
      prevSign = sign;
    }
  }
  const pos = m.clickPosition(geo, last.get(page) || null, T.offset, st.scale, rand);
  const extra = { scroll: 'none', ...(pos ? { position: { x: pos[0], y: pos[1] } } : {}) };
  const attemptTimeout = T.trialTimeoutMs;  // fixed: the first attempt's timeout, never the caller's
  const dir = geo.y + geo.h / 2 < geo.vh / 2 ? -1 : 1;  // away from a cover at the top
  for (let attempt = 0; attempt < 2; attempt++) {
    let result;
    try {
      result = await click({ ...opts, ...extra, timeout: attemptTimeout });
    } catch (e) {  // only a driver timeout is retried
      if (e.name !== 'TimeoutError') {
        // the click may already have been delivered: a second one would double-click
        throw e;
      }
      if (maybeDelivered(e.message)) {
        // the press was dispatched before the deadline: a retry would double-click
        throw e;
      }
      if (attempt === 1) return click(opts);
      await wheel(page, dir, st.windows, rand, sleep);  // a covered target: one corrective burst
      await sleep(200);
      continue;
    }
    if (pos) {
      const y = geo.y + geo.bt + pos[1] - (attempt === 1 ? 100 * dir : 0);  // the notch moved it
      last.set(page, [geo.x + geo.bl + pos[0], y]);
    }
    return result;
  }
}

async function humanClick(locator, opts = {}, rand = Math.random) {
  const page = locator.page();
  return act(locator, page, opts, state.get(page.context()), rand, defaultSleep, (o) => locator.click(o));
}

function installState(ctx, { effectiveKeys, claimedOs }, config, preset) {
  state.set(ctx, { scale: m.profileScale(seedOf(effectiveKeys(config, preset)), 'offset'),
    windows: claimedOs(config, preset) === 'Windows' });
}

async function install(ctx, helpers, config, preset) {
  installState(ctx, helpers, config, preset);
  bContexts.add(ctx);
  const page = ctx.pages()[0] || await ctx.waitForEvent('page');
  const proto = Object.getPrototypeOf(page.mainFrame());
  if (proto._camouHumanClick) return;
  const orig = proto.click;
  proto.click = async function click(selector, options = {}) {
    const ctx = this.page().context();
    const st = state.get(ctx);
    if (!bContexts.has(ctx) || PASS_THROUGH.some((k) => k in options)) return orig.call(this, selector, options);
    hits += 1;
    const first = this.locator(selector).first();
    return act(first, this.page(), options, st, Math.random, defaultSleep, (o) => orig.call(this, selector, o));
  };
  proto._camouHumanClick = true;
}

module.exports = { act, humanClick, install, installState, seedOf, wrapperHits, lastPoint: (page) => last.get(page),
  driverVersion, supportsIsolation };
