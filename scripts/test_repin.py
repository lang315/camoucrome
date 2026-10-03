"""repin.py: version choice, the shipped-stable assertion, and the pin rewrite."""
import json
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import repin  # noqa: E402

OLD_REV = "507c6ee3e2f3b2ca0e660547e5b9ea4820c67f4c"
NEW_REV = "0123456789abcdef0123456789abcdef01234567"


def fake_fetch(versions):
    def fetch(url):
        assert "channel=Stable" in url and "platform=Windows" in url
        return json.dumps([{"version": v, "time": 1} for v in versions])
    return fetch


def test_newest_compares_numerically_not_as_text():
    assert repin.newest(["154.0.8037.9", "154.0.8037.98", "153.0.8010.36"]) == "154.0.8037.98"


def test_stable_versions_reads_the_channel_listing():
    got = repin.stable_versions(fetch=fake_fetch(["154.0.8037.98", "153.0.8010.36"]))
    assert got == ["154.0.8037.98", "153.0.8010.36"]


def test_stable_versions_refuses_an_empty_listing():
    with pytest.raises(SystemExit):
        repin.stable_versions(fetch=fake_fetch([]))


@pytest.fixture
def tree(tmp_path):
    root = tmp_path
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "upstream.env").write_text(
        "# refuses any other HEAD\n"
        f"CHROMIUM_REV={OLD_REV}\n"
        "# The tag that commit is: Chrome stable 153.0.8010.36 (refs/tags/153.0.8010.36,\n"
        "# branch-heads/8010).\n"
        "CHROMIUM_TAG=153.0.8010.36\n")
    (root / "scripts").mkdir()
    (root / "scripts" / "verify_x.py").write_text(
        'BASE = "baselines/chrome-8010-stock-oracle-windows.json"\n'
        'UA = "baselines/chrome-507c6ee3e2-stock-ua.json"\n'
        'STOCK_BASE_COMMIT = "507c6ee3e2"\n'
        'META = {"chrome": "153.0.8010.36"}\n'
        "PORT = 8010\n"
        # A record of the PREVIOUS re-pin. Its right-hand values are this
        # re-pin's "old" pair, so a blind rewrite turns it into a false record.
        "# 2026-09-10: 0e8d4a9268 -> 507c6ee3e2 (Chrome stable 153.0.8010.36), captured that way.\n")
    (root / "settings").mkdir()
    (root / "settings" / "audio.json").write_text('{"chrome": "153.0.8010.36"}\n')
    (root / "baselines").mkdir()
    for name in ("chrome-8010-stock-oracle-windows.json", "content_shell-8010-stock-ua.json",
                 "chrome-507c6ee3e2-stock-ua.json", "chrome-0e8d4a9268-stock-ua.json"):
        (root / "baselines" / name).write_text("{}\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x"],
                   cwd=root, check=True)
    return root


def test_retarget_rewrites_the_pin_and_renames_the_baselines(tree):
    changed = repin.retarget(tree, "154.0.8037.98", NEW_REV)
    env = (tree / "upstream.env").read_text()
    assert f"CHROMIUM_REV={NEW_REV}\n" in env
    assert "CHROMIUM_TAG=154.0.8037.98\n" in env
    assert "refs/tags/154.0.8037.98" in env and "branch-heads/8037" in env
    assert "8010" not in env and OLD_REV not in env
    names = sorted(p.name for p in (tree / "baselines").iterdir())
    assert names == ["chrome-0123456789-stock-ua.json", "chrome-0e8d4a9268-stock-ua.json",
                     "chrome-8037-stock-oracle-windows.json", "content_shell-8037-stock-ua.json"]
    script = (tree / "scripts" / "verify_x.py").read_text()
    assert "chrome-8037-stock-oracle-windows.json" in script
    assert "chrome-0123456789-stock-ua.json" in script
    assert 'STOCK_BASE_COMMIT = "0123456789"' in script
    assert '"chrome": "154.0.8037.98"' in script
    assert "upstream.env" in changed and "scripts/verify_x.py" in changed


def test_retarget_leaves_unrelated_numbers_and_settings_alone(tree):
    repin.retarget(tree, "154.0.8037.98", NEW_REV)
    assert "PORT = 8010\n" in (tree / "scripts" / "verify_x.py").read_text()
    assert (tree / "settings" / "audio.json").read_text() == '{"chrome": "153.0.8010.36"}\n'


def test_retarget_refuses_a_malformed_tag_or_revision(tree):
    with pytest.raises(SystemExit):
        repin.retarget(tree, "154.0.8037", NEW_REV)
    with pytest.raises(SystemExit):
        repin.retarget(tree, "154.0.8037.98", "0123abc")


def test_a_failed_rename_leaves_the_pin_so_a_rerun_finishes_the_job(tree):
    extra = tree / "baselines" / "content_shell-8010-stock-extra.json"
    extra.write_text("{}\n")  # untracked: git mv refuses it
    with pytest.raises(subprocess.CalledProcessError):
        repin.retarget(tree, "154.0.8037.98", NEW_REV)
    env = (tree / "upstream.env").read_text()
    assert OLD_REV in env and "CHROMIUM_TAG=153.0.8010.36\n" in env
    subprocess.run(["git", "add", str(extra)], cwd=tree, check=True)
    repin.retarget(tree, "154.0.8037.98", NEW_REV)
    assert "CHROMIUM_TAG=154.0.8037.98\n" in (tree / "upstream.env").read_text()
    assert not [p for p in (tree / "baselines").iterdir() if "-8010-stock" in p.name]
    assert "chrome-8037-stock-oracle-windows.json" in (tree / "scripts" / "verify_x.py").read_text()


def test_retarget_leaves_a_dated_history_line_byte_identical(tree):
    """RED without HISTORY_RE: the line records what the LAST re-pin did, and both
    of its values are this re-pin's "old" pair, so rewriting it claims the
    2026-09-10 re-pin went to a tag that did not exist yet -- in the one comment
    whose purpose is to stop the baseline becoming a recording of itself."""
    repin.retarget(tree, "154.0.8037.93", NEW_REV)
    text = (tree / "scripts" / "verify_x.py").read_text()
    assert "# 2026-09-10: 0e8d4a9268 -> 507c6ee3e2 (Chrome stable 153.0.8010.36), captured that way." in text
    # and the exemption is narrow: the live literals on other lines did move
    assert f'STOCK_BASE_COMMIT = "{NEW_REV[:10]}"' in text
    assert f'META = {{"chrome": "154.0.8037.93"}}' in text


def test_retarget_still_rewrites_an_undated_version_mention(tree):
    """The exemption is anchored on a date, not on the word "history": a comment
    that merely names the pin is a reference to the current pin and must move."""
    f = tree / "scripts" / "verify_y.py"
    f.write_text("# the pin is 153.0.8010.36 today\n")
    repin.retarget(tree, "154.0.8037.93", NEW_REV)
    assert f.read_text() == f"# the pin is 154.0.8037.93 today\n"
