"""Row judges of the CDP footprint harness. Pure: no browser, no I/O."""
PASS, FAIL, UNMEASURED = "PASS", "FAIL", "UNMEASURED"
CLASS = {"L1": 1, "L2": 1, "L3": 3, "L4": 2, "L5a": 3, "L5b": 3, "L6": 2, "L7": 3, "L8": 1}
ARMS = ("tdp", "tdp-main", "red")
_MIN_BATCHES = 9
_NEEDS_NONE = {"L1", "L2", "L4", "L6", "L8"}
_TEXT = {"L5a": "camou footprint", "L5b": "Tiếng Việt có dấu"}
_CLICK_TYPES = ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]
_CLICK_DETAIL = [0, 1, 0, 1, 1]  # as sp2b-4


def judge_timing(base, arm):
    if len(base) < _MIN_BATCHES or len(arm) < _MIN_BATCHES:
        return UNMEASURED
    return FAIL if max(arm) < min(base) or max(base) < min(arm) else PASS


def judge_flag(base, arm):
    return FAIL if base != arm else PASS


def judge_trap(callers):
    return FAIL if callers else PASS


def judge_keys(events, text):
    if not events:
        return UNMEASURED
    for c in text:
        want = ["keydown", "beforeinput", "input", "keyup"]
        if c.isprintable():
            want.insert(1, "keypress")
        it = iter(e["type"] for e in events if c in (e.get("key"), e.get("data")))
        if not all(w in it for w in want):  # `in` consumes the iterator: ordered subsequence
            return FAIL
    return PASS


def judge_click(fields):
    if not fields:
        return UNMEASURED
    if [f["type"] for f in fields] != _CLICK_TYPES:
        return FAIL
    if [f["detail"] for f in fields] != _CLICK_DETAIL:
        return FAIL
    if not all(f["isTrusted"] for f in fields):
        return FAIL
    if len({f["screenX"] - f["clientX"] for f in fields}) != 1:
        return FAIL
    return PASS


def _verdict(row, none, arm):
    if arm is None or (row in _NEEDS_NONE and none is None):
        return UNMEASURED
    if row in _TEXT:
        return judge_keys(arm["L5"][row[-1]], _TEXT[row])
    if row == "L7":
        return judge_click(arm["L7"])
    if row == "L3":
        return judge_trap(arm["L3"])
    if row in ("L2", "L4", "L6"):
        return judge_timing(none[row], arm[row])
    return judge_flag(none[row], arm[row])


def judge_row(row, results):
    # row "L5a" reads results[arm]["L5"]["a"]; every other row reads results[arm][row]
    none = results.get("none")
    if row in _NEEDS_NONE and none is None:
        return {a: UNMEASURED for a in ARMS}
    out = {a: _verdict(row, none, results.get(a)) for a in ARMS}
    if out["red"] != FAIL:
        return {a: UNMEASURED for a in ARMS}
    return out


def judge_observer(base, arm):
    if not base["groups"] or not arm["groups"]:
        return ["UNMEASURED empty summary"]
    b, a = base["groups"], arm["groups"]
    lines = [f"+{g}" for g in sorted(set(a) - set(b))]
    lines += [f"-{g}" for g in sorted(set(b) - set(a))]
    if base["ajax_bz"] != arm["ajax_bz"]:
        lines.append(f"ajax_bz {base['ajax_bz']}->{arm['ajax_bz']}")
    return lines


def render(table):
    arms = ["none", *ARMS]
    lines = ["| row | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    fails = []
    for row, v in table.items():
        lines.append(f"| {row} | " + " | ".join(v.get(a, "") for a in arms) + " |")
        fails += [f"{row} {a} (class {CLASS.get(row, 'by hand')})" for a in arms if v.get(a) == FAIL]
    return "\n".join(lines + ["", "FAIL list:"] + (fails or ["none"]))
