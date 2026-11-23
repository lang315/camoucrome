"""observe-auto.ps1 cleanup, checked as text: the repo has no Pester or PowerShell test setup, and the script needs the host."""
import pathlib

PS1 = (pathlib.Path(__file__).resolve().parent / "windows" / "observe-auto.ps1").read_text()
FINALLY = PS1[PS1.index("} finally {"):]


def test_a_surviving_profile_copy_or_cookie_file_is_named_and_ends_unmeasured():
    assert "Test-Path" in FINALLY or "Get-ChildItem $run -Filter 'profile-arm*'" in FINALLY
    line = next(l for l in FINALLY.splitlines() if "PROFILE delete FAILED $($sv.FullName)" in l)
    assert "$worst = [math]::Max($worst, 3)" in line


def test_the_stale_warm_sweep_counts_what_it_removed():
    assert "$($stale.Count - $left.Count) of $($stale.Count) stale" in PS1
    assert "WARM delete FAILED $($l.FullName)" in PS1


def test_a_logged_in_arm_copy_that_survives_raises_worst():
    line = next(l for l in PS1.splitlines() if 'PROFILE delete FAILED arm$a' in l)
    assert "$worst" in line
