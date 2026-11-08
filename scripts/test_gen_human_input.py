"""gen_human_input.py: one JSON in, the same numbers out in Go, Python and Node."""
import json
import pathlib
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import calibrate_human_input as cal  # noqa: E402
import gen_human_input as gen  # noqa: E402


def doc():
    d = cal.assemble(date="2026-11-09")
    d["dwell"].update(median_ms=92.16, sigma=0.3474, min_ms=32.0, max_ms=226.0)
    d["rollover"]["chance"] = 0.1757
    d["typos"]["run_len_probs"] = [0.5, 0.3, 0.2]
    d["digraph"] = {"source": "keyrecs", "date": "2026-11-09", "min_n": 300,
                    "pairs": {"th": {"median_ms": 150.0, "n": 900}}}
    return d


def test_render_same_numbers_three_languages():
    out = gen.render(doc())
    assert set(out) == {"client/go/rodclient/human_params.go",
                        "client/python/camoucrome/human_params.py",
                        "client/node/human_params.js",
                        "client/go/rodclient/cmd/camoucrome-smoke/calibrated_floors.go"}
    go = out["client/go/rodclient/human_params.go"]
    py = out["client/python/camoucrome/human_params.py"]
    js = out["client/node/human_params.js"]
    assert "dwellMedian = 92160 * time.Microsecond" in go
    assert "dwellSigma = 0.3474" in go
    assert "DWELL_MEDIAN_MS = 92.16" in py
    assert "const dwellMedianMs = 92.16;" in js
    assert "rolloverChance = 0.1757" in go
    assert '"th": 150.0' in py and '"th": 150' in js and 'digraphFlight["th"] = 150000 *' in go
    floors = out["client/go/rodclient/cmd/camoucrome-smoke/calibrated_floors.go"]
    assert "package main" in floors and "calibDwellMinMs = 32.0" in floors
    assert "calibHoldMinMs" in floors and "calibLeadMinMs" in floors
    assert "DO NOT EDIT" in go and "DO NOT EDIT" in py and "DO NOT EDIT" in js


def test_python_output_imports_and_matches():
    py = gen.render(doc())["client/python/camoucrome/human_params.py"]
    ns = {}
    exec(compile(py, "human_params.py", "exec"), ns)
    assert ns["DWELL_SIGMA"] == 0.3474
    assert ns["TYPO_RUN_LEN_PROBS"] == [0.5, 0.3, 0.2]
    assert ns["DIGRAPH_FLIGHT_MS"] == {"th": 150.0}


@pytest.mark.skipif(shutil.which("node") is None, reason="node missing")
def test_node_output_loads(tmp_path):
    js = gen.render(doc())["client/node/human_params.js"]
    (tmp_path / "human_params.js").write_text(js)
    r = subprocess.run(["node", "-e", "const p=require('./human_params.js');"
                        "console.log(p.dwellMedianMs, p.typoRunLenProbs.length, p.digraphFlightMs.th)"],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.stdout.split() == ["92.16", "3", "150"], r.stderr


def seed_root(tmp_path):
    (tmp_path / "settings").mkdir()
    (tmp_path / "settings" / "human_input.json").write_text(json.dumps(doc()))
    return tmp_path


def test_check_red_on_missing_then_stale_then_green(tmp_path):
    root = seed_root(tmp_path)
    args = ["--root", str(root)]
    assert gen.main(["--check", *args]) == 1           # nothing generated yet
    assert gen.main(args) == 0                          # write
    assert gen.main(["--check", *args]) == 0           # GREEN
    go = root / "client/go/rodclient/human_params.go"
    go.write_text(go.read_text().replace("92160", "92161"))
    assert gen.main(["--check", *args]) == 1           # RED: stale
    assert gen.main(args) == 0
    assert gen.main(["--check", *args]) == 0


def test_json_change_makes_outputs_stale(tmp_path):
    root = seed_root(tmp_path)
    args = ["--root", str(root)]
    gen.main(args)
    j = root / "settings" / "human_input.json"
    d = json.loads(j.read_text())
    d["dwell"]["median_ms"] = 100.0
    j.write_text(json.dumps(d))
    assert gen.main(["--check", *args]) == 1


def test_missing_field_is_an_error(tmp_path):
    root = seed_root(tmp_path)
    j = root / "settings" / "human_input.json"
    d = json.loads(j.read_text())
    del d["flight"]
    j.write_text(json.dumps(d))
    with pytest.raises(KeyError):
        gen.main(["--root", str(root)])


def test_committed_outputs_are_current():
    """The repo's own generated files match settings/human_input.json."""
    assert gen.main(["--check"]) == 0
