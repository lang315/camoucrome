"""Parity with settings/launcher.json and the option guard. No browser."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import camoucrome  # noqa: E402

CONTRACT = json.loads((pathlib.Path(__file__).resolve().parents[3]
                       / "settings" / "launcher.json").read_text())


def test_forbidden_options_match_the_contract():
    assert set(CONTRACT["forbidden_context_options"]["options"]) == camoucrome.FORBIDDEN_OPTIONS


def test_args_match_the_contract():
    launch = CONTRACT["launch"]
    pipe = ["--remote-debugging-pipe"]
    assert camoucrome.build_args(headless=False) == launch["base_args"] + pipe
    assert camoucrome.build_args() == launch["base_args"] + [launch["headless_arg"]] + pipe
    assert camoucrome.build_args(window=(1920, 1040), dpr=1.25, headless=False, user_data_dir="/p") == \
        launch["base_args"] + pipe + ["--user-data-dir=/p",
        launch["window_size_arg"].format(width=1920, height=1040),
        launch["dpr_arg"].format(dpr=1.25)]
    assert launch["ignore_default_args"] is True


def test_env_drops_stale_camou_vars_and_sets_the_transport():
    env = camoucrome.build_env({"screen.width": 1}, {"os": "Windows"}, strict=True,
                               base={"CAMOU_CONFIG_1": "stale", "PATH": "/bin"})
    assert env == {"PATH": "/bin", "CAMOU_CONFIG": '{"screen.width": 1}',
                   "CAMOU_PRESET": '{"os": "Windows"}', "CAMOU_CONFIG_STRICT": "1"}


class FakeChromium:
    def launch_persistent_context(self, user_data_dir, **kw):
        self.user_data_dir, self.kw = user_data_dir, kw
        return "ctx"


class FakePlaywright:
    chromium = FakeChromium()


def test_launch_refuses_forbidden_options():
    with pytest.raises(ValueError, match="timezone_id"):
        camoucrome.launch(FakePlaywright(), "/x/chrome", timezone_id="UTC")


def test_launch_uses_persistent_context_without_viewport_emulation():
    pw = FakePlaywright()
    assert camoucrome.launch(pw, "/x/chrome", config={"a": 1}, user_data_dir="/tmp/p",
                             window=(800, 600)) == "ctx"
    assert pw.chromium.user_data_dir == "/tmp/p"
    kw = pw.chromium.kw
    assert kw["no_viewport"] is True and kw["headless"] is True
    assert kw["ignore_default_args"] is True
    assert kw["env"]["CAMOU_CONFIG"] == '{"a": 1}'
    assert kw["args"] == ["--no-first-run", "--no-default-browser-check", "--headless=new",
                          "--remote-debugging-pipe", "--user-data-dir=/tmp/p", "--window-size=800,600"]


def test_per_instance_seeds_match_the_contract_and_are_nonzero_uint32():
    assert list(camoucrome.SEED_KEYS) == CONTRACT["per_instance_seeds"]["keys"]
    import random
    cfg = camoucrome.per_instance_config(random.Random(7))
    assert set(cfg) == set(camoucrome.SEED_KEYS)
    assert all(1 <= v <= 0xFFFFFFFF for v in cfg.values())
    assert cfg != camoucrome.per_instance_config(random.Random(8))
