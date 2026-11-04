"""navigator.hardwareConcurrency never exceeds the host's cores (C3): timing on the host would show it."""
import inspect
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from camoucrome import gen  # noqa: E402

SEEDS = range(1, 41)
SEEDED = ("canvas:seed", "mediaDevices:seed", "share:cancelMs")
BIG = 10**6


def cfg(seed, host_cores):
    return gen.generate("windows", "Europe/Paris", None, seed, host_cores=host_cores)["config"]


def snapped(host_cores):
    return max([t for t in gen.THREAD_STEPS if t <= host_cores], default=host_cores)


@pytest.mark.parametrize("host_cores", [1, 3, 4, 5, 8, 10])
def test_claim_above_host_snaps_to_largest_step_within_it(host_cores):
    hit = 0
    for s in SEEDS:
        base = cfg(s, BIG)["navigator.hardwareConcurrency"]
        got = cfg(s, host_cores)["navigator.hardwareConcurrency"]
        if base > host_cores:
            hit += 1
            assert got == snapped(host_cores)
        else:
            assert got == base
    if host_cores < 8:
        assert hit  # the draws do exceed it, so the snap branch ran


def test_snap_moves_nothing_else():
    for s in SEEDS:
        a, b = cfg(s, BIG), cfg(s, 2)
        del a["navigator.hardwareConcurrency"], b["navigator.hardwareConcurrency"]
        assert a == b


def test_seeded_keys_are_the_same_with_and_without_a_snap():
    for s in (1, 2, 3):
        assert {k: cfg(s, 2)[k] for k in SEEDED} == {k: cfg(s, BIG)[k] for k in SEEDED}


def test_unset_host_cores_uses_this_machine(monkeypatch):
    monkeypatch.setattr(gen, "allowed_cpus", lambda: 2)
    for s in SEEDS:
        assert gen.generate("windows", "Europe/Paris", None, s)["config"]["navigator.hardwareConcurrency"] <= 2


def test_allowed_cpus_is_the_affinity_mask_size(monkeypatch):
    monkeypatch.setattr(gen.pin, "get_mask", lambda pid: {0, 1})
    monkeypatch.setattr(gen._os, "cpu_count", lambda: 64)
    assert gen.allowed_cpus() == 2


def test_cli_passes_host_cores(capsys):
    gen.main(["--os", "windows", "--timezone", "Europe/Paris", "--seed", "1", "--host-cores", "2"])
    assert json.loads(capsys.readouterr().out)["config"]["navigator.hardwareConcurrency"] <= 2


def test_from_pool_defaults_to_no_snap():
    assert inspect.signature(gen.from_pool).parameters["host_cores"].default is None


def test_without_an_affinity_api_all_cpus_count(monkeypatch):
    monkeypatch.setattr(gen.pin, "get_mask", lambda pid: None)
    monkeypatch.setattr(gen._os, "cpu_count", lambda: 6)
    assert gen.allowed_cpus() == 6
