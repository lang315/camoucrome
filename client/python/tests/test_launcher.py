"""Parity with settings/launcher.json and the option guard. No browser."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import camoucrome  # noqa: E402
import camoucrome.launcher  # noqa: E402
ROOT = pathlib.Path(__file__).resolve().parents[3]

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


@pytest.fixture(autouse=True)
def temp_dirs_under_tmp_path(tmp_path, monkeypatch):
    """launch() mkdtemps a crash-dump dir on every call; keep them out of /tmp."""
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))


class FakeChromium:
    def launch_persistent_context(self, user_data_dir, **kw):
        self.user_data_dir, self.kw = user_data_dir, kw
        return ClosingContext()


class FakePlaywright:
    chromium = FakeChromium()


def test_launch_refuses_forbidden_options():
    with pytest.raises(ValueError, match="timezone_id"):
        camoucrome.launch(FakePlaywright(), "/x/chrome", timezone_id="UTC")


def test_launch_uses_persistent_context_without_viewport_emulation():
    pw = FakePlaywright()
    assert isinstance(camoucrome.launch(pw, "/x/chrome", config={"a": 1}, user_data_dir="/tmp/p",
                                        window=(800, 600)), ClosingContext)
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


def test_profile_seeds_are_drawn_once_and_read_back(tmp_path):
    profile = tmp_path / "profile"  # not created yet: the first launch makes it
    first = camoucrome.profile_seeds(profile)
    assert set(first) == set(camoucrome.SEED_KEYS)
    assert all(1 <= v <= 0xFFFFFFFF for v in first.values())
    stored = profile / CONTRACT["per_instance_seeds"]["profile_file"]
    assert json.loads(stored.read_text()) == first
    assert camoucrome.profile_seeds(profile) == first


def test_profile_seeds_draw_only_the_missing_keys(tmp_path):
    stored = tmp_path / CONTRACT["per_instance_seeds"]["profile_file"]
    stored.write_text('{"canvas:seed": 5}')
    seeds = camoucrome.profile_seeds(tmp_path)
    assert seeds["canvas:seed"] == 5 and set(seeds) == set(camoucrome.SEED_KEYS)
    assert json.loads(stored.read_text()) == seeds


@pytest.mark.parametrize("damaged", ['{"canvas:seed"', '[1, 2]', '{"audio:seed": 0}',
                                     '{"audio:seed": 4294967296}', '{"audio:seed": "7"}',
                                     '{"audio:seed": true}'])
def test_profile_seeds_refuse_a_damaged_file_rather_than_redraw(tmp_path, damaged):
    # A redraw would silently give the profile a different canvas, audio and
    # device-ID fingerprint than every earlier session showed.
    stored = tmp_path / CONTRACT["per_instance_seeds"]["profile_file"]
    stored.write_text(damaged)
    with pytest.raises(ValueError, match="camoucrome-seeds.json"):
        camoucrome.profile_seeds(tmp_path)
    assert stored.read_text() == damaged


def test_accept_lang_follows_the_config_and_the_contract():
    launch = CONTRACT["launch"]
    assert camoucrome.accept_lang_of({"navigator.languages": ["fr-FR", "fr"]}) == "fr-FR,fr"
    assert camoucrome.accept_lang_of('{"locale:tag": "de-DE"}') == "de-DE"
    assert camoucrome.accept_lang_of({"screen.width": 1}) is None and camoucrome.accept_lang_of(None) is None
    args = camoucrome.build_args(headless=False, accept_lang="fr-FR,fr", extensions=["/e1", "/e2"],
                                 spki_list=["AAA=", "BBB="])
    assert args[len(launch["base_args"]) + 1:] == [
        launch["accept_lang_arg"].format(languages="fr-FR,fr"),
        *[a.format(paths="/e1,/e2") for a in launch["extension_args"]],
        launch["spki_arg"].format(hashes="AAA=,BBB=")]
    pw = FakePlaywright()
    camoucrome.launch(pw, "/x/chrome", config={"navigator.languages": ["fr-FR", "fr"]}, user_data_dir="/p")
    assert "--accept-lang=fr-FR,fr" in pw.chromium.kw["args"]


def test_fontconfig_env_follows_the_claimed_os(tmp_path):
    launcher = camoucrome.launcher
    (tmp_path / "fonts").mkdir()
    (tmp_path / "settings" / "fontconfig").mkdir(parents=True)
    (tmp_path / "settings" / "fontconfig" / "windows.conf").write_text("<fontconfig/>")
    (tmp_path / "settings" / "fontconfig" / "macos.conf").write_text("<fontconfig/>")
    win = launcher.fontconfig_for({"ua:platform": "Windows"}, None, tmp_path / "fonts")
    assert win == str(tmp_path / "settings" / "fontconfig" / "windows.conf")
    assert launcher.fontconfig_for({"ua:platform": "Linux"}, None, tmp_path / "fonts") is None
    assert launcher.fontconfig_for(None, {"os": "macOS"}, tmp_path / "fonts") == str(tmp_path / "settings" / "fontconfig" / "macos.conf")
    assert launcher.fontconfig_for({"ua:platform": "Windows"}, None, None, tmp_path / "nowhere" / "chrome") is None
    (tmp_path / "chrome").write_bytes(b"")
    assert launcher.fontconfig_for({"ua:platform": "Windows"}, None, None, tmp_path / "chrome") == win
    assert launcher.build_env(fontconfig="/x/windows.conf")["FONTCONFIG_FILE"] == "/x/windows.conf"
    assert "FONTCONFIG_FILE" not in launcher.build_env()
    contract = json.loads((ROOT / "settings" / "launcher.json").read_text())["launch"]["fontconfig"]
    assert contract["env"] == launcher.FONTCONFIG_ENV and contract["files"] == launcher.FONTCONFIG_FILES


def test_a_large_config_is_chunked_into_numbered_env_strings():
    big = {"fonts:local": ["x" * 100] * 700}  # ~70 KB: past one 30000-char chunk, under Linux's 128 KiB per string
    env = camoucrome.build_env(big, base={})
    assert "CAMOU_CONFIG" not in env
    parts = [env[f"CAMOU_CONFIG_{n}"] for n in range(1, 4)]
    assert "CAMOU_CONFIG_4" not in env and all(len(p) <= 30000 for p in parts)
    assert json.loads("".join(parts)) == big


def test_accept_lang_follows_the_preset_locale_under_the_config():
    # preset_loader.cc: locale "fr-FR" -> navigator.languages ["fr-FR", "fr"]; "fr" alone -> ["fr"].
    assert camoucrome.accept_lang_of(None, {"locale": "fr-FR"}) == "fr-FR,fr"
    assert camoucrome.accept_lang_of(None, '{"locale": "fr"}') == "fr"
    assert camoucrome.accept_lang_of({"navigator.languages": ["de-DE"]}, {"locale": "fr-FR"}) == "de-DE"
    # An explicit member of the preset's locale triple re-derives the whole
    # triple (preset_loader.cc OverridePresetGroups), as the browser does.
    assert camoucrome.accept_lang_of({"locale:tag": "de-DE"}, {"locale": "fr-FR"}) == "de-DE,de"
    assert camoucrome.accept_lang_of({"navigator.language": "ja-JP"}, {"locale": "fr-FR"}) == "ja-JP,ja"
    pw = FakePlaywright()
    camoucrome.launch(pw, "/x/chrome", preset={"locale": "fr-FR"}, user_data_dir="/p")
    assert "--accept-lang=fr-FR,fr" in pw.chromium.kw["args"]


def test_bad_config_shapes_are_rejected():
    for bad in ("{not json", "[1]", '"x"', {"navigator.languages": "fr"}, {"navigator.languages": ["fr", 1]}):
        with pytest.raises(ValueError):
            camoucrome.build_env(bad, base={})
        with pytest.raises(ValueError):
            camoucrome.accept_lang_of(bad)


def test_claimed_os_mirrors_derive_cc():
    claimed = camoucrome.launcher.claimed_os
    assert claimed({"ua:osInfo": "Windows NT 10.0; Win64; x64", "ua:platform": "macOS"}) == "Windows"
    assert claimed({"ua:osInfo": "X11; Linux x86_64", "ua:platform": "Windows"}) == "Linux"
    assert claimed({"ua:osInfo": "Linux; Android 10; K"}) == "Android"
    assert claimed({"ua:osInfo": "garbage", "ua:platform": "macOS"}) == "macOS"
    # An explicit ua:platform re-derives the preset's OS pair
    # (preset_loader.cc OverridePresetGroups), so the browser claims Windows.
    assert claimed({"ua:platform": "Windows"}, {"os": "macOS"}) == "Windows"
    assert claimed({"ua:platform": "Bogus"}, {"os": "macOS"}) == "macOS"
    assert claimed({"ua:osInfo": "Windows NT 10.0"}, {"os": "macOS"}) == "Windows"
    assert claimed(None, {"os": "Windows"}) == "Windows" and claimed(None, None) is None


def test_fontconfig_env_is_never_inherited_and_the_conf_must_exist(tmp_path):
    launcher = camoucrome.launcher
    assert "FONTCONFIG_FILE" not in launcher.build_env(base={"FONTCONFIG_FILE": "/host.conf"})
    (tmp_path / "fonts").mkdir()
    with pytest.raises(FileNotFoundError):
        launcher.fontconfig_for({"ua:platform": "Windows"}, None, tmp_path / "fonts")


def test_a_large_preset_is_chunked_like_the_config():
    big = {"fonts": ["x" * 100] * 700}
    env = camoucrome.build_env(preset=big, base={})
    assert "CAMOU_PRESET" not in env and json.loads(env["CAMOU_PRESET_1"] + env["CAMOU_PRESET_2"] + env["CAMOU_PRESET_3"]) == big


class ClosingContext:
    def __init__(self):
        self.handlers = []

    def on(self, event, fn):
        self.handlers.append((event, fn))

    def close(self):
        pass


class ClosingChromium:
    def __init__(self, fail=False):
        self.fail = fail

    def launch_persistent_context(self, user_data_dir, **kw):
        self.user_data_dir, self.kw = user_data_dir, kw
        if self.fail:
            raise RuntimeError("spawn failed")
        self.ctx = ClosingContext()
        return self.ctx


def test_temp_profile_is_removed_on_close_and_on_failure(tmp_path):
    import os
    pw = type("PW", (), {"chromium": ClosingChromium()})()
    ctx = camoucrome.launch(pw, "/x/chrome")
    assert os.path.isdir(pw.chromium.user_data_dir)
    [(event, fn)] = ctx.handlers
    assert event == "close"
    fn(ctx)
    assert not os.path.exists(pw.chromium.user_data_dir)
    pw = type("PW", (), {"chromium": ClosingChromium(fail=True)})()
    with pytest.raises(RuntimeError):
        camoucrome.launch(pw, "/x/chrome")
    assert not os.path.exists(pw.chromium.user_data_dir)
    kept = tmp_path / "profile"
    kept.mkdir()
    pw = type("PW", (), {"chromium": ClosingChromium()})()
    [(_, fn)] = camoucrome.launch(pw, "/x/chrome", user_data_dir=str(kept)).handlers
    fn(None)
    assert kept.is_dir()  # a kept profile is the caller's; only the crash-dump dir goes


def test_touch_and_mobile_emulation_are_forbidden():
    for opt in ("has_touch", "is_mobile"):
        with pytest.raises(ValueError, match=opt):
            camoucrome.launch(FakePlaywright(), "/x/chrome", **{opt: True})


def test_temp_profile_cleanup_works_with_the_async_api():
    import asyncio
    import os

    class AsyncChromium(ClosingChromium):
        def launch_persistent_context(self, user_data_dir, **kw):
            async def go():
                return ClosingChromium.launch_persistent_context(self, user_data_dir, **kw)
            return go()

    pw = type("PW", (), {"chromium": AsyncChromium()})()
    ctx = asyncio.run(camoucrome.launch(pw, "/x/chrome"))
    [(event, fn)] = ctx.handlers
    fn(ctx)
    assert event == "close" and not os.path.exists(pw.chromium.user_data_dir)
    pw = type("PW", (), {"chromium": AsyncChromium(fail=True)})()
    with pytest.raises(RuntimeError):
        asyncio.run(camoucrome.launch(pw, "/x/chrome"))
    assert not os.path.exists(pw.chromium.user_data_dir)


def test_temp_profile_removal_outlasts_a_locked_profile(monkeypatch):
    """Windows: the "close" event fires while the browser still holds files in
    its profile, so one rmtree(ignore_errors=True) leaves the directory behind
    (measured 2026-10-03). Here rmtree is a no-op twice before it works."""
    import os
    import shutil
    real, calls = shutil.rmtree, []

    def locked_twice(path, ignore_errors=False):
        calls.append(path)
        if len(calls) > 2:
            real(path, ignore_errors=ignore_errors)

    pw = type("PW", (), {"chromium": ClosingChromium()})()
    ctx = camoucrome.launch(pw, "/x/chrome")
    monkeypatch.setattr(shutil, "rmtree", locked_twice)
    [(_, fn)] = ctx.handlers
    fn(ctx)
    # The crash-dump dir is removed first (two no-ops, then it goes), then the profile.
    assert len(calls) == 4 and not os.path.exists(pw.chromium.user_data_dir)


def test_crash_dumps_go_to_a_dir_the_launcher_deletes(tmp_path):
    """Chrome writes a crash's minidump -- which holds the whole environment
    block, CAMOU_CONFIG verbatim (measured 2026-10-03 on Windows) -- to
    <profile>/Crashpad unless BREAKPAD_DUMP_LOCATION names somewhere else. Every
    launch, a kept profile included, points it at a temp dir removed on close
    or on a failed launch; the parent's value is never inherited."""
    import os
    launch = CONTRACT["launch"]
    env_name = launch["crash_dumps"]["env"]
    assert env_name == camoucrome.launcher.CRASH_DUMPS_ENV == "BREAKPAD_DUMP_LOCATION"
    assert env_name not in camoucrome.build_env(base={env_name: "/host/dumps"})
    assert camoucrome.build_env(base={}, crash_dir="/c")[env_name] == "/c"

    kept = tmp_path / "profile"
    kept.mkdir()
    pw = type("PW", (), {"chromium": ClosingChromium()})()
    ctx = camoucrome.launch(pw, "/x/chrome", user_data_dir=str(kept))
    crash = pw.chromium.kw["env"][env_name]
    assert os.path.isdir(crash) and not crash.startswith(str(kept))
    [(event, fn)] = ctx.handlers
    fn(ctx)
    assert event == "close" and not os.path.exists(crash) and kept.is_dir()

    pw = type("PW", (), {"chromium": ClosingChromium(fail=True)})()
    with pytest.raises(RuntimeError):
        camoucrome.launch(pw, "/x/chrome", user_data_dir=str(kept))
    assert not os.path.exists(pw.chromium.kw["env"][env_name])


class ShuttingDownContext(ClosingContext):
    """Linux: the "close" event fires while the browser is still shutting
    down, and it then writes its profile (Local State, Default/...) and
    crashpad re-creates the dump dir -- after the handler removed both
    (measured 2026-10-03: 518 such profiles in the box's /tmp). By the time
    close() returns, no process names the profile."""

    def __init__(self, dirs):
        super().__init__()
        self.dirs = dirs

    def close(self):
        import os
        for _, fn in self.handlers:
            fn(self)
        for d in self.dirs:
            os.makedirs(os.path.join(d, "Default"), exist_ok=True)


class ShuttingDownChromium(ClosingChromium):
    def launch_persistent_context(self, user_data_dir, **kw):
        ClosingChromium.launch_persistent_context(self, user_data_dir, **kw)
        crash = kw["env"][camoucrome.launcher.CRASH_DUMPS_ENV]
        self.ctx = ShuttingDownContext([user_data_dir, crash])
        return self.ctx


def test_what_the_browser_writes_while_closing_is_removed_once_close_returns():
    import os
    pw = type("PW", (), {"chromium": ShuttingDownChromium()})()
    ctx = camoucrome.launch(pw, "/x/chrome")
    ctx.close()
    assert [os.path.exists(d) for d in ctx.dirs] == [False, False]


def test_what_the_browser_writes_while_closing_is_removed_with_the_async_api():
    import asyncio
    import os

    class AsyncShuttingDown(ShuttingDownContext):
        async def close(self):
            ShuttingDownContext.close(self)

    class AsyncChromium(ShuttingDownChromium):
        def launch_persistent_context(self, user_data_dir, **kw):
            async def go():
                ShuttingDownChromium.launch_persistent_context(self, user_data_dir, **kw)
                self.ctx.__class__ = AsyncShuttingDown
                return self.ctx
            return go()

    async def run():
        ctx = await camoucrome.launch(type("PW", (), {"chromium": AsyncChromium()})(), "/x/chrome")
        await ctx.close()
        return ctx

    ctx = asyncio.run(run())
    assert [os.path.exists(d) for d in ctx.dirs] == [False, False]
