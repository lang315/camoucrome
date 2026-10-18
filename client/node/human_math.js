// client/node/human_math.js -- SP2d reference math, a port of
// client/python/camoucrome/human_math.py; settings/human_click_vectors.json pins both.
'use strict';
const M64 = (1n << 64n) - 1n;
const SALT = { hold: 0x686F6C64n, dwell: 0x6477656C6Cn, offset: 0x6F6666736574n };

function splitmix64(x) {
  let z = (x + 0x9E3779B97F4A7C15n) & M64;
  z = ((z ^ (z >> 30n)) * 0xBF58476D1CE4E5B9n) & M64;
  z = ((z ^ (z >> 27n)) * 0x94D049BB133111EBn) & M64;
  return z ^ (z >> 31n);
}

function profileScale(seed, salt) {
  if (seed === null || seed === undefined) return 1.0;
  const u = Number(splitmix64((BigInt(seed) ^ SALT[salt]) & M64) >> 11n) * 2 ** -53;
  return Math.exp(Math.log(1.25) * (2 * u - 1));
}

function sampleKnots(knots, u) {
  const pos = Math.min(Math.max(u, 0), 1) * 20;
  const i = Math.min(Math.floor(pos), 19);
  return knots[i] + (pos - i) * (knots[i + 1] - knots[i]);
}

function normalPair(r) {
  const u1 = r(), u2 = r();
  const rad = Math.sqrt(-2 * Math.log(1 - u1));
  return [rad * Math.cos(2 * Math.PI * u2), rad * Math.sin(2 * Math.PI * u2)];
}

function edgeEntry(w, h, uEdge, uAlong, uInset) {
  if (w < 2 || h < 2) return [0, 0];
  const inset = Math.min(uInset * 12, w / 2 - 1, h / 2 - 1);
  switch (Math.min(Math.floor(uEdge * 4), 3)) {
    case 0: return [uAlong * (w - 1), inset];
    case 1: return [w - 1 - inset, uAlong * (h - 1)];
    case 2: return [uAlong * (w - 1), h - 1 - inset];
    default: return [inset, uAlong * (h - 1)];
  }
}

function clickPosition(geo, last, model, scale, r, inner = 0.8, minSide = 4, redraws = 8) {
  const { w, h } = geo;
  if (w < minSide || h < minSide || geo.t || geo.n !== 1) return null;
  const cx = geo.x + w / 2, cy = geo.y + h / 2;
  let ax = 1, ay = 0;
  if (last) {
    const dx = cx - last[0], dy = cy - last[1], d = Math.hypot(dx, dy);
    if (d >= 1) { ax = dx / d; ay = dy / d; }
  }
  const wAlong = Math.abs(ax) * w + Math.abs(ay) * h;
  const wAcross = Math.abs(ay) * w + Math.abs(ax) * h;
  const sdAlong = (model.along.a + model.along.b * wAlong) * scale;
  const sdAcross = (model.across.a + model.across.b * wAcross) * scale;
  for (let k = 0; k < redraws; k++) {
    const [z1, z2] = normalPair(r);
    const px = cx + ax * z1 * sdAlong - ay * z2 * sdAcross;
    const py = cy + ay * z1 * sdAlong + ax * z2 * sdAcross;
    if (Math.abs(px - cx) <= inner * w / 2 && Math.abs(py - cy) <= inner * h / 2) {
      return [px - geo.x - geo.bl, py - geo.y - geo.bt];
    }
  }
  return null;
}

function visible(geo) {
  return geo.h > geo.vh ? geo.y >= 0 && geo.y < geo.vh : geo.y >= 0 && geo.y + geo.h <= geo.vh;
}

// Rounds half away from zero, like the reference's copysign(floor(|x| + 0.5)).
const roundAway = (x) => Math.sign(x) * Math.floor(Math.abs(x) + 0.5);

function nextBurst(geo, landing, burstKnots, pauseKnots, r, maxNotches = 60) {
  if (visible(geo)) return null;
  const delta = geo.y - landing * geo.vh;
  let total = Math.max(-maxNotches, Math.min(maxNotches, roundAway(delta / 100)));
  if (total === 0) total = delta > 0 ? 1 : -1;
  let size = Math.max(1, Math.floor(sampleKnots(burstKnots, r()) + 0.5));
  size = Math.min(size, Math.abs(total));
  return [Math.sign(total) * size, sampleKnots(pauseKnots, r())];
}

module.exports = { SALT, splitmix64, profileScale, sampleKnots, normalPair, edgeEntry, clickPosition, visible, nextBurst };
