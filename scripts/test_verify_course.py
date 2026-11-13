"""verify_course's vendored-CreepJS lock, without a browser."""
import os
import pathlib
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("CAMOU_CLIENT", str(HERE.parent))
import verify_course  # noqa: E402


def test_vendor_intact():
    assert verify_course.check_vendor(verify_course.CREEP_DIR) == []


def test_vendor_detects_edit(tmp_path):
    d = tmp_path / "creepjs"
    shutil.copytree(verify_course.CREEP_DIR, d)
    with open(d / "creep.js", "ab") as f:
        f.write(b"x")
    bad = verify_course.check_vendor(d)
    assert len(bad) == 1 and "creep.js" in bad[0]
