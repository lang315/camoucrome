"""Row judges of the driver probes (L9 stacks during driver actions, H routed header order). Pure: no browser, no I/O."""
import re

from cdp_footprint_rows import FAIL, PASS, UNMEASURED

NA_CELL = "n/a"
EVENTS =("focus", "blur", "input", "keydown", "click", "mousedown", "pointerdown", "change", "select", "scroll")
# frames a stock user's event never has: driver sourceURLs, Playwright/Puppeteer utility scripts, eval frames
MARKERS = re.compile(r"pptr:|__playwright|__puppeteer|UtilityScript|sourceURL|\beval\b|extensions::|playwright", re.I)
_URL = re.compile(r"https?://127\.0\.0\.1:\d+/([\w.-]+)(\?[^\s):]*)?(:\d+){0,2}")


def norm_frame(frame):
    """A frame without host, port, query and line:col, so one page's frames compare across arms."""
    return _URL.sub(r"\1", frame).strip()


def _frames(rec):
    return [norm_frame(f) for f in rec["stack"].split("\n")[1:]]


def _sites(rec):
    return [norm_frame(s) for s in rec.get("sites") or []]


def extras(control, arm):
    """What the arm's fires of one event type hold that the control's never do: frames, callsites, a currentScript."""
    ok_f = {f for r in control for f in _frames(r)}
    ok_s = {s for r in control for s in _sites(r)}
    ok_c = {r.get("script") for r in control}
    out = []
    for r in arm:
        out += [f for f in _frames(r) if f not in ok_f or MARKERS.search(f)]
        out += ["site:" + s for s in _sites(r) if s not in ok_s or MARKERS.search(s)]
        if r.get("script") not in ok_c:
            out.append("currentScript")
    return sorted(set(out))


def judge_stack(control, arm):
    """control, arm: lists of fire records of one event type, or None / [] when nothing fired.
    Nothing fired is UNMEASURED, never PASS: an arm that fires no listener has no stack to read."""
    if not control or not arm:
        return UNMEASURED
    return FAIL if extras(control, arm) else PASS


# The action whose call a row measures. Other actions fire the same events as a side effect (a click focuses), so a
# cell counts only when its OWN action ran: a driver whose action is n/a or errored must not borrow a PASS from another.
OWNER = {"focus": "focus", "blur": "blur", "input": "type", "keydown": "type", "click": "click", "mousedown": "click",
         "pointerdown": "click", "change": "blur", "select": "select", "scroll": "scroll"}


def action_ok(acts, event):
    return str((acts or {}).get(OWNER[event], "")).startswith("ok:")


def judge_stack_row(event, results, acts=None, red="red", control="control"):
    """results: arm -> {event: [fires]} or None. acts: arm -> {action: status}; None = not gated (unit use).
    A cell whose owning action did not report ok: is UNMEASURED, and a control whose action did not run voids the row.
    The red arm must FAIL the row itself, else every arm is UNMEASURED."""
    ctl = (results.get(control) or {}).get(event)
    if acts is not None and not action_ok(acts.get(control), event):
        ctl = None
    out = {a: judge_stack(ctl, (r or {}).get(event)) for a, r in results.items() if a != control}
    if acts is not None:
        out = {a: (v if action_ok(acts.get(a), event) else UNMEASURED) for a, v in out.items()}
    if out.get(red) != FAIL:
        return {a: UNMEASURED for a in out}
    return out


def parse_request(raw):
    """(request line, [header names in wire order and case]) of one raw HTTP/1.1 request."""
    head = raw.split(b"\r\n\r\n", 1)[0].decode("latin-1").split("\r\n")
    return head[0], [h.split(":", 1)[0] for h in head[1:] if ":" in h]


def _uniform(samples):
    return all(s == samples[0] for s in samples)


def judge_headers(base, arm, added=None, required=None):
    """base, arm: lists of samples, each a header-name list (wire order, wire case). added: the one name the arm adds on
    purpose (compared case-insensitively and removed before the comparison). FAIL when the order, case or set differs.
    required: a name that must be on the wire in both and is NOT removed (the override-vs-raw-CDP compare).
    Samples that disagree among themselves, or too few, are UNMEASURED: no stable reference."""
    if not base or not arm or len(base) < 2 or len(arm) < 2 or not _uniform(base):
        return UNMEASURED, "no stable reference"
    if required and not all(landing(s, required) is not None for s in base):
        return UNMEASURED, f"reference lacks {required}"
    if required and not all(landing(s, required) is not None for s in arm):
        return FAIL, f"{required} missing from the wire: the override did not land"
    if added and not all(landing(s, added) is not None for s in arm):
        return FAIL, f"{added} missing from the wire: the override did not land"  # absence must not pass
    got = [[n for n in s if not (added and n.lower() == added.lower())] for s in arm]
    if not _uniform(got):
        return FAIL, "unstable: " + " | ".join(",".join(g) for g in got[:2])
    if got[0] == base[0]:
        return PASS, ""
    return FAIL, "base " + ",".join(base[0]) + " | arm " + ",".join(got[0])


def landing(names, added):
    """Index of the added header in the arm's list, for the report (None when absent)."""
    return next((i for i, n in enumerate(names) if n.lower() == added.lower()), None)
