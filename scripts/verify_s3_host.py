"""S3 host rows: enumerateDevices() under a grant, fork vs stock, on the Windows host.

S3-W1: both arms list a non-empty audiooutput deviceId (the host's real
speaker). Compared by shape, never by value; RED on main, where the fork's
ids are all "".
S3-W2: the fork's phantom audioinput starts with "default" and
"communications", and their label prefixes ("<prefix> - ") equal the
prefixes of the real audiooutput sentinels on the same page.
S3-W3: the fork's phantom audioinput (the entry that is not default or
communications) has getCapabilities() with sampleRate, channelCount and latency
ranges that are well formed (sampleRate min > 0, channelCount max >= 1, 0 <= latency min <= max). The
stock host has no mic, so there is no stock comparison.
S3-W4: one profile, two documents of one origin: every fork deviceId (phantom
and real; sentinels, else 64 hex) is equal across them and every non-empty groupId differs; the stock
audiooutput shows the same relation, or the row fails.
S3-W5: with mediaDevices:micros=0, webcams=0, speakers=1 under a grant, every
non-sentinel audiooutput deviceId is 64 hex and there is at least one (the
grant test must not need an input device).
S3-W6: setSinkId(<that non-sentinel audiooutput id>) resolves and sinkId reads
back equal, on the control and the fork (the phantom speaker is authorized).
S3-W7: one profile dir, three launches: same seed twice gives equal non-sentinel
ids; a different seed gives a disjoint set.
Headless only: no window in the console session. Run in the client venv on
the host while holding the build lock, as measure_step2.py is run.
Prints kinds, id lengths, booleans, label prefixes and numeric ranges only.
"""

import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import measure_step2 as m2

EXPECTED = 7
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PAGE = b"<!doctype html><title>s3</title><body></body>"
ENUM = ("navigator.mediaDevices.enumerateDevices().then(ds => ds.map(d => "
        "({kind: d.kind, deviceId: d.deviceId, groupId: d.groupId, label: d.label})))")
CAPS = ("navigator.mediaDevices.enumerateDevices().then(ds => ds"
        ".filter(d => d.kind === 'audioinput' && d.deviceId !== 'default' && d.deviceId !== 'communications')"
        ".map(d => JSON.parse(JSON.stringify(d.getCapabilities()))))")
SINK = ("(async () => { const ds = await navigator.mediaDevices.enumerateDevices();"
        " const o = ds.find(d => d.kind === 'audiooutput' && !['', 'default', 'communications'].includes(d.deviceId));"
        " if (!o) return 'none'; const a = new Audio();"
        " try { await a.setSinkId(o.deviceId); return a.sinkId === o.deviceId ? 'ok' : 'mismatch'; }"
        " catch (e) { return e.name; } })()")
OUTS = ("navigator.mediaDevices.enumerateDevices().then(ds => ds.filter(d => d.kind === 'audiooutput'"
        " && !['', 'default', 'communications'].includes(d.deviceId)).map(d => d.deviceId))")


def one(pw, arm, script, config="arm", user_data_dir=None, url=None):
    """One headless launch, camera and mic granted, one script result."""
    with m2.opened(pw, arm, "headless", user_data_dir=user_data_dir, config=config) as ctx:
        ctx.grant_permissions(["camera", "microphone"], origin=url)
        page = m2.first_page(ctx)
        page.goto(url, wait_until="load")
        return page.evaluate(script)


def session(pw, arm):
    """One context, two same-origin documents: (listing 1, listing 2, phantom mic capabilities)."""
    with m2.serve(PAGE) as url, m2.opened(pw, arm, "headless") as ctx:
        ctx.grant_permissions(["camera", "microphone"], origin=url)
        page = m2.first_page(ctx)
        page.goto(url, wait_until="load")
        first = page.evaluate(ENUM)
        caps = page.evaluate(CAPS)
        page.goto(url + "?second", wait_until="load")
        return first, page.evaluate(ENUM), caps


SENTINELS = ("default", "communications")


def prefix(d):
    """The label prefix of a sentinel entry; for any other entry only whether it has one, never its text."""
    i = d["label"].find(" - ")
    if d["deviceId"] in SENTINELS:
        return d["label"][:i] if i >= 0 else None
    return i >= 0


def id_ok(d):
    return d["deviceId"] in SENTINELS or bool(HEX64.match(d["deviceId"]))


def main():
    from patchright.sync_api import sync_playwright
    stock = os.path.join(os.environ.get("CAMOU_STOCK_APP", m2.STOCK_APP), "chrome.exe")
    control = m2.Arm("control", stock, None)
    fork = m2.Arm("fork", os.environ["CAMOU_FORK_EXE"], m2.identity(1))
    with sync_playwright() as pw:
        got = {a.name: session(pw, a) for a in (control, fork)}
        cfg = dict(fork.ident["config"])
        assert "mediaDevices:seed" in cfg, "identity has no mediaDevices:seed"
        w5cfg = dict(cfg, **{"mediaDevices:micros": 0, "mediaDevices:webcams": 0,
                             "mediaDevices:speakers": 1})
        with m2.serve(PAGE) as url:
            w5 = one(pw, fork, OUTS, config=w5cfg, url=url)
            sink = {a.name: one(pw, a, SINK, url=url) for a in (control, fork)}
            import tempfile
            udd = tempfile.mkdtemp(prefix="s3b-w7-")
            seed_b = dict(cfg, **{"mediaDevices:seed": (cfg["mediaDevices:seed"] % 4000000000) + 1})
            w7 = [one(pw, fork, OUTS, config=c, user_data_dir=udd, url=url)
                  for c in (cfg, cfg, seed_b)]
    shape = {n: [(d["kind"], len(d["deviceId"]), prefix(d)) for d in s[0]] for n, s in got.items()}
    print(f"shape control={shape['control']}")
    print(f"shape fork={shape['fork']}")

    def out_ok(lst):
        outs = [d for d in lst if d["kind"] == "audiooutput" and d["deviceId"] not in SENTINELS]
        return len(outs) > 0 and all(HEX64.match(d["deviceId"]) for d in outs)
    w1 = out_ok(got["control"][0]) and out_ok(got["fork"][0])

    f = got["fork"][0]
    ins = [d for d in f if d["kind"] == "audioinput"]
    outs = {d["deviceId"]: prefix(d) for d in f if d["kind"] == "audiooutput"}
    w2 = (len(ins) == 3 and bool(HEX64.match(ins[2]["deviceId"])) and ins[0]["deviceId"] == "default" and ins[1]["deviceId"] == "communications"
          and prefix(ins[0]) is not None and prefix(ins[0]) == outs.get("default")
          and prefix(ins[1]) is not None and prefix(ins[1]) == outs.get("communications"))

    caps = got["fork"][2]
    c = caps[0] if len(caps) == 1 else {}
    print(f"caps devices={len(caps)} keys={sorted(c)} sampleRate={c.get('sampleRate')} "
          f"channelCount={c.get('channelCount')} latency_present={'latency' in c} latency={c.get('latency')}")
    sr, cc, lat = c.get("sampleRate"), c.get("channelCount"), c.get("latency")
    w3 = (len(caps) == 1 and isinstance(sr, dict) and isinstance(cc, dict) and isinstance(lat, dict)
          and 0 < sr.get("min", 0) <= sr.get("max", -1) and cc.get("max", 0) >= 1
          and 0 <= lat.get("min", -1) <= lat.get("max", -2))

    def stable(arm, kinds=None):
        a, b = got[arm][0], got[arm][1]
        a = [d for d in a if kinds is None or d["kind"] in kinds]
        b = [d for d in b if kinds is None or d["kind"] in kinds]
        ids = (len(a) > 0 and all(id_ok(d) for d in a + b)
               and [d["deviceId"] for d in a] == [d["deviceId"] for d in b])
        grp = [(x["groupId"], y["groupId"]) for x, y in zip(a, b) if x["groupId"] or y["groupId"]]
        return ids, bool(grp) and all(x and y and x != y for x, y in grp), len(a), len(grp)
    s_ids, s_grp, s_n, s_g = stable("control", ("audiooutput",))
    f_ids, f_grp, f_n, f_g = stable("fork")
    print(f"stability control audiooutput: ids_equal={s_ids} groups_differ={s_grp} entries={s_n} grouped={s_g}")
    print(f"stability fork all: ids_equal={f_ids} groups_differ={f_grp} entries={f_n} grouped={f_g}")
    w4 = f_ids and f_grp and s_ids and s_grp

    w5_ok = len(w5) > 0 and all(HEX64.match(i) for i in w5)
    print(f"W5 outs={len(w5)} hex={w5_ok}")
    w6_ok = sink["control"] == "ok" and sink["fork"] == "ok"
    print(f"W6 sink control={sink['control']} fork={sink['fork']}")
    a1, a2, b = (sorted(x) for x in w7)
    w7_ok = len(a1) > 0 and a1 == a2 and set(a1).isdisjoint(b)
    print(f"W7 same-seed equal={a1 == a2} other-seed disjoint={set(a1).isdisjoint(b)} n={len(a1)}")

    rows = {"S3-W1": w1, "S3-W2": w2, "S3-W3": w3, "S3-W4": w4,
            "S3-W5": w5_ok, "S3-W6": w6_ok, "S3-W7": w7_ok}
    assert len(rows) == EXPECTED
    for k, ok in rows.items():
        print(f"{k}: {'PASS' if ok else 'FAIL'}")
    n = sum(rows.values())
    print(f"{n}/{EXPECTED} " + ("ALL_PASS" if n == EXPECTED else "FAIL"))
    sys.exit(0 if n == EXPECTED else 1)


if __name__ == "__main__":
    main()
