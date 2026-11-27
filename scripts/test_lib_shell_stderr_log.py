"""lib_shell's per-process stderr log is removed when the process exits, an UNMEASURED exit (os._exit) included.

2026-11-27: 244 camoucrome_verify_stderr.<pid>.log files were left in the Windows host's %TEMP%; 4 held camoucfg
invariant lines, which print config values."""
import pathlib
import subprocess
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent
PLANT = "import lib_shell; open(lib_shell.STDERR_LOG, 'w').write('camoucfg: x'); print(lib_shell.STDERR_LOG, flush=True)"


@pytest.mark.parametrize("tail,rc", [("", 0), ("; lib_shell._mark_unmeasured('UNMEASURED x')", 3)])
def test_stderr_log_is_removed_at_exit(tail, rc):
    p = subprocess.run([sys.executable, "-c", PLANT + tail], cwd=SCRIPTS, capture_output=True, text=True, timeout=60)
    assert p.returncode == rc, p.stderr
    log = pathlib.Path(p.stdout.splitlines()[0])
    assert log.name.startswith("camoucrome_verify_stderr.")
    assert not log.exists(), log
