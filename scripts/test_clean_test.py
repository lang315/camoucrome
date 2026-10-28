"""clean_test.py: README block extraction, transcript parser, the UNMEASURED path, and the
"no token and no payload reaches the host through winhost" properties. winhost.powershell, the
gh download and scp are stubbed; nothing touches a host or GitHub."""
import base64
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "windows"))
import clean_test  # noqa: E402
import winhost  # noqa: E402

README = (HERE.parent / "README.md").read_text()
ARGS = ["--tag", "v1", "--sha", "a" * 40, "--chrome-version", "1.2.3.4", "--repo", "o/r"]

GOOD = """=== BEGIN install-1
ok
=== END install-1 rc=0
=== BEGIN install-3-checksum
True
=== END install-3-checksum rc=0
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
```powershell
$b = 'https://x/releases/download/<tag>'
```
```powershell
(Get-FileHash z).Hash -eq 'q'
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
    assert [b[1] for b in clean_test.fenced_blocks(SYNTH, "Install")][0] == "a"
    assert len(clean_test.fenced_blocks(SYNTH, "Install")) == 3
    assert len(clean_test.fenced_blocks(SYNTH, "Quickstart: two identities")) == 1
    assert clean_test.fenced_blocks(SYNTH, "Nope") == []


def test_real_readme_block_counts():
    inst = clean_test.fenced_blocks(README, "Install")
    assert len(inst) == 5 and {b[0] for b in inst} == {"powershell"}
    assert sum("releases/download/<tag>" in b[1] for b in inst) == 1  # the one block the runner stages
    assert sum("Get-FileHash" in b[1] for b in inst) == 1
    q = clean_test.fenced_blocks(README, "Quickstart: two identities")
    assert len(q) == 1 and q[0][0] == "python"


def test_parse_pass():
    v, why, ids = clean_test.parse_transcript(GOOD)
    assert v == "PASS" and why == [] and ids == {"alice": (8, 1920), "bob": (12, 1366)}


@pytest.mark.parametrize("mutate,needle", [
    (lambda t: t.replace("install-1 rc=0", "install-1 rc=1"), "install-1"),
    (lambda t: t.replace("\nTrue\n", "\nFalse\n"), "checksum"),
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
    monkeypatch.setattr(winhost, "powershell", lambda s, timeout=300: calls.append(s) or "SESSION=1\nFEATURE=Disabled\n")
    monkeypatch.setattr(clean_test, "gh_download", lambda *a: pytest.fail("gh called"))
    rc = clean_test.main(ARGS + ["--report-dir", str(tmp_path), "--readme", str(HERE.parent / "README.md")])
    assert rc == 3 and len(calls) == 1 and not list(tmp_path.iterdir())


@pytest.fixture
def run(monkeypatch, tmp_path):
    """A full stubbed run: returns (scripts, scp calls, subprocess argvs, report dir, rc)."""
    scripts, scps, argvs = [], [], []
    asset = b"\x00ZIPBYTES" * 20000  # 180 KB
    b64 = base64.b64encode(asset).decode()

    def fake(script, timeout=300):
        scripts.append(script)
        if "Get-WindowsOptionalFeature" in script:
            return "SESSION=1\nFEATURE=Enabled\n"
        if "TRANSCRIPT_BEGIN" in script:
            return f"SESSION=1\nTRANSCRIPT_BEGIN\n{GOOD}TRANSCRIPT_END\n"
        if "Test-Path" in script and "Remove-Item" in script:
            return "SESSION=1\n"
        return "SESSION=1\n"

    def gh(repo, tag, d):
        (pathlib.Path(d) / "a.zip").write_bytes(asset)
        (pathlib.Path(d) / "SHA256SUMS").write_text("x  a.zip\n")

    monkeypatch.setattr(winhost, "powershell", fake)
    monkeypatch.setattr(clean_test, "gh_download", gh)
    monkeypatch.setattr(clean_test, "scp", lambda local, remote: scps.append((local, remote)))
    for n in ("run", "check_output", "check_call", "Popen"):
        monkeypatch.setattr(subprocess, n, lambda *a, _n=n, **k: argvs.append(a[0]) or pytest.fail("subprocess " + _n))
    readme = tmp_path / "R.md"
    readme.write_text(SYNTH)
    rc = clean_test.main(ARGS + ["--report-dir", str(tmp_path / "rep"), "--readme", str(readme), "--poll-s", "0"])
    return scripts, scps, b64, tmp_path / "rep", rc


def test_no_token_no_payload_through_winhost(run):
    scripts, scps, b64, rep, rc = run
    assert rc == 0
    assert all(len(s) < 8000 for s in scripts)
    assert not any(b64[:200] in s for s in scripts)
    assert scps  # the files went by scp
    assert all("D:/camou-win/clean-test/" in r for _, r in scps)


def test_cleanup_script_safe(run):
    scripts, *_ = run
    assert not any("vmmem" in s for s in scripts)
    last = scripts[-1]
    assert "WindowsSandbox" in last and "Remove-Item" in last and "Test-Path" in last and "WARN" in last


def test_no_gh_auth_token_anywhere():
    for p in (HERE / "windows").glob("clean*"):
        t = p.read_text()
        assert not any(w in t.lower() for w in ('"auth"', "token.env", "gh_token", "bearer", "redact")), p.name


def test_download_step_staged_by_runner_recorded(run):
    *_, rep, rc = run
    text = next(rep.iterdir()).read_text()
    assert "download step staged by the runner" in text and "install-2" in text


def test_run_ps1_blocks_run_in_child_powershell():
    t = (HERE / "windows" / "clean-test-run.ps1.template").read_text()
    child = [l for l in t.splitlines() if "powershell" in l and "-Command" in l]
    assert len(child) == 1 and "2>&1" in child[0]
    # Stop is set only inside the child's command string, never in the parent around the capture
    assert "ErrorActionPreference='Stop'" in t
    assert not [l for l in t.splitlines() if "ErrorActionPreference" in l and "Stop" in l and not l.startswith("#") and "-Command" not in l
                and "$cmd" not in l]
    assert "$LASTEXITCODE" in t.split("function Block", 1)[1]
    assert "Block 'quickstart'" in t and "Step " not in t


def test_readme_install_block1_checks_installer_exit_codes():
    b1 = clean_test.fenced_blocks(README, "Install")[0][1]
    assert b1.count("-Wait -PassThru") == 2 and b1.count(".ExitCode") >= 2
    assert "Run as administrator" in README.split("## Install", 1)[1].split("```", 1)[0]


def test_quickstart_identities_are_seeded():
    q = clean_test.fenced_blocks(README, "Quickstart: two identities")[0][1]
    assert "seed=" in q and "generate(os=\"windows\")" not in q
    assert q.count("seed=seed") == 1 and '(("alice", 1), ("bob", 2))' in q


def test_pip_line_pins_the_sha_and_the_fill_substitutes_it():
    inst = "\n".join(b for _, b in clean_test.fenced_blocks(README, "Install"))
    assert "camoucrome@<sha>#subdirectory=client/python" in inst
    assert "@<tag>" not in inst and "@" + "a" * 40 + "#subdirectory" in inst.replace("<sha>", "a" * 40) and "releases/download/<tag>" in README


def test_parse_fail_without_a_checksum_step():
    t = GOOD.replace("=== BEGIN install-3-checksum\nTrue\n=== END install-3-checksum rc=0\n", "")
    v, why, _ = clean_test.parse_transcript(t)
    assert v == "FAIL" and any("no checksum step" in w for w in why)
