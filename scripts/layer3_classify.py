"""Roadmap step 5: one page load -> one outcome, from what the page shows (spec 2026-10-24-step5-layer3-design.md, 4).

A page is a dict the harness reads from the DOM and the response (never a cookie value):
  title    document.title
  text     document.body.innerText, truncated
  html     document.documentElement.outerHTML, truncated
  frames   the src of every iframe and script
  cookies  cookie NAMES present
  ok       True when the site's own content marker (a CSS selector kept in the private site list) is on the page

classify(vendor, page) -> {"outcome": pass|challenge|block|unknown, "markers": [...], "cookies": [...]}.
The marker rules come from the vendors' public behaviour and are re-checked against fixtures saved at run time
(scripts/testdata/layer3). `markers` lists every vendor's rule that fired, so a site behind two vendors says which one
challenged; the outcome uses the site's own vendor first and any vendor's block/challenge second.
A challenge marker is decisive only while the site's own content (`ok`) is absent: a widget or script on a real page
(a Turnstile login form) stays in `markers` as context but the outcome is pass. A block marker is decisive regardless."""
import re

# (name, field, regex, severity) -- severity block outranks challenge.
RULES = {
    "cloudflare": [
        ("title-just-a-moment", "title", r"^\s*Just a moment", "challenge"),
        ("challenge-form", "html", r'id=["\']challenge-form["\']', "challenge"),
        ("turnstile", "html", r"cf-turnstile", "challenge"),
        ("challenge-frame", "frames", r"challenges\.cloudflare\.com", "challenge"),
        ("checking-browser", "text", r"Checking your browser|Verify you are human", "challenge"),
        ("title-attention-required", "title", r"Attention Required! \| Cloudflare", "block"),
        ("blocked-text", "text", r"Sorry, you have been blocked|Error 1020", "block"),
    ],
    "datadome": [
        ("captcha-delivery-frame", "frames", r"captcha-delivery\.com", "challenge"),
    ],
    "akamai": [
        ("cpt-container", "html", r"sec-if-cpt-container|sec-cpt", "challenge"),
        ("access-denied", "title", r"^\s*Access Denied", "block"),
        ("reference-number", "text", r"Reference #\d+\.[0-9a-f]+", "block"),
    ],
    "perimeterx": [
        ("px-captcha", "html", r'id=["\']px-captcha["\']', "challenge"),
        ("press-and-hold", "text", r"Press (&|and) Hold", "challenge"),
        ("px-denied", "text", r"Access to this page has been denied", "block"),
        ("px-frame", "frames", r"captcha\.px-cloud\.net", "challenge"),
    ],
}
# Cookie names recorded for context only (is the sensor active); never an outcome, never a value.
COOKIE_NAMES = re.compile(r"^(cf_clearance|__cf_bm|datadome|_abck|bm_sz|ak_bmsc|_px3|_pxhd|_pxvid)$")


def _field(page, name):
    v = page.get(name) or ""
    return "\n".join(v) if isinstance(v, (list, tuple)) else str(v)


def classify(vendor, page):
    fired = []  # (vendor, name, severity)
    for v, rules in RULES.items():
        for name, field, rx, sev in rules:
            if re.search(rx, _field(page, field), re.I):
                fired.append((v, name, sev))
    own = [f for f in fired if f[0] == vendor]
    pool = own or fired  # a vendor we did not expect may still be the one challenging
    sevs = {f[2] for f in pool}
    if "block" in sevs:
        outcome = "block"
    elif page.get("ok"):
        outcome = "pass"
    elif "challenge" in sevs:
        outcome = "challenge"
    else:
        outcome = "unknown"
    return {"outcome": outcome, "markers": [f"{v}:{n}" for v, n, _ in fired],
            "cookies": sorted(c for c in (page.get("cookies") or []) if COOKIE_NAMES.match(c))}


def combine(first, second):
    """Two stages -> one run. Challenged at either stage counts; pass needs both."""
    outs = [first["outcome"], second["outcome"]]
    if "block" in outs:
        return "block"
    if "challenge" in outs:
        return "challenge"
    return "pass" if outs == ["pass", "pass"] else "unknown"


def challenged(outcome):
    return outcome in ("challenge", "block")
