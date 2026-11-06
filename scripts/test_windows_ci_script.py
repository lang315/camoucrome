"""Static checks of scripts/windows/windows-ci.ps1 (spec 2026-10-28 section 2). The PowerShell cannot run
on the Mac, so these read it as text: the rules that must hold whatever the host does."""
import pathlib
import re

PS1 = pathlib.Path(__file__).resolve().parent / "windows" / "windows-ci.ps1"


def text():
    return PS1.read_text(encoding="utf-8")


def code_lines():
    return [(i, l) for i, l in enumerate(text().splitlines(), 1) if not l.lstrip().startswith("#")]


def test_no_forbidden_literals():
    t = text()
    assert not re.search(r"/home/|C:\\Users|\\Users\\|/Users/", t)
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", t)
    assert not re.search(r"-u\s+[A-Za-z][\w-]*\s+--", t.replace("-u $WslUser", ""))
    assert not re.search(r"facebook|instagram|threads", t, re.I)
    assert "$env:USERNAME" not in t and "whoami" not in t


def test_every_get_date_is_utc():
    hits = [(i, l) for i, l in code_lines() if "Get-Date" in l]
    assert hits
    assert [i for i, l in hits if "ToUniversalTime" not in l] == []


def test_release_in_finally_after_acquire():
    t = text()
    acq = t.index("Invoke-Lock 'acquire'")
    fin = t.index("finally", acq)
    assert "Invoke-Lock 'release'" in t[fin:]
    assert "try {" in t[acq:fin]
    assert t.count("Invoke-Lock 'release'") == 1


def test_force_needs_reason():
    assert re.search(r"if \(\$Force -and -not \$ForceReason\) \{ throw", text())


def test_observe_check_before_lock():
    t = text()
    assert t.index("observe-auto") < t.index("Invoke-Lock 'acquire'")
    assert "observe-recon" in t and "recon\\.ps1" in t
    assert "DryRun" not in t[t.index("function Get-ObserveInUse"):t.index("function Get-ObserveInUse") + 700]


def test_tested_commit_only_after_pass_or_fail():
    t = text()
    writes = [m.start() for m in re.finditer(r"Set-Content \$stamp", t)]
    assert len(writes) == 1
    guard = t[:writes[0]].rstrip().splitlines()[-1]
    assert "'PASS'" in guard and "'FAIL'" in guard and "SKIPPED" not in guard


def test_result_line_printed_last():
    lines = [l for l in text().splitlines() if l.strip() and not l.lstrip().startswith("#")]
    assert lines[-1].strip() == "exit $rc"
    assert lines[-2].strip() == "Write-Output $res"


def test_dryrun_uses_test_lock():
    t = text()
    assert "CAMOU_BUILD_LOCK" in t
    assert re.search(r"if \(\$DryRun -and -not \$env:CAMOU_BUILD_LOCK\) \{ throw", t)


def test_no_lock_waiting():
    t = text()
    body = t[t.index("function Invoke-Lock"):]
    body = body[:body.index("\nfunction ", 5)] if "\nfunction " in body[5:] else body
    assert "Start-Sleep" not in body
    assert not any("lock" in l.lower() and "Start-Sleep" in l for _, l in code_lines())


def test_no_scheduled_task_registration():
    assert "Register-ScheduledTask" not in text()
    assert "New-ScheduledTask" not in text()


def test_host_config_required_and_not_hardcoded():
    t = text()
    assert "host.config.ps1" in t
    assert re.search(r"if \(-not \(Test-Path \$HostConfig\)\) \{ throw", t)
    assert "$WslUser" in t and "$LockScript" in t


def _ps():
    import pathlib
    return (pathlib.Path(__file__).parent / "windows" / "windows-ci.ps1").read_text()


def test_build_process_handle_is_read_before_exitcode():
    # PS 5.1: ExitCode is $null for a -PassThru process unless $p.Handle was read first.
    s = _ps()
    assert s.index("$null = $p.Handle") < s.index("$p.ExitCode")


def test_runner_clone_is_fetched_before_the_commit_is_resolved():
    s = _ps()
    assert s.index("fetch -q origin") < s.index("rev-parse $Commit")


def test_build_timeout_is_a_parameter_not_a_literal():
    s = _ps()
    assert "[int]$BuildHours" in s and "4 * 3600" not in s
