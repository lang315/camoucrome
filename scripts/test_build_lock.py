"""scripts/build_lock.sh: one build at a time on the build PC.

The WSL checkout and the Windows tree share one machine. A build in each at
once halves both and, on 2026-10-03, would have raced CI against an unattended
overnight Windows build that nothing on the WSL side could see. These run the
real script against a scratch lock path; the ninja check runs against a real
process whose command line looks like a build.

Run: python3 -m pytest -q scripts/test_build_lock.py
"""

import os
import pathlib
import subprocess
import time

import pytest

SCRIPT = pathlib.Path(__file__).with_name("build_lock.sh")


def lock(tmp_path, *args):
    env = dict(os.environ, CAMOU_BUILD_LOCK=str(tmp_path / "lock"))
    return subprocess.run(["bash", str(SCRIPT), *args], env=env,
                          capture_output=True, text=True)


def test_a_second_build_is_refused_and_told_who_holds_the_lock(tmp_path):
    first = lock(tmp_path, "acquire", "windows overnight")
    assert first.returncode == 0, first.stderr
    second = lock(tmp_path, "acquire", "ci run 7")
    assert second.returncode == 1
    assert "windows overnight" in second.stderr
    status = lock(tmp_path, "status")
    assert status.returncode == 1 and "windows overnight" in status.stdout


def test_only_the_owner_releases_the_lock(tmp_path):
    lock(tmp_path, "acquire", "windows overnight")
    stranger = lock(tmp_path, "release", "ci run 7")
    assert stranger.returncode == 1 and "windows overnight" in stranger.stderr
    assert lock(tmp_path, "release", "windows overnight").returncode == 0
    assert lock(tmp_path, "status").returncode == 0
    assert lock(tmp_path, "acquire", "ci run 7").returncode == 0


def test_a_running_ninja_refuses_the_lock(tmp_path):
    # exec -a puts the build's command line on a harmless process, which is
    # all pgrep -f can see of a real one.
    ninja = subprocess.Popen(["bash", "-c", 'exec -a "ninja -C out/Default" sleep 30'])
    try:
        time.sleep(0.3)
        refused = lock(tmp_path, "acquire", "windows overnight")
        assert refused.returncode == 1 and "ninja" in refused.stderr
        assert not (tmp_path / "lock").exists()
    finally:
        ninja.kill()
        ninja.wait()


@pytest.mark.parametrize("args", [[], ["acquire"], ["release"], ["frobnicate"]])
def test_usage_errors_exit_2(tmp_path, args):
    assert lock(tmp_path, *args).returncode == 2
