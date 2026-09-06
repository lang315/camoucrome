"""Verifies geo-ii watchPosition re-fire cadence (folded into sp4-geo).

sp4-geo delivers the synthesized position ONCE per arm then suppresses the
re-arm (camou_geo_delivered_), so a standing watchPosition fires once then goes
silent -- a tell (real Chrome re-fires a stationary watch at the WiFi poll
backoff 10s -> 2min -> 10min) and a functional gap (a page awaiting a 2nd
callback waits forever). geo-ii re-delivers on each re-arm at that cadence, with
a fresh timestamp and IDENTICAL coordinates (stationary; coordinate jitter is
deliberately NOT done -- it would imply motion a fixed position does not have).

RED (stock fork): GC-REFIRE/TIMESTAMP/STATIONARY/INTERVAL FAIL (only 1 fix ever
arrives); GC-ONESHOT already PASS. GREEN: all pass.

The 2min/10min backoff stages are too slow to test; this gate proves the re-fire
happens and its first interval (~10s = kDefaultPollingInterval) took effect.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell
import echo_server

# Un-cleared watchPosition; record every fix (timestamp, coords, wall-clock ms
# since registration) over a 14s window -- long enough for the first re-fire at
# ~10s. Then clear.
WATCH_CADENCE = r"""(async () => {
  return await new Promise((res) => {
    const fixes = [];
    const t0 = performance.now();
    const id = navigator.geolocation.watchPosition(
      (p)=>{ fixes.push({ts:p.timestamp, lat:p.coords.latitude,
                         lon:p.coords.longitude, wall:performance.now()-t0}); },
      (e)=>{ /* ignore errors, count only successes */ }, {});
    setTimeout(()=>{ navigator.geolocation.clearWatch(id); res({fixes}); }, 14000);
  });
})()"""

# getCurrentPosition is one-shot by spec; count callbacks over 12s to prove the
# re-fire logic is watch-only and never re-fires a one-shot request.
GET_ONESHOT = r"""(async () => {
  return await new Promise((res) => {
    let count = 0;
    navigator.geolocation.getCurrentPosition(
      (p)=>{ count++; }, (e)=>{ /* ignore */ }, {});
    setTimeout(()=>res({count}), 12000);
  });
})()"""

# Regression for the parallel-chain bug: a getCurrentPosition issued DURING a
# standing watch forces the entry reset (count=0, updating_=false) with the
# watch's re-fire still queued. If QueryNextPosition does not cancel the queued
# re-fire before posting, a SECOND self-perpetuating chain starts and the watch's
# effective cadence degrades to N x. Count the watch's success callbacks over 15s:
# a single chain fires at ~0 (watch), ~2s (the gCP delivery also notifies the
# watch) and ~12s (re-fire), i.e. <= 3; two chains add the un-cancelled ~10s fire
# -> 4+.
OVERLAP = r"""(async () => {
  return await new Promise((res) => {
    let watchCount = 0;
    const wid = navigator.geolocation.watchPosition(
      (p)=>{ watchCount++; }, (e)=>{ /* ignore */ }, {});
    setTimeout(() => {
      navigator.geolocation.getCurrentPosition(
        (p)=>{}, (e)=>{}, {});  // entry reset mid-watch
    }, 2000);
    setTimeout(()=>{ navigator.geolocation.clearWatch(wid); res({watchCount}); }, 15000);
  });
})()"""

CFG = json.dumps({"geolocation:latitude": 48.8566,
                  "geolocation:longitude": 2.3522,
                  "geolocation:accuracy": 25})


def run(expr):
    url, _, stop = echo_server.start([])
    try:
        v, e = lib_shell.session(CFG, [expr], navigate_to=url)
        if e:
            return None, e
        return v[0], None
    finally:
        stop()


results = {}
notes = []

w, e = run(WATCH_CADENCE)
if e or not isinstance(w, dict):
    for k in ("GC-REFIRE", "GC-TIMESTAMP", "GC-STATIONARY", "GC-INTERVAL"):
        results[k] = False
    notes.append(f"watch session error: {e or w}")
else:
    fixes = w.get("fixes", [])
    notes.append(f"watch fixes: {fixes}")
    results["GC-REFIRE standing watch fires >=2 times"] = len(fixes) >= 2
    if len(fixes) >= 2:
        f0, f1 = fixes[0], fixes[1]
        results["GC-TIMESTAMP 2nd fix has a fresh (later) timestamp"] = f1["ts"] > f0["ts"]
        results["GC-STATIONARY coords identical across fixes (no jitter)"] = (
            f1["lat"] == f0["lat"] and f1["lon"] == f0["lon"])
        gap = f1["wall"] - f0["wall"]
        results["GC-INTERVAL first re-fire ~10s (8-13s)"] = 8000 <= gap <= 13000
        notes.append(f"first re-fire gap: {gap:.0f}ms")
    else:
        results["GC-TIMESTAMP 2nd fix has a fresh (later) timestamp"] = False
        results["GC-STATIONARY coords identical across fixes (no jitter)"] = False
        results["GC-INTERVAL first re-fire ~10s (8-13s)"] = False

g, e = run(GET_ONESHOT)
if e or not isinstance(g, dict):
    results["GC-ONESHOT getCurrentPosition fires exactly once"] = False
    notes.append(f"get session error: {e or g}")
else:
    results["GC-ONESHOT getCurrentPosition fires exactly once"] = g.get("count") == 1
    notes.append(f"getCurrentPosition count: {g.get('count')}")

o, e = run(OVERLAP)
if e or not isinstance(o, dict):
    results["GC-NODOUBLE gCP during watch spawns no parallel re-fire chain"] = False
    notes.append(f"overlap session error: {e or o}")
else:
    wc = o.get("watchCount")
    # <=3 = single chain; 4+ = the parallel-chain regression.
    results["GC-NODOUBLE gCP during watch spawns no parallel re-fire chain"] = (
        isinstance(wc, int) and wc <= 3)
    notes.append(f"overlap watchCount: {wc}")

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for n in notes:
    print(f"      {n}")

sys.exit(0 if results and all(results.values()) else 1)
