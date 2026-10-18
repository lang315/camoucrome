"""Timestamps that reach the repository come from a UTC clock (spec 2026-10-18 §6.5)."""
import datetime
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
LOCAL = [
    (re.compile(r"Get-Date\s+-Format|\(Get-Date\)\.ToString\(|\$\w+\.ToString\('yyyy"), "*.ps1"),
    (re.compile(r"datetime\.(?:datetime\.)?(?:now|today)\(\s*\)|time\.(?:localtime|strftime)\("), "*.py"),
]


def test_no_local_clock_formatting_in_scripts():
    bad = []
    for rx, glob in LOCAL:
        for f in sorted(HERE.rglob(glob)):
            if f.name.startswith("test_"):
                continue
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if rx.search(line) and "ToUniversalTime" not in line:
                    bad.append(f"{f.relative_to(HERE)}:{i}")
    assert bad == []


def test_run_stamp_is_utc():
    import measure_step2
    s = measure_step2.run_stamp()
    got = datetime.datetime.strptime(s, "%Y%m%d-%H%M%S").replace(tzinfo=datetime.timezone.utc)
    assert abs((datetime.datetime.now(datetime.timezone.utc) - got).total_seconds()) < 5
