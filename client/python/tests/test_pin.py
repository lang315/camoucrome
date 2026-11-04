"""pin_cpu_cores (C3): the driver that spawns Chrome is pinned to N CPUs for the launch call, then restored.
The affinity calls are injected: this Mac has no affinity API, so no real pin is read back here."""
import asyncio
import pathlib
import sys
import tempfile
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import camoucrome  # noqa: E402
from camoucrome import pin  # noqa: E402

PID = 4242
ALLOWED = set(range(8))


@pytest.fixture(autouse=True)
def temp_dirs_under_tmp_path(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))


@pytest.fixture
def calls(monkeypatch):
    class Log(list):
        pass
    log = Log()
    state = {"mask": set(ALLOWED), "fail": None}

    def get(pid):
        return set(state["mask"])

    def set_(pid, cpus):
        if state["fail"]:
            raise OSError(state["fail"])
        log.append((pid, set(cpus)))
        state["mask"] = set(cpus)
    monkeypatch.setattr(pin, "get_mask", get)
    monkeypatch.setattr(pin, "set_mask", set_)
    log.state = state
    return log


def fake_pw(launch, aio=False):
    if aio:
        async def lpc(*a, **k):
            return launch(*a, **k)
    else:
        def lpc(*a, **k):
            return launch(*a, **k)
    transport = types.SimpleNamespace(_proc=types.SimpleNamespace(pid=PID))
    return types.SimpleNamespace(
        chromium=types.SimpleNamespace(launch_persistent_context=lpc),
        _impl_obj=types.SimpleNamespace(_connection=types.SimpleNamespace(_transport=transport)))


class Ctx:
    def on(self, *a):
        pass

    def close(self):
        pass


def run(n, pw, **kw):
    return camoucrome.launch(pw, "/x/chrome", config={"navigator.hardwareConcurrency": n}, **kw)


def test_pins_to_n_of_the_allowed_cpus_then_restores(calls):
    seen = []
    pw = fake_pw(lambda *a, **k: seen.append(set(calls.state["mask"])) or Ctx())
    run(4, pw)
    assert seen[0] <= ALLOWED and len(seen[0]) == 4  # during the launch call
    assert calls == [(PID, seen[0]), (PID, ALLOWED)]


@pytest.mark.parametrize("n", [8, 12])
def test_no_pin_when_claim_reaches_the_allowed_cpus(calls, n):
    run(n, fake_pw(lambda *a, **k: Ctx()))
    assert calls == []


def test_no_pin_when_disabled(calls):
    run(2, fake_pw(lambda *a, **k: Ctx()), pin_cpu_cores=False)
    assert calls == []


def test_no_pin_without_a_claim(calls):
    camoucrome.launch(fake_pw(lambda *a, **k: Ctx()), "/x/chrome", config={})
    assert calls == []


def test_restored_when_the_launch_raises(calls):
    def boom(*a, **k):
        raise RuntimeError("no chrome")
    with pytest.raises(RuntimeError, match="no chrome"):
        run(2, fake_pw(boom))
    assert len(calls) == 2 and calls[-1] == (PID, ALLOWED)


def test_pin_failure_raises_naming_pid_and_error_and_does_not_launch(calls):
    calls.state["fail"] = "EPERM nope"
    launched = []
    with pytest.raises(RuntimeError, match=rf"{PID}.*EPERM nope"):
        run(2, fake_pw(lambda *a, **k: launched.append(1) or Ctx()))
    assert launched == []


def test_unfindable_driver_pid_raises(calls):
    pw = fake_pw(lambda *a, **k: Ctx())
    del pw._impl_obj
    with pytest.raises(RuntimeError, match="driver"):
        run(2, pw)


def test_async_pin_covers_the_awaited_launch_and_restores(calls):
    seen = []
    pw = fake_pw(lambda *a, **k: seen.append(len(calls.state["mask"])) or Ctx(), aio=True)

    async def go():
        return await run(3, pw)
    asyncio.run(go())
    assert seen == [3] and calls[-1] == (PID, ALLOWED)


def test_async_restored_when_the_launch_raises(calls):
    def boom(*a, **k):
        raise RuntimeError("no chrome")

    async def go():
        await run(3, fake_pw(boom, aio=True))
    with pytest.raises(RuntimeError, match="no chrome"):
        asyncio.run(go())
    assert calls[-1] == (PID, ALLOWED)


def test_restore_failure_after_a_good_launch_closes_the_browser(calls):
    closed = []

    class C(Ctx):
        def close(self):
            closed.append(1)
    real = pin.set_mask

    def set_(pid, cpus):
        if len(calls) == 1:  # the restore
            raise OSError("restore denied")
        real(pid, cpus)
    pin.set_mask = set_
    try:
        with pytest.raises(RuntimeError, match="restore"):
            run(2, fake_pw(lambda *a, **k: C()))
    finally:
        pin.set_mask = real
    assert closed == [1]


def test_partial_pin_is_rolled_back(monkeypatch):
    log = []

    def set_(pid, cpus):
        log.append(set(cpus))
        if len(log) == 1:
            raise OSError("half")
    monkeypatch.setattr(pin, "get_mask", lambda pid: set(ALLOWED))
    monkeypatch.setattr(pin, "set_mask", set_)
    with pytest.raises(RuntimeError, match="half"):
        run(2, fake_pw(lambda *a, **k: Ctx()))
    assert log[-1] == ALLOWED and len(log) == 2


def test_overlapping_threads_are_serialised(calls):
    import threading
    import time
    order = []

    def slow(name):
        def call():
            order.append("start " + name)
            time.sleep(0.05)
            order.append("end " + name)
        return call
    ts = [threading.Thread(target=pin.apply, args=(fake_pw(None), 2, slow(n))) for n in "ab"]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert order[0][6:] == order[1][4:] and order[2][6:] == order[3][4:]
    assert calls.state["mask"] == ALLOWED
