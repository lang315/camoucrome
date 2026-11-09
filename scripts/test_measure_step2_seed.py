"""measure_step2's stock arm launches on a seeded profile and refuses an unseeded one (stock_seed.py).
`camoucrome.launch` is a fake; no browser runs."""
import contextlib
import json
import pathlib
import sys
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import measure_step2 as ms  # noqa: E402
import stock_seed  # noqa: E402
from test_stock_seed import write_template  # noqa: E402


class FakeCtx:
    def __init__(self, join_on):
        self.closed = False
        self.pages = [types.SimpleNamespace(evaluate=lambda js: join_on if "joinAdInterestGroup" in js else None)]

    def close(self):
        self.closed = True


@pytest.fixture
def launcher(monkeypatch):
    seen = types.SimpleNamespace(calls=[], ctxs=[], join_on=False)

    def launch(pw, exe, **kw):
        seen.calls.append((exe, kw))
        ctx = FakeCtx(seen.join_on)
        seen.ctxs.append(ctx)
        return ctx

    monkeypatch.setitem(sys.modules, "camoucrome", types.SimpleNamespace(launch=launch))
    monkeypatch.setattr(ms.gpu_gate, "check", lambda *a: None)
    monkeypatch.setattr(ms.gpu_gate, "read_ctx", lambda ctx: None)
    return seen


@pytest.fixture
def seed(tmp_path, monkeypatch):
    with stock_seed.SeededStock(write_template, tmp_path) as s:
        monkeypatch.setattr(ms, "SEED", s)
        yield s


def test_every_stock_launch_gets_its_own_seeded_copy_that_is_removed_after(launcher, seed):
    stock = ms.Arm("control", "stock.exe", None, stock=True)
    dirs = []
    for _ in range(6):
        with ms.opened(None, stock, "headed"):
            d = pathlib.Path(launcher.calls[-1][1]["user_data_dir"])
            dirs.append(d)
            assert (d / "VariationsSeedV2").exists() and d != seed.template
        assert not d.exists()  # dropped when the launch ended
    assert len(set(dirs)) == 6 and seed.primed == 1
    assert all(c.closed for c in launcher.ctxs)


def test_an_unseeded_stock_launch_is_unmeasured_and_still_cleaned_up(launcher, seed):
    launcher.join_on = True  # joinAdInterestGroup on Navigator: no seed took effect
    stock = ms.Arm("control", "stock.exe", None, stock=True)
    with pytest.raises(stock_seed.Unseeded, match="UNSEEDED.*control/headless"):
        with ms.opened(None, stock, "headless"):
            pytest.fail("the body must not run on an unseeded stock")
    assert launcher.ctxs[0].closed and not pathlib.Path(launcher.calls[0][1]["user_data_dir"]).exists()


def test_a_callers_own_stock_profile_is_kept_and_still_guarded(launcher, seed, tmp_path):
    mine = tmp_path / "stab"
    seed.seed(mine)
    stock = ms.Arm("control", "stock.exe", None, stock=True)
    for _ in (1, 2):  # stability: one profile, two launches
        with ms.opened(None, stock, "headed", user_data_dir=str(mine)):
            assert launcher.calls[-1][1]["user_data_dir"] == str(mine)
    assert mine.exists()
    launcher.join_on = True
    with pytest.raises(stock_seed.Unseeded):
        with ms.opened(None, stock, "headed", user_data_dir=str(mine)):
            pass


def test_the_fork_arm_is_unchanged(launcher, monkeypatch):
    monkeypatch.setattr(ms, "SEED", None)  # the fork never touches the seed
    fork = ms.Arm("fork", "fork.exe", {"config": {"a": 1}, "launch": {}})
    launcher.join_on = True  # a fork with Protected Audience would be a finding, not an UNSEEDED run
    with ms.opened(None, fork, "headed"):
        assert launcher.calls[0][1]["user_data_dir"] is None
    assert launcher.ctxs[0].closed


def test_stability_seeds_the_stock_profile_once_before_its_two_launches(monkeypatch, tmp_path):
    seeded = []

    class S:
        def seed(self, d):
            seeded.append(pathlib.Path(d).exists())

    monkeypatch.setattr(ms, "SEED", S())
    reports = []

    @contextlib.contextmanager
    def fake_opened(pw, arm, mode, user_data_dir=None, config=None):
        reports.append(user_data_dir)
        yield types.SimpleNamespace(pages=[], grant_permissions=lambda *a, **k: None,
                                    new_page=lambda: types.SimpleNamespace(evaluate=lambda js: []))

    monkeypatch.setattr(ms, "opened", fake_opened)
    monkeypatch.setattr(ms, "serve", lambda *a, **k: contextlib.nullcontext("http://x/"))
    monkeypatch.setattr(ms, "read_oracle", lambda ctx, url: {})
    monkeypatch.setattr(ms.rows, "stability_rows", lambda *r: {"n": len(r)})
    monkeypatch.setitem(sys.modules, "camoucrome", types.SimpleNamespace(per_instance_config=dict, profile_seeds=dict))
    monkeypatch.setitem(sys.modules, "camoucrome.launcher", types.SimpleNamespace(remove_dir=lambda d: None))
    out = ms.probe_stability(None, ms.Arm("control", "stock.exe", None, stock=True), "headed", types.SimpleNamespace(fresh_seeds=False))
    assert out == {"n": 2} and seeded == [True]
    assert len(set(reports)) == 1 and reports[0] is not None  # the same directory both times
