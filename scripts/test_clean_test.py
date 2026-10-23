"""clean_test.py: README block extraction, transcript parser, the UNMEASURED path and the
token-never-leaks property. winhost.powershell is stubbed; nothing touches a host."""
import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "windows"))
import clean_test  # noqa: E402
import winhost  # noqa: E402

README = (HERE.parent / "README.md").read_text()
TOKEN = "ghp_FAKEtoken0123456789abcdefABCDEF"
ARGS = ["--tag", "v1", "--sha", "a" * 40, "--chrome-version", "1.2.3.4", "--repo", "o/r"]

GOOD = """=== BEGIN install-1
ok
=== END install-1 rc=0
=== BEGIN quickstart
alice [8, 1920]
bob [12, 1366]
=== END quickstart rc=0
RUN_DONE elapsed=420
"""

SYNTH = """# T
## Install
```powershell
a
```
text
```cmd
b
```
## Quickstart: two identities
```python
print(1)
```
## Other
```sh
x
```
"""


def test_extract_synthetic():
    assert [b[1] for b in clean_test.fenced_blocks(SYNTH, "Install")] == ["a", "b"]
    assert [b[0] for b in clean_test.fenced_blocks(SYNTH, "Install")] == ["powershell", "cmd"]
    assert len(clean_test.fenced_blocks(SYNTH, "Quickstart: two identities")) == 1
    assert clean_test.fenced_blocks(SYNTH, "Nope") == []


def test_real_readme_quickstart_has_one_block():
    b = clean_test.fenced_blocks(README, "Quickstart: two identities")
    assert len(b) == 1 and b[0][0] == "python"


@pytest.mark.xfail(strict=True, reason="README Install has its commands inline, not in fenced blocks (Task 6 gap)")
def test_real_readme_install_has_two_blocks():
    assert len(clean_test.fenced_blocks(README, "Install")) == 2


def test_parse_pass():
    v, why, ids = clean_test.parse_transcript(GOOD)
    assert v == "PASS" and why == [] and ids == {"alice": (8, 1920), "bob": (12, 1366)}


@pytest.mark.parametrize("mutate,needle", [
    (lambda t: t.replace("install-1 rc=0", "install-1 rc=1"), "install-1"),
    (lambda t: t.replace("RUN_DONE elapsed=420", "RUN_DONE elapsed=901"), "elapsed"),
    (lambda t: t.replace("RUN_DONE elapsed=420", ""), "RUN_DONE"),
    (lambda t: t.replace("bob [12, 1366]", ""), "bob"),
    (lambda t: t.replace("bob [12, 1366]", "bob [8, 1920]"), "differ"),
])
def test_parse_fail(mutate, needle):
    v, why, _ = clean_test.parse_transcript(mutate(GOOD))
    assert v == "FAIL" and any(needle in w for w in why)


def test_unmeasured_when_sandbox_disabled(monkeypatch, tmp_path):
    calls = []

    def fake(script, timeout=300):
        calls.append(script)
        return "SESSION=1\nFEATURE=Disabled\n"

    monkeypatch.setattr(winhost, "powershell", fake)
    got = []
    rc = clean_test.main(ARGS + ["--report-dir", str(tmp_path), "--readme", str(HERE.parent / "README.md")],
                         get_token=lambda: got.append(1) or TOKEN)
    assert rc == 3 and len(calls) == 1 and not got and not list(tmp_path.iterdir())


def test_token_never_in_report_and_file_removed(monkeypatch, tmp_path):
    scripts = []

    def fake(script, timeout=300):
        scripts.append(script)
        if "Get-WindowsOptionalFeature" in script:
            return "SESSION=1\nFEATURE=Enabled\n"
        if "TRANSCRIPT_BEGIN" in script:  # adversarial: the sandbox echoes the token
            return f"SESSION=1\nTRANSCRIPT_BEGIN\n{GOOD}leak {TOKEN}\nTRANSCRIPT_END\n"
        return "SESSION=1\nPATH=C:\\x\n"

    monkeypatch.setattr(winhost, "powershell", fake)
    readme = tmp_path / "R.md"
    readme.write_text(SYNTH)
    rep = tmp_path / "rep"
    rc = clean_test.main(ARGS + ["--report-dir", str(rep), "--readme", str(readme), "--poll-s", "0"],
                         get_token=lambda: TOKEN)
    assert rc == 0
    text = "".join(p.read_text() for p in rep.iterdir())
    assert TOKEN not in text and "[REDACTED]" in text
    assert any("Remove-Item" in s and "token.env" in s for s in scripts)


def test_token_file_removed_when_run_raises(monkeypatch, tmp_path):
    scripts = []

    def fake(script, timeout=300):
        scripts.append(script)
        if "Get-WindowsOptionalFeature" in script:
            return "SESSION=1\nFEATURE=Enabled\n"
        if "Start-Process" in script:
            raise RuntimeError(f"boom {TOKEN}")
        return "SESSION=1\nPATH=C:\\x\n"

    monkeypatch.setattr(winhost, "powershell", fake)
    readme = tmp_path / "R.md"
    readme.write_text(SYNTH)
    with pytest.raises(RuntimeError) as e:
        clean_test.main(ARGS + ["--report-dir", str(tmp_path / "rep"), "--readme", str(readme), "--poll-s", "0"],
                        get_token=lambda: TOKEN)
    assert TOKEN not in str(e.value)
    assert "Remove-Item" in scripts[-1] and "token.env" in scripts[-1]
