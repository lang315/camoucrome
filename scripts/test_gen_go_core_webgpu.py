"""The Go webGpu:blocked golden and the architecture table are what gen.py answers now; they need no pinned draw deps."""
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
    # same string (3: RTX, Xe, the off-pool Gen9 shape), Gen9 on Gen9 (4: two pool ids, two Dawn-masked ids), and a different SKU of
    # one vendor and architecture (Ampere, RDNA 2): 11
    assert sum(not r["blocked"] for r in got) == 11


def test_architecture_table_copy_is_fresh():
    assert (d.DATA / "gpu-architectures.json").read_text(encoding="utf-8") == \
        (d.ROOT / "settings" / "webgl" / "gpu-architectures.json").read_text(encoding="utf-8")
