#!/usr/bin/env python3
"""Dev-only: KS equivalence of the C++ Cursory port vs upstream cursory 2.1.0.

  cursory_stats.py compare --cpp-dump FILE [--seed-base N]
  cursory_stats.py compare --bezier-dump  (RED control: old SP2b Bezier generator)

Run with a python that has `cursory==2.1.0` importable (scratch venv, never the
verify venv). The C++ dump comes from CURSORY_DUMP=path scripts/mac_cpp/run_cursory_tests.sh.
"""
import argparse
import bisect
import math
import random
import statistics
import sys

N_PAIRS = 200
M64 = (1 << 64) - 1
ASSERTED = ("duration", "efficiency", "peak_pos", "mean_speed")


def ks_statistic(a, b):
    a, b = sorted(a), sorted(b)
    d = 0.0
    for v in a + b:
        d = max(d, abs(bisect.bisect_right(a, v) / len(a) - bisect.bisect_right(b, v) / len(b)))
    return d


def critical(n, m):
    """5 % two-sample KS critical value."""
    return 1.36 * math.sqrt((n + m) / (n * m))


def features(samples):
    """samples: [(x, y, t_ms)]."""
    segs = [(x1 - x0, y1 - y0, t1 - t0) for (x0, y0, t0), (x1, y1, t1) in zip(samples, samples[1:])]
    lens = [math.hypot(dx, dy) for dx, dy, _ in segs]
    path = sum(lens)
    dur = samples[-1][2]
    speeds = [l / dt if dt > 0 else 0.0 for l, (_, _, dt) in zip(lens, segs)]
    k = speeds.index(max(speeds))
    turns = []
    for (ax, ay, _), (bx, by, _) in zip(segs, segs[1:]):
        if math.hypot(ax, ay) > 0 and math.hypot(bx, by) > 0:
            d = math.atan2(by, bx) - math.atan2(ay, ax)
            turns.append(abs(math.atan2(math.sin(d), math.cos(d))))
    straight = math.hypot(samples[-1][0] - samples[0][0], samples[-1][1] - samples[0][1])
    return {
        "duration": dur,
        "efficiency": straight / path if path else 1.0,
        "peak_pos": (k + 0.5) / len(segs),
        "mean_speed": path / dur if dur else 0.0,
        "curvature": statistics.fmean(turns) if turns else 0.0,
    }


def make_pairs():
    """Same LCG as cursory_unittest.cc (seed 7); order sx, sy, ex, ey."""
    s = 7

    def nxt(lo, hi):
        nonlocal s
        s = (s * 6364136223846793005 + 1442695040888963407) & M64
        return lo + (hi - lo) * (s >> 11) / 9007199254740992.0

    pairs = []
    while len(pairs) < N_PAIRS:
        sx, sy, ex, ey = nxt(0, 1920), nxt(0, 1080), nxt(0, 1920), nxt(0, 1080)
        if math.hypot(ex - sx, ey - sy) >= 5:
            pairs.append((sx, sy, ex, ey))
    return pairs


def read_dump(path):
    pairs, paths = [], []
    for line in open(path):
        line = line.strip()
        if line.startswith("# "):
            pairs.append(tuple(float(v) for v in line[2:].split(",")[1:]))
            paths.append([])
        elif line:
            _, _, x, y, t = line.split(",")
            paths[-1].append((float(x), float(y), int(t)))
    return pairs, paths


def upstream(pairs, seed_base):
    import cursory  # pinned wheel, scratch venv
    out = []
    for i, (sx, sy, ex, ey) in enumerate(pairs):
        pts, ts = cursory.generate_trajectory((sx, sy), (ex, ey), seed=seed_base + i)
        out.append([(x, y, t) for (x, y), t in zip(pts, ts)])
    return out


def bezier(pairs, seed_base):
    """Old SP2b HumanizeTrajectory (mouse_trajectories.cc): cubic Bezier via two random
    control points in the start/end box +-80, 24 steps, ease-out-quad sampling, total
    duration uniform [40,120] ms split by weights in [.5,1.5). Python RNG, not SplitMix64."""
    out = []
    for i, (sx, sy, ex, ey) in enumerate(pairs):
        r = random.Random(seed_base + i)
        l, rt, d, u = min(sx, ex) - 80, max(sx, ex) + 80, min(sy, ey) - 80, max(sy, ey) + 80
        c = [(sx, sy), (r.uniform(l, rt), r.uniform(d, u)), (r.uniform(l, rt), r.uniform(d, u)), (ex, ey)]
        pts = []
        for k in range(25):
            n = k / 24
            t = -n * (n - 2)
            b = [(1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3]
            pts.append((sum(w * p[0] for w, p in zip(b, c)), sum(w * p[1] for w, p in zip(b, c))))
        pts[0], pts[-1] = (sx, sy), (ex, ey)
        dur = r.uniform(40, 120)
        w = [r.uniform(.5, 1.5) for _ in range(24)]
        cum, t = 0.0, [0.0]
        for wi in w:
            cum += wi / sum(w) * dur
            t.append(cum)
        out.append([(x, y, tt) for (x, y), tt in zip(pts, t)])
    return out


def compare(cpp, ref, label):
    n = len(cpp)
    fc = [features(p) for p in cpp]
    fr = [features(p) for p in ref]
    crit = critical(n, len(fr))
    ok = True
    print(f"{label}: n={n}  5% critical={crit:.4f}")
    for k in ("duration", "efficiency", "peak_pos", "mean_speed"):
        d = ks_statistic([f[k] for f in fc], [f[k] for f in fr])
        v = "PASS" if d < crit else "FAIL"
        ok &= d < crit
        print(f"  {k:11s} n={n} D={d:.4f} crit={crit:.4f} {v}")
    mc, mr = (statistics.median(f["curvature"] for f in x) for x in (fc, fr))
    d = ks_statistic([f["curvature"] for f in fc], [f["curvature"] for f in fr])
    print(f"  curvature   REPORT-ONLY D={d:.4f} median cpp/ref={mc:.4f}/{mr:.4f}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["compare"])
    ap.add_argument("--cpp-dump")
    ap.add_argument("--bezier-dump", action="store_true", help="RED control: substitute old Bezier for the dump")
    ap.add_argument("--seed-base", type=int, default=0)
    a = ap.parse_args()
    pairs = make_pairs()
    if a.bezier_dump:
        cpp, label = bezier(pairs, a.seed_base + 1000), "bezier(old SP2b) vs upstream"
    else:
        dp, cpp = read_dump(a.cpp_dump)
        assert len(dp) == len(pairs) and all(
            max(abs(x - y) for x, y in zip(p, q)) < 1e-9 for p, q in zip(dp, pairs)), "pair mismatch"
        label = f"cpp port vs upstream (seed-base {a.seed_base})"
    ok = compare(cpp, upstream(pairs, a.seed_base), label)
    print("VERDICT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
