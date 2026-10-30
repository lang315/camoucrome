"""observe_unlink.py on hand-made captures (no browser)."""
import base64
import json
import pathlib
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import observe_unlink as u  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = json.loads((ROOT / "settings" / "fb_fields.json").read_text(encoding="utf-8"))
CONSTANTS = json.loads((ROOT / "settings" / "machine_constants.json").read_text(encoding="utf-8"))["leaves"]
ACCEPTED = json.loads((ROOT / "settings" / "accepted_defaults.json").read_text(encoding="utf-8"))["leaves"]


def req(path, form):
    raw = urllib.parse.urlencode({k: json.dumps(v) if not isinstance(v, str) else v for k, v in form.items()}).encode()
    return {"url": "https://www.facebook.com" + path, "body_b64": base64.b64encode(raw).decode(),
            "content_type": "application/x-www-form-urlencoded"}


def bz(**payload):
    return req("/ajax/bz", {"q": {"payload": payload}})


def pv(*requests):
    return u.profile_values(list(requests))


def row(doc, field):
    return next(r for r in doc["rows"] if r["field"] == field)


def test_same_renderer_in_three_fork_profiles_is_a_gap():
    fork = [pv(bz(gpu_renderer="ANGLE (X)")) for _ in range(3)]
    stock = [pv(bz(gpu_renderer="ANGLE (X)")) for _ in range(3)]
    doc = u.classify(fork, stock, DOC, CONSTANTS, ACCEPTED)
    r = row(doc, "/ajax/bz q.payload.gpu_renderer")
    assert (r["class"], r["fork_distinct"], r["stock_distinct"], r["explained_by"]) == ("gap", 1, 1, None)
    assert doc["counts"]["net_gap"] == 1


def test_three_renderers_are_unlinked():
    fork = [pv(bz(gpu_renderer=f"ANGLE ({i})")) for i in range(3)]
    stock = [pv(bz(gpu_renderer="ANGLE (X)")) for _ in range(3)]
    assert row(u.classify(fork, stock, DOC, CONSTANTS, ACCEPTED), "/ajax/bz q.payload.gpu_renderer")["class"] == "unlinked"


def test_ip_bound_field_is_never_a_gap():
    fork = [pv(req("/ajax/bz", {"q": {"metadata": {"locale_info": {"locale": "fr_FR"}}}})) for _ in range(3)]
    doc = u.classify(fork, fork, DOC, CONSTANTS, ACCEPTED)
    assert row(doc, "/ajax/bz q.metadata.locale_info.locale")["class"] == "ip-bound"
    assert doc["counts"]["net_gap"] == 0


def test_fork_constant_where_stock_drifts_is_pinned():
    fork = [pv(bz(ram=8)) for _ in range(3)]
    stock = [pv(bz(ram=v)) for v in (8, 16, 32)]
    assert row(u.classify(fork, stock, DOC, CONSTANTS, ACCEPTED), "/ajax/bz q.payload.ram")["class"] == "pinned"


def test_a_profile_value_is_the_set_of_all_its_beacons():
    # one beacon each says 8, but profile 2 also sent 16: not the same profile value
    fork = [pv(bz(ram=8), bz(ram=8)), pv(bz(ram=8), bz(ram=16)), pv(bz(ram=8))]
    assert row(u.classify(fork, fork, DOC, CONSTANTS, ACCEPTED), "/ajax/bz q.payload.ram")["fork_distinct"] == 2


def test_machine_constant_explains_a_gap():
    fork = [pv(bz(webgpu_available=True)) for _ in range(3)]
    r = row(u.classify(fork, fork, DOC, CONSTANTS, ACCEPTED), "/ajax/bz q.payload.webgpu_available")
    assert (r["class"], r["explained_by"]) == ("gap", "machine-constant")


def test_prefix_machine_constant_explains_a_gap():
    fork = [pv(req("/ajax/bz", {"q": {"annotations_bool": {"is_mobile": False}}})) for _ in range(3)]
    r = row(u.classify(fork, fork, DOC, CONSTANTS, ACCEPTED), "/ajax/bz q.annotations_bool.is_mobile")
    assert (r["class"], r["explained_by"]) == ("gap", "machine-constant")  # uad.mobile, under the uad. prefix


def test_owner_limit_explains_a_gap():
    doc = dict(DOC, limits={"ram": {"why": "test", "approved": "2026-10-30"}})
    fork = [pv(bz(ram=8)) for _ in range(3)]
    out = u.classify(fork, fork, doc, CONSTANTS, ACCEPTED)
    assert row(out, "/ajax/bz q.payload.ram")["explained_by"] == "limit"
    assert out["counts"]["net_gap"] == 0 and out["counts"]["raw_gap"] == 1


def test_low_cardinality_gap_is_marked():
    fork = [pv(bz(cpu_cores=8)) for _ in range(3)]
    assert row(u.classify(fork, fork, DOC, CONSTANTS, ACCEPTED), "/ajax/bz q.payload.cpu_cores")["low_cardinality"] is True


def test_unmapped_constant_shared_with_stock_is_site_constant():
    fork = [pv(req("/ajax/bz", {"__a": "1"})) for _ in range(3)]
    doc = u.classify(fork, fork, DOC, CONSTANTS, ACCEPTED)
    assert row(doc, "/ajax/bz __a")["class"] == "site-constant"
    assert doc["counts"]["net_gap"] == 0


def test_unmapped_constant_that_differs_from_stock_is_a_gap():
    fork = [pv(req("/ajax/bz", {"zz": "F"})) for _ in range(3)]
    stock = [pv(req("/ajax/bz", {"zz": "S"})) for _ in range(3)]
    assert row(u.classify(fork, stock, DOC, CONSTANTS, ACCEPTED), "/ajax/bz zz")["class"] == "gap"


def test_path_in_one_fork_profile_is_sparse():
    fork = [pv(bz(ram=8)), pv(bz(cpu_cores=4)), pv(bz(cpu_cores=4))]
    assert row(u.classify(fork, fork, DOC, CONSTANTS, ACCEPTED), "/ajax/bz q.payload.ram")["class"] == "sparse"


def test_fork_only_path_is_listed_and_classified():
    fork = [pv(bz(ram=8)) for _ in range(3)]
    stock = [pv(bz(cpu_cores=4)) for _ in range(3)]
    doc = u.classify(fork, stock, DOC, CONSTANTS, ACCEPTED)
    assert "/ajax/bz q.payload.ram" in doc["fork_only"]
    assert row(doc, "/ajax/bz q.payload.ram")["class"] == "gap"


def test_mapped_field_never_captured_is_absent():
    fork = [pv(bz(ram=8)) for _ in range(3)]
    doc = u.classify(fork, fork, DOC, CONSTANTS, ACCEPTED)
    assert any(r["field"] == "sjd" and r["class"] == "absent" for r in doc["rows"])


def test_field_key_matches_whole_segments_only():
    assert u.field_key("/ajax/bz q.batch[].metadata.ram", DOC["fields"]) == "ram"
    assert u.field_key("/ajax/bz q.program", DOC["fields"]) is None
    assert u.field_key("/ajax/bz q.metadata.memory_stats.total_mem", DOC["fields"]) == "memory_stats.total_mem"


def test_other_endpoints_are_ignored():
    assert u.endpoint_path("https://www.facebook.com/api/graphql/") is None
    assert u.endpoint_path("https://web.facebook.com/ajax/qm/?a=1") == "/ajax/qm/"
    assert u.endpoint_path("https://www.facebook.com/ajax/bz") == "/ajax/bz"


def ident(mem, window=(1280, 720)):
    return {"config": {"navigator.deviceMemory": mem}, "launch": {"window": list(window), "dpr": 1}}


def test_same_device_memory_predicts_ram_shared():
    p = u.predict(DOC["fields"], [ident(8), ident(8), ident(8)])
    assert p["ram"] == "shared" and p["memory_stats.total_mem"] == "shared"


def test_different_device_memory_predicts_ram_varies():
    assert u.predict(DOC["fields"], [ident(4), ident(8), ident(8)])["ram"] == "varies"


def test_launch_keys_and_unknown():
    p = u.predict(DOC["fields"], [ident(8, (1280, 720)), ident(8, (1366, 768)), ident(8)])
    assert p["viewport_x"] == "varies"
    assert p["sjd"] == "unknown"
    assert p["webgpu_available"] == "shared"  # keys [] is the host's own value


def test_prediction_disagreement_is_listed():
    fork = [pv(bz(ram=8)) for _ in range(3)]
    doc = u.classify(fork, fork, DOC, CONSTANTS, ACCEPTED)
    u.attach_prediction(doc, u.predict(DOC["fields"], [ident(4), ident(8), ident(16)]))
    assert row(doc, "/ajax/bz q.payload.ram")["prediction"] == "varies"
    assert doc["disagreements"] == ["/ajax/bz q.payload.ram"]


def test_agreeing_prediction_is_not_listed():
    fork = [pv(bz(ram=8)) for _ in range(3)]
    doc = u.attach_prediction(u.classify(fork, fork, DOC, CONSTANTS, ACCEPTED),
                              u.predict(DOC["fields"], [ident(8)] * 3))
    assert doc["disagreements"] == []
