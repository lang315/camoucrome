"""Obstacle course: the fork against CreepJS and mutant (R) rows.

Only the vendored-CreepJS lock exists so far; the rows come in later tasks.
"""
import hashlib
import sys
from pathlib import Path

CREEP_DIR = Path(__file__).parent / "third_party" / "creepjs"


def check_vendor(d: Path) -> list[str]:
    """One string per file whose sha256 differs from, or is missing against, SHA256SUMS."""
    bad = []
    for line in (d / "SHA256SUMS").read_text().splitlines():
        want, name = line.split("  ", 1)
        p = d / name
        if not p.is_file():
            bad.append(f"{name}: missing")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != want:
            bad.append(f"{name}: sha256 differs from SHA256SUMS")
    return bad


def main() -> int:
    print("course not calibrated")
    return 2


if __name__ == "__main__":
    sys.exit(main())
