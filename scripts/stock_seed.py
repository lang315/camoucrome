"""A stock Chrome control that has its variations seed, as a real user's stock Chrome has.

Stock gets its feature states (Topics, Protected Audience, Attribution Reporting, the XML parser, unload...) from a
seed it fetches on the first launch, about 12 to 30 s in. A fresh profile has none, so a stock arm on one measures
compiled defaults: the fork matches the seeded state since `finch-stable-defaults`
(measurements/2026-11-07-finch-feature-gap.md), and an unseeded control shows the difference as "unexpected" rows.

The one profile that fetched the seed is the TEMPLATE. It is closed with Browser.close, so the browser records a clean
exit and its crash streak stays 0 (a killed launch raises the streak, and the sixth launch on one profile falls back to
compiled defaults: variations safe mode, measured 2026-11-07). Every stock launch then starts on a COPY of three files
of the template, `Local State`, `Variations` and `VariationsSeedV2`, so it begins at streak 0 and a copy never carries
another launch's profile state (media device salt, cookies, storage): two stock profiles stay two profiles.

Shared by capture_host_oracle.py (the baseline) and measure_step2.py (the control arm)."""
import contextlib
import json
import pathlib
import shutil
import tempfile

SEED_FILES = ("Local State", "Variations", "VariationsSeedV2")
# On Navigator only while Fledge / AdInterestGroupAPI are on, which is stock's state without a seed.
UNSEEDED_MARKER = "joinAdInterestGroup"
SEED_PAGE = "<!doctype html><title>seed</title>"


class Unseeded(RuntimeError):
    """The stock control showed the compiled defaults: the run measured nothing about stock as users run it."""


def unseeded_modes(docs):
    """The modes (`{mode: oracle doc}`) whose Navigator still carries joinAdInterestGroup."""
    return [mode for mode, doc in docs.items() if UNSEEDED_MARKER in (doc.get("navProto") or [])]


def guard(on_navigator, where):
    """`on_navigator`: whether the page saw joinAdInterestGroup on Navigator.prototype. Raises Unseeded when it did."""
    if on_navigator:
        raise Unseeded(f"UNSEEDED: Protected Audience is on Navigator in {where}: the stock control has no variations "
                       "seed, so this is not a stock result")


def prime(winhost, exe, profile, headed, args=(), wait_ms=60000):
    """One launch of stock `exe` on `profile` that waits for the seed fetch, then closes the browser through
    Browser.close, so the profile is left with a clean exit (see the module docstring)."""
    return winhost.cdp_eval(SEED_PAGE, expression="1", args=args, headed=headed, profile=profile, wait_ms=wait_ms,
                            exe=exe, graceful_close=True)


def template_problem(profile):
    """None when `profile` holds a usable seeded template, else why not."""
    p = pathlib.Path(profile)
    missing = [n for n in SEED_FILES if not (p / n).is_file()]
    if missing:
        return "no " + ", ".join(missing)
    try:
        state = json.loads((p / "Local State").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"Local State unreadable: {exc}"
    if not state.get("variations_last_fetch_time"):
        return "Local State has no variations_last_fetch_time: the seed was never fetched"
    if (p / "VariationsSeedV2").stat().st_size == 0:
        return "VariationsSeedV2 is empty"
    if state.get("variations_crash_streak", 0) != 0:
        return f"variations_crash_streak is {state['variations_crash_streak']}, not 0 (the template was not closed cleanly)"
    if state.get("user_experience_metrics", {}).get("stability", {}).get("exited_cleanly") is not True:
        return "the template did not record a clean exit"
    return None


class SeededStock:
    """Primes one template, hands out a fresh seeded profile per stock launch, removes all of it on exit.

    `prime_fn(profile_dir)` runs the priming launch (production: stock_seed.prime through winhost); `workdir` is
    where the template and the copies live."""

    def __init__(self, prime_fn, workdir=None):
        self.prime_fn = prime_fn
        self.workdir = pathlib.Path(workdir) if workdir else None
        self.template = None
        self.copies = []
        self.primed = 0

    def __enter__(self):
        base = str(self.workdir) if self.workdir else None
        self._root = pathlib.Path(tempfile.mkdtemp(prefix="camou-stock-seed-", dir=base))
        self.template = self._root / "template"
        try:
            self.prime_fn(str(self.template))
            self.primed += 1
            why = template_problem(self.template)
            if why:
                raise Unseeded("UNSEEDED: the priming launch left no usable seeded template: " + why)
        except BaseException:
            self._cleanup()
            raise
        return self

    def __exit__(self, *exc):
        self._cleanup()
        return False

    def seed(self, dest):
        """Put the seed into the (empty or new) profile directory `dest`."""
        dest = pathlib.Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        for name in SEED_FILES:
            shutil.copy2(self.template / name, dest / name)
        return str(dest)

    def fresh_copy(self):
        """A new profile directory holding the seed and nothing else."""
        dest = pathlib.Path(tempfile.mkdtemp(prefix="copy-", dir=str(self._root)))
        self.copies.append(dest)
        return self.seed(dest)

    def drop(self, path):
        """Remove one copy as soon as its launch is over (a profile is tens of MB; a run makes about a hundred)."""
        shutil.rmtree(path, ignore_errors=True)
        self.copies = [c for c in self.copies if str(c) != str(path)]

    def _cleanup(self):
        shutil.rmtree(self._root, ignore_errors=True)
        self.copies = []


@contextlib.contextmanager
def seeded_stock(winhost, exe, args=(), headed=True, workdir=None):
    """SeededStock primed through `winhost.cdp_eval` on `exe` (the frozen stock build)."""
    with SeededStock(lambda prof: prime(winhost, exe, prof, headed, args), workdir) as s:
        yield s
