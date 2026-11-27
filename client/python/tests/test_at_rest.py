"""What a launch leaves on disk, and what its error text carries (the #272 audit's
three client-side holes): owner-only profile dirs, the sweep of a killed
client's temp dirs, and the browser stderr redacted out of a launch error."""
import os
import pathlib
import subprocess
import sys
import tempfile
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import camoucrome  # noqa: E402
from camoucrome import atrest  # noqa: E402

posix = pytest.mark.skipif(os.name != "posix", reason="POSIX modes and SingletonLock")


@pytest.fixture(autouse=True)
def tmp_is_tempdir(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))


@pytest.fixture
def umask022():
    old = os.umask(0o022)
    yield
    os.umask(old)


class Ctx:
    def on(self, event, fn):
        pass

    def close(self):
        pass


class Chromium:
    def __init__(self, error=None):
        self.error = error

    def launch_persistent_context(self, user_data_dir, **kw):
        self.user_data_dir, self.kw = user_data_dir, kw
        if self.error:
            raise self.error
        return Ctx()


def pw(error=None):
    return type("PW", (), {"chromium": Chromium(error)})()


# 1. Profile dir mode.

@posix
def test_profile_seeds_creates_every_missing_dir_owner_only(tmp_path, umask022):
    udd = tmp_path / "a" / "b" / "udd"
    camoucrome.profile_seeds(str(udd))
    for d in (tmp_path / "a", tmp_path / "a" / "b", udd):
        assert oct(d.stat().st_mode & 0o777) == oct(0o700), d


@posix
def test_profile_seeds_leaves_an_existing_dir_mode_alone(tmp_path, umask022):
    udd = tmp_path / "udd"
    udd.mkdir(mode=0o755)
    camoucrome.profile_seeds(str(udd))
    assert oct(udd.stat().st_mode & 0o777) == oct(0o755)


@posix
def test_launch_temp_dirs_are_owner_only(umask022):
    p = pw()
    camoucrome.launch(p, "/x/chrome")
    for d in (p.chromium.user_data_dir, p.chromium.kw["env"]["BREAKPAD_DUMP_LOCATION"]):
        assert oct(os.stat(d).st_mode & 0o777) == oct(0o700), d


# 2. Stale temp dirs of a killed client.

def dead_pid():
    p = subprocess.Popen([sys.executable, "-c", ""])
    p.wait()  # reaped: the pid names no process
    return p.pid


def made(tmp_path, name, age=7200.0, lock_pid=None):
    d = tmp_path / name
    d.mkdir()
    (d / "Preferences").write_text('{"intl":{"accept_languages":"xx-YY"}}')
    if lock_pid is not None:
        os.symlink(f"somehost-{lock_pid}", d / "SingletonLock")
    t = time.time() - age
    os.utime(d, (t, t))
    return d


def test_temp_dirs_carry_the_clients_pid():
    p = pw()
    camoucrome.launch(p, "/x/chrome")
    pid = os.getpid()
    assert os.path.basename(p.chromium.user_data_dir).startswith(f"camoucrome-{pid}-")
    assert os.path.basename(p.chromium.kw["env"]["BREAKPAD_DUMP_LOCATION"]).startswith(f"camoucrome-crash-{pid}-")


def test_launch_sweeps_only_a_dead_clients_old_temp_dirs(tmp_path):
    dead = dead_pid()
    gone = [made(tmp_path, f"camoucrome-{dead}-abcd1234"),
            made(tmp_path, f"camoucrome-crash-{dead}-abcd1234")]
    kept = [made(tmp_path, f"camoucrome-{os.getpid()}-live"),           # this client: alive
            made(tmp_path, f"camoucrome-{dead}-young", age=60),        # too young
            made(tmp_path, "camoucrome-verify-abcd1234"),              # a script's prefix
            made(tmp_path, "camoucrome-abcd1234"),                     # the old, pid-less name
            made(tmp_path, f"camoucrome-{dead}-caller")]               # the caller's own profile
    if os.name == "posix":
        kept.append(made(tmp_path, f"camoucrome-{dead}-locked", lock_pid=os.getpid()))  # a browser still runs
        target = made(tmp_path, "elsewhere")
        os.symlink(target, tmp_path / f"camoucrome-{dead}-link")
        kept.append(target)
    (tmp_path / f"camoucrome-{dead}-file").write_text("x")
    camoucrome.launch(pw(), "/x/chrome", user_data_dir=str(tmp_path / f"camoucrome-{dead}-caller"))
    assert [d.name for d in gone if d.exists()] == []
    assert [d.name for d in kept if not (d / "Preferences").exists()] == []
    assert (tmp_path / f"camoucrome-{dead}-file").exists()
    if os.name == "posix":
        assert (tmp_path / f"camoucrome-{dead}-link").is_symlink()


def test_sweep_ignores_a_failure_to_remove(tmp_path, monkeypatch):
    made(tmp_path, f"camoucrome-{dead_pid()}-abcd1234")
    monkeypatch.setattr(atrest.shutil, "rmtree", lambda *a, **k: (_ for _ in ()).throw(OSError("busy")))
    camoucrome.launch(pw(), "/x/chrome")  # no raise


# 3. Browser stderr in the launch error.

class PlaywrightError(Exception):
    """playwright._impl._errors.Error's shape: message and stack beside args."""
    def __init__(self, message):
        self._message, self._stack = message, "Error: " + message + "\n    at x"
        super().__init__(message)

    @property
    def message(self):
        return self._message


CONFIG = {"navigator.platform": "Win32", "timezone:id": "Asia/Secretville",
          "navigator.hardwareConcurrency": 8, "ua:fullVersion": "157.0.8103.51",
          "navigator.languages": ["xq-ZZ", "xq"]}
PRESET = {"os": "Windows", "gpu": "ANGLE (Secret GPU 9000)"}
STDERR = "\n".join([
    "BrowserType.launch_persistent_context: Target page, context or browser has been closed",
    "Browser logs:",
    "<launching> /x/chrome --accept-lang=xq-ZZ,xq --user-data-dir=/p",
    "[pid=7][err] [7:7:ERROR:coherence_validator.cc(726)] camoucfg: invariant 'inv-1' violated. "
    "'navigator.platform' is 'Win32', which disagrees with 'ua:osInfo'. It should be 'MacIntel'. Not repaired: x",
    "[pid=7][err] [7:7:ERROR:coherence_validator.cc(707)] camoucfg: invariant 'inv-2' violated. "
    "'ua:fullVersion' is set but 'x.y' is not. It should be Mozilla/5.0 (Derived 1.2). Not repaired: x",
    "[pid=7][err] [7:7:ERROR:coherence_validator.cc(743)] camoucfg: 'navigator.hardwareConcurrency' is '8', out of range",
    "[pid=7][err] [7:7:WARNING:tz.cc(1)] camoucfg: timezone:id 'Asia/Secretville' invalid; falling back to UTC",
    "[pid=7][err] [7:7:WARNING:gpu.cc(1)] renderer ANGLE (Secret GPU 9000) chosen",
    "[pid=7][err] [7:7:WARNING:ua.cc(1)] camoucfg: 'ua:osInfo' is set but 'ua:platform' is not, so x",
])
SECRETS = ["Win32", "MacIntel", "Mozilla/5.0 (Derived 1.2)", "'8'", "Asia/Secretville", "157.0.8103.51",
           "xq-ZZ", "Secret GPU 9000"]
KEPT = ["invariant 'inv-1' violated", "but 'x.y' is not", "camoucfg: 'ua:osInfo' is set but 'ua:platform' is not, so x",
        "'navigator.hardwareConcurrency' is '<redacted>', out of range", "coherence_validator.cc(743)"]  # public names stay


def test_launch_error_has_the_configured_values_redacted_line_by_line():
    env = camoucrome.build_env(CONFIG, PRESET)
    with pytest.raises(PlaywrightError) as info:
        camoucrome.launch(pw(PlaywrightError(STDERR + "\n" + env["CAMOU_CONFIG"])), "/x/chrome",
                          config=CONFIG, preset=PRESET)
    e = info.value
    for text in (str(e), e.message, e._stack):
        assert [s for s in SECRETS + [env["CAMOU_CONFIG"]] if s in text] == []
    assert len(str(e).splitlines()) == len(STDERR.splitlines()) + 1
    assert [k for k in KEPT if k not in str(e)] == []


def test_redact_drops_chunked_config_and_preset_strings():
    big = {"k:big": "Q" * 70000}
    env = camoucrome.build_env(big, {"os": "Windows", "pad": "P" * 70000})
    assert "CAMOU_CONFIG_1" in env and "CAMOU_PRESET_1" in env
    out = atrest.redact(env["CAMOU_CONFIG_1"] + "\n" + env["CAMOU_PRESET_2"] + "\nQQQ", env)
    assert "Q" * 100 not in out and "P" * 100 not in out
