"""SP2d reference math (spec §2, §4). Pure; every other language matches the
vectors this module emits (scripts/gen_click_vectors.py)."""
import math

M64 = (1 << 64) - 1
SALT = {"hold": 0x686F6C64, "dwell": 0x6477656C6C, "offset": 0x6F6666736574}


def splitmix64(x):
    z = (x + 0x9E3779B97F4A7C15) & M64
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & M64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & M64
    return z ^ (z >> 31)


def profile_scale(seed, salt):
    if seed is None:
        return 1.0
    u = (splitmix64((seed ^ SALT[salt]) & M64) >> 11) * 2.0 ** -53
    return math.exp(math.log(1.25) * (2 * u - 1))


def sample_knots(knots, u):
    pos = min(max(u, 0.0), 1.0) * 20
    i = min(int(pos), 19)
    return knots[i] + (pos - i) * (knots[i + 1] - knots[i])


def normal_pair(r):
    u1, u2 = r(), r()
    rad = math.sqrt(-2.0 * math.log(1.0 - u1))
    return rad * math.cos(2 * math.pi * u2), rad * math.sin(2 * math.pi * u2)


def edge_entry(w, h, u_edge, u_along, u_inset):
    if w < 2 or h < 2:
        return (0.0, 0.0)
    inset = min(u_inset * 12.0, w / 2 - 1, h / 2 - 1)
    edge = min(int(u_edge * 4), 3)
    if edge == 0:
        return (u_along * (w - 1), inset)
    if edge == 1:
        return (w - 1 - inset, u_along * (h - 1))
    if edge == 2:
        return (u_along * (w - 1), h - 1 - inset)
    return (inset, u_along * (h - 1))


def click_position(geo, last, model, scale, r, inner=0.8, min_side=4, redraws=8):
    w, h = geo["w"], geo["h"]
    if w < min_side or h < min_side or geo["t"] or geo["n"] != 1:
        return None
    cx, cy = geo["x"] + w / 2, geo["y"] + h / 2
    ax, ay = 1.0, 0.0
    if last is not None:
        dx, dy = cx - last[0], cy - last[1]
        d = math.hypot(dx, dy)
        if d >= 1:
            ax, ay = dx / d, dy / d
    w_along = abs(ax) * w + abs(ay) * h
    w_across = abs(ay) * w + abs(ax) * h
    sd_along = (model["along"]["a"] + model["along"]["b"] * w_along) * scale
    sd_across = (model["across"]["a"] + model["across"]["b"] * w_across) * scale
    for _ in range(redraws):
        z1, z2 = normal_pair(r)
        px = cx + ax * z1 * sd_along - ay * z2 * sd_across
        py = cy + ay * z1 * sd_along + ax * z2 * sd_across
        if abs(px - cx) <= inner * w / 2 and abs(py - cy) <= inner * h / 2:
            return (px - geo["x"] - geo["bl"], py - geo["y"] - geo["bt"])
    return None


def visible(geo):
    top, h, vh = geo["y"], geo["h"], geo["vh"]
    return 0 <= top < vh if h > vh else (top >= 0 and top + h <= vh)


def next_burst(geo, landing, burst_knots, pause_knots, r, max_notches=60):
    goal = min(landing * geo["vh"], max(0, geo["vh"] - geo["h"]))
    delta = geo["y"] - goal
    if visible(geo) and abs(delta) < 100:
        return None
    total = int(math.copysign(math.floor(abs(delta) / 100 + 0.5), delta))
    total = max(-max_notches, min(max_notches, total))
    if total == 0:
        total = 1 if delta > 0 else -1
    size = max(1, int(math.floor(sample_knots(burst_knots, r()) + 0.5)))
    size = min(size, abs(total))
    return (int(math.copysign(size, total)), sample_knots(pause_knots, r()))
