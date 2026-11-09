'use strict';
// Human-like input on a patchright Page: click, hold and type.
//
//   const { human } = require('camoucrome');
//   await human.click(page, '#buy');
//   await human.hold(page, '#hold-me', 1200);               // ms
//   await human.type(page, '#name', 'Hello, World!', { typos: true });
//
// The model is the one in client/go/rodclient (human.go, page.go) plus key rollover and typos. Every timing comes
// from human_params.js (generated from settings/human_input.json; lognormal, truncated by redrawing, never flat
// uniform). Input goes only through page.mouse.move/down/up and page.keyboard.down/up/insertText: no page JS, no
// Runtime.enable. The fork humanizes the mouse path browser-side; the keys are timed here.
//
// How it is built: a plan (a generator) yields the next input, wait or lookup; one small runner performs it and
// remembers what is down, so an error releases every key and the button. One seeded rng per page; `{ rng }`
// replaces it (tests). `rng` has random() in [0,1) and gauss(mu, sigma).

const P = require('./human_params');

const POLL_MS = 50;
const POLL_TRIES = 600; // 30 s, as rodclient's op timeout

// mulberry32, with a Box-Muller normal.
function makeRng(seed) {
  let a = seed >>> 0;
  const random = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return { random, gauss: (mu, sigma) => mu + sigma * Math.sqrt(-2 * Math.log(1 - random())) * Math.cos(2 * Math.PI * random()) };
}

// median*exp(sigma*N(0,1)) inside [lo, hi] by redrawing.
function lognormal(rng, median, sigma, lo, hi) {
  for (let i = 0; i < 32; i++) {
    const d = median * Math.exp(sigma * rng.gauss(0, 1));
    if (d >= lo && d <= hi) return d;
  }
  return median;
}

const dwell = (rng) => lognormal(rng, P.dwellMedianMs, P.dwellSigma, P.dwellMinMs, P.dwellMaxMs);
const isPunct = (c) => /\s/u.test(c) || /[\p{P}\p{S}]/u.test(c);

// keyDown to keyDown for the pair: the digraph median when the table has it, else the overall one.
function flight(rng, prev, next) {
  const tok = (c) => (c === ' ' ? 'space' : c.toLowerCase());
  const k = tok(prev) + tok(next);
  const med = Object.hasOwn(P.digraphFlightMs, k) ? P.digraphFlightMs[k] : P.flightMedianMs;
  let d = lognormal(rng, med, P.flightSigma, P.flightMinMs, P.flightMaxMs);
  if (isPunct(prev)) d *= P.flightAfterPunct;
  const nk = us(next);
  if (nk && nk[1]) d *= P.flightBeforeShift;
  if (/\s/u.test(prev) && !/\s/u.test(next) && rng.random() < P.pauseChance) {
    d += lognormal(rng, P.pauseMedianMs, P.pauseSigma, P.pauseMinMs, P.pauseMaxMs);
  }
  return d;
}

// US layout
const SHIFTED = ')!@#$%^&*(' + '_+{}|:"<>?~';
const BASE = '0123456789' + "-=[]\\;',./`";
const SHIFT_TO_BASE = new Map([...SHIFTED].map((c, i) => [c, BASE[i]]));
for (const c of 'ABCDEFGHIJKLMNOPQRSTUVWXYZ') SHIFT_TO_BASE.set(c, c.toLowerCase());
const BASE_TO_SHIFT = new Map([...SHIFT_TO_BASE].map(([s, b]) => [b, s]));

// [Playwright key, needs Shift] for a rune on a US layout; null for runes off it.
function us(ch) {
  if (ch === '\r' || ch === '\n') return ['Enter', false];
  if (ch === '\t') return ['Tab', false];
  if (ch.length === 1 && ch >= ' ' && ch <= '~') return [ch, SHIFT_TO_BASE.has(ch)];
  return null;
}
const phys = (ch) => SHIFT_TO_BASE.get(ch) ?? ch;

const ROWS = [['`1234567890-=', 0], ['qwertyuiop[]\\', 1.5], ["asdfghjkl;'", 1.75], ['zxcvbnm,./', 2.25]];
const NEIGHBOURS = (() => {
  const pos = new Map();
  ROWS.forEach(([row, off], r) => [...row].forEach((c, i) => pos.set(c, [r, off + i])));
  const out = new Map();
  for (const [c, [r, x]] of pos) {
    out.set(c, [...pos].filter(([o, [r2, x2]]) => o !== c && Math.abs(r2 - r) <= 1 && Math.abs(x2 - x) < (r2 === r ? 1.01 : 1.0)).map(([o]) => o));
  }
  for (const c of 'vbn') out.get(c).push(' '); // the space bar sits under these
  out.set(' ', ['v', 'b', 'n']);
  return out;
})();

// A US-QWERTY neighbour of ch (same row or adjacent row, same Shift state), or null.
function neighbour(rng, ch) {
  const shifted = SHIFT_TO_BASE.has(ch);
  const cands = (NEIGHBOURS.get(phys(ch)) ?? []).map((n) => (shifted ? BASE_TO_SHIFT.get(n) : n)).filter((c) => c && c !== ch);
  return cands.length ? cands[Math.floor(rng.random() * cands.length)] : null;
}

// A character a typo may touch or sweep into a run: a US key that is not Enter or Tab.
function plain(ch) {
  const k = us(ch);
  return k !== null && k[0] !== 'Enter' && k[0] !== 'Tab';
}

// The keys to press, in order. A stroke is { ch, key, shifted, kind: 'key'|'insert'|'bs', gap }; gap names a
// special wait before it ('notice', 'retype').
function strokes(rng, text, typos) {
  const chars = [];
  for (const c of text) {
    if (c === '\n' && chars.at(-1) === '\r') continue; // CRLF is one Enter
    chars.push(c);
  }
  const stroke = (ch, gap = null) => {
    const k = us(ch);
    return { ch, key: k ? k[0] : null, shifted: !!(k && k[1]), kind: k ? 'key' : 'insert', gap };
  };
  const out = [];
  for (let i = 0; i < chars.length;) {
    const c = chars[i];
    if (typos && plain(c) && rng.random() < P.typoRate) {
      const wrong = neighbour(rng, c);
      if (wrong) {
        let r = rng.random(); let n = 1;
        for (const p of P.typoRunLenProbs.slice(0, -1)) { if (r < p) break; r -= p; n++; }
        const run = [c];
        while (run.length < n && i + run.length < chars.length && plain(chars[i + run.length])) run.push(chars[i + run.length]);
        out.push(stroke(wrong), ...run.slice(1).map((x) => stroke(x)));
        run.forEach((_, j) => out.push({ ch: '', key: 'Backspace', shifted: false, kind: 'bs', gap: j === 0 ? 'notice' : null }));
        run.forEach((x, j) => out.push(stroke(x, j === 0 ? 'retype' : null)));
        i += run.length;
        continue;
      }
    }
    out.push(stroke(c));
    i++;
  }
  return out;
}

// The timed keyboard script for text: [[ms, [op, arg]]] in time order, op 'kdown' | 'kup' | 'insert'.
// Times are absolute from the first stroke. At most 2 typed keys are down at once (Shift is a modifier, not
// counted); a keyUp is never before its keyDown plus the dwell; rollover sends the next keyDown before the previous
// keyUp (plain keys, no Shift change, never insertText or Backspace, never the same physical key).
function planType(rng, text, typos = false) {
  const ss = strokes(rng, text, typos);
  const ev = []; // [time, prio, seq, op]: ups before downs at the same time
  const add = (t, op) => ev.push([t, op[0] === 'kup' ? 0 : 1, ev.length, op]);
  const ln = (m, s, lo, hi) => lognormal(rng, m, s, lo, hi);
  let prev = null;
  let prevDown = 0; let prevUp = 0; let prev2Up = 0; let shUp = 0;
  let shift = false;
  ss.forEach((s, k) => {
    const { ch, key, shifted, kind, gap } = s;
    let roll = false;
    let t;
    if (prev === null) t = 0;
    else if (gap === 'notice') t = prevUp + ln(P.typoNoticeMedianMs, P.typoNoticeSigma, P.typoNoticeMinMs, P.typoNoticeMaxMs);
    else if (gap === 'retype') t = prevUp + ln(P.typoRetypeMedianMs, P.typoRetypeSigma, P.typoRetypeMinMs, P.typoRetypeMaxMs);
    else if (kind === 'bs') t = prevDown + ln(P.backspaceFlightMedianMs, P.backspaceFlightSigma, P.backspaceFlightMinMs, P.backspaceFlightMaxMs);
    else if (kind === 'key' && prev.kind === 'key' && prev.shifted === shifted && phys(prev.ch) !== phys(ch) && rng.random() < P.rolloverChance) {
      const ov = ln(P.rolloverOverlapMedianMs, P.rolloverOverlapSigma, P.rolloverOverlapMinMs, P.rolloverOverlapMaxMs);
      t = Math.max(prevUp - ov, prevDown + 10);
      roll = true;
    } else t = prevDown + flight(rng, prev.ch, ch);
    if (!roll && prev !== null) t = Math.max(t, prevUp); // keys do not overlap unless rolled
    t = Math.max(t, prev2Up); // never a third key down
    if (kind === 'key' && shifted) {
      if (!shift) {
        const lead = ln(P.shiftLeadMedianMs, P.shiftLeadSigma, P.shiftLeadMinMs, P.shiftLeadMaxMs);
        t = Math.max(t, Math.max(prevUp, shUp) + lead);
        add(t - lead, ['kdown', 'Shift']);
        shift = true;
      }
    } else t = Math.max(t, shUp);
    let up;
    if (kind === 'insert') {
      add(t, ['insert', ch]);
      up = t;
    } else {
      const d = kind === 'bs' ? ln(P.backspaceDwellMedianMs, P.backspaceDwellSigma, P.backspaceDwellMinMs, P.backspaceDwellMaxMs) : dwell(rng);
      up = t + d;
      add(t, ['kdown', key]);
      add(up, ['kup', key]);
    }
    const nx = ss[k + 1];
    if (shift && !(nx && nx.kind === 'key' && nx.shifted)) {
      shUp = Math.max(up, prevUp) + ln(P.shiftReleaseMedianMs, P.shiftReleaseSigma, P.shiftReleaseMinMs, P.shiftReleaseMaxMs);
      add(shUp, ['kup', 'Shift']);
      shift = false;
    }
    prev2Up = prevUp; prevUp = up; prevDown = t; prev = s;
  });
  ev.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
  return ev.map(([t, , , op]) => [t, op]);
}

// Plans yield ['sleep', ms] | ['scroll'|'box'|'focus', selector] | ['viewport'] | ['move', x, y] | ['down'] | ['up'] |
// ['kdown'|'kup'|'insert', arg]; the runner sends back a lookup's result.
const states = new WeakMap();
function stateOf(page, rng) {
  let st = states.get(page);
  if (!st) { st = { rng: rng ?? makeRng(Math.floor(Math.random() * 2 ** 32)), moved: false }; states.set(page, st); }
  else if (rng) st.rng = rng;
  return st;
}

function axis(rng, lo, hi) {
  const c = (lo + hi) / 2; const w = hi - lo;
  if (w < P.clickMinBox) return c;
  for (let i = 0; i < 32; i++) {
    const v = c + rng.gauss(0, 1) * w * P.clickSpread;
    if (Math.abs(v - c) <= P.clickInner * w) return v;
  }
  return c;
}

function startPoint(rng, vp) {
  let hx = 300; let hy = 200;
  if (vp) {
    if (Math.floor(vp.width / 2) > 0 && Math.floor(vp.width / 2) < hx) hx = Math.floor(vp.width / 2);
    if (Math.floor(vp.height / 2) > 0 && Math.floor(vp.height / 2) < hy) hy = Math.floor(vp.height / 2);
  }
  const lx = Math.min(50, Math.floor(hx / 2)); const ly = Math.min(50, Math.floor(hy / 2));
  const pick = (lo, hi) => lo + Math.floor(rng.random() * (hi - lo + 1));
  return [pick(lx, hx), pick(ly, hy)];
}

// Find, scroll into view, make the first-move seed if needed, move to a press point, settle.
function* approach(st, selector) {
  yield ['scroll', selector];
  let box;
  for (let i = 0; ; i++) {
    if (i === POLL_TRIES) throw new Error(`camoucrome.human: ${JSON.stringify(selector)} has no box`);
    box = yield ['box', selector];
    if (box && box.width > 0 && box.height > 0) break;
    yield ['sleep', POLL_MS];
  }
  if (!st.moved) {
    const [x0, y0] = startPoint(st.rng, yield ['viewport']);
    yield ['move', x0, y0];
    st.moved = true;
  }
  const x = axis(st.rng, box.x, box.x + box.width);
  const y = axis(st.rng, box.y, box.y + box.height);
  yield ['move', x, y];
  yield ['sleep', lognormal(st.rng, P.settleMedianMs, P.settleSigma, P.settleMinMs, P.settleMaxMs)];
  return [x, y];
}

function* clickPlan(st, selector) {
  yield* approach(st, selector);
  yield ['down'];
  yield ['sleep', lognormal(st.rng, P.clickHoldMedianMs, P.clickHoldSigma, P.clickHoldMinMs, P.clickHoldMaxMs)];
  yield ['up'];
}

function* holdPlan(st, selector, ms) {
  const [x, y] = yield* approach(st, selector);
  yield ['down'];
  let left = ms;
  while (left > 0) {
    const w = Math.min(left, lognormal(st.rng, P.tremorMedianMs, P.tremorSigma, P.tremorMinMs, P.tremorMaxMs));
    yield ['sleep', w];
    left -= w;
    if (left > 0) {
      const j = () => Math.max(-P.tremorPx, Math.min(P.tremorPx, st.rng.gauss(0, 1) * P.tremorSigmaPx));
      const dx = j(); const dy = j();
      yield ['move', x + dx, y + dy];
    }
  }
  yield ['up']; // the mouse is where the last tremor move left it
}

function* typePlan(st, selector, text, typos) {
  yield ['focus', selector];
  let now = 0;
  for (const [t, op] of planType(st.rng, text, typos)) {
    if (t > now) { yield ['sleep', t - now]; now = t; }
    yield op;
  }
}

const loc = (page, sel) => page.locator(sel).first();
const calls = {
  move: (p, x, y) => p.mouse.move(x, y),
  down: (p) => p.mouse.down(),
  up: (p) => p.mouse.up(),
  kdown: (p, k) => p.keyboard.down(k),
  kup: (p, k) => p.keyboard.up(k),
  insert: (p, s) => p.keyboard.insertText(s),
  scroll: (p, sel) => loc(p, sel).scrollIntoViewIfNeeded(),
  box: (p, sel) => loc(p, sel).boundingBox(),
  focus: (p, sel) => loc(p, sel).focus(),
};

const realSleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function run(page, plan, sleep = realSleep) {
  const keys = []; let button = false;
  try {
    let res;
    for (;;) {
      const { value: op, done } = plan.next(res);
      if (done) return;
      res = undefined;
      if (op[0] === 'sleep') await sleep(op[1]);
      else if (op[0] === 'viewport') res = page.viewportSize();
      else {
        res = await calls[op[0]](page, ...op.slice(1));
        if (op[0] === 'kdown') keys.push(op[1]);
        else if (op[0] === 'kup') { const i = keys.lastIndexOf(op[1]); if (i >= 0) keys.splice(i, 1); }
        else if (op[0] === 'down') button = true;
        else if (op[0] === 'up') button = false;
      }
    }
  } catch (e) {
    for (const k of keys.reverse()) { try { await page.keyboard.up(k); } catch { /* the original error wins */ } }
    if (button) { try { await page.mouse.up(); } catch { /* ditto */ } }
    throw e;
  }
}

// Move to a press point in the inner 70% of the element, settle, press, hold tens of ms, release.
function click(page, selector, { rng, sleep } = {}) {
  return run(page, clickPlan(stateOf(page, rng), selector), sleep);
}

// Like click, but keep the button down for ms milliseconds, with a 1-2 px tremor; released at the last point.
function hold(page, selector, ms, { rng, sleep } = {}) {
  return run(page, holdPlan(stateOf(page, rng), selector, ms), sleep);
}

// Focus the element and type text with dwell, digraph flights, real Shift and key rollover. typos: true also makes
// occasional neighbour-key typos and corrects them with Backspace; the final text is exact.
function type(page, selector, text, { typos = false, rng, sleep } = {}) {
  return run(page, typePlan(stateOf(page, rng), selector, text, typos), sleep);
}

module.exports = { click, hold, type, planType, makeRng };
