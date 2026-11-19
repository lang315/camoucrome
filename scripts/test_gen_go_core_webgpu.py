"""The Go webGpu:blocked golden and the Gen9 id list are what gen.py answers now; they need no pinned draw deps."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gen_go_core_data as d  # noqa: E402
import gen_go_core_golden as g  # noqa: E402
from camoucrome import gen  # noqa: E402


def test_golden_is_fresh_and_covers_every_case():
    got = json.loads((g.OUT / "webgpu.json").read_text(encoding="utf-8"))
    assert got == json.loads(json.dumps(g.webgpu_rows(gen)))
    assert {r["blocked"] for r in got} == {True, False}
    assert sum(not r["blocked"] for r in got) == 6  # same string (3: RTX, Xe, the off-pool Gen9 shape), Gen9 on Gen9 (3)


def test_gen9_ids_are_fresh():
    assert (d.DATA / "gen9-ids.json").read_text(encoding="utf-8") == d.dumps(d.gen9_ids())
