"""Browser rows for the 2026-09-24 review fixes (content_shell).

Each row reproduces one finding from
docs/superpowers/measurements/2026-09-24-review-triage.md. All of them were
RED on the pre-fix binary (branch tip ada4cdcfa4); the triage doc records the
values that were observed then.

R1  canvas:seed above 2^31-1 (4000000000) noises pixels of a canvas with an arc
    (was: 0 of 4096 on a solid fill); no pixel outside the arc's bounding box
    (plus a 2px margin) changes against unconfigured, and an interior solid
    pixel stays exact.
R2  getImageData of a sub-rect agrees with a full read on the same pixel.
R3  a transparent canvas with one half-transparent arc: every alpha-0 pixel
    has RGB 0, also next to the arc's anti-aliased edge (the canvas is eligible,
    so the noise path runs; seeded must differ from unconfigured, else vacuous).
R4  AudioBuffer copyToChannel then copyFromChannel is an identity under
    audio:seed (was: 128/128 samples differ)...
R5  ...and a rendered OfflineAudioContext buffer is still noised.
R6  queryLocalFonts is a function with no config (stock Linux has it).
R7  navigator.maxTouchPoints -1 falls back to the real value.
R8  navigator.languages alone sets the Intl locale (was: en-US).
R9  battery:charging false reports chargingTime Infinity (was: 0).
R10 the WebGL extension whitelist is intersected with the real set:
    getSupportedExtensions has no name without a tracker, getExtension agrees.
R11 enumerateDevices before a grant shows at most one entry per kind.
R12 a macOS preset with an explicit ua:platform "Windows" claims Windows
    (navigator.platform), not the preset's macOS.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import echo_server
import lib_shell

GL = lib_shell.SHELL_FLAGS + ["--use-angle=swiftshader",
                              "--enable-unsafe-swiftshader"]

# A solid fill is flat and stays stock under the target design, so the canvas
# carries an arc (eligible) and the pixels come back for a seeded-vs-unconfigured
# diff; R1 also checks the solid corner is untouched.
CANVAS_COUNT = """() => { const c=document.createElement('canvas'); c.width=64; c.height=64;
 const x=c.getContext('2d'); x.fillStyle='rgb(100,150,200)'; x.fillRect(0,0,64,64);
 x.fillStyle='#f60'; x.beginPath(); x.arc(32,32,20,0,7); x.fill();
 return JSON.stringify(Array.from(x.getImageData(0,0,64,64).data)); }"""

CANVAS_SHAPE = """() => { const c=document.createElement('canvas'); c.width=16; c.height=16;
 const x=c.getContext('2d');
 for(let i=0;i<16;i++){x.fillStyle=`rgb(${i*13},${200-i*9},${i*7})`;x.fillRect(i,0,1,16);}
 x.fillStyle='#f60'; x.beginPath(); x.arc(8,8,6,0,7); x.fill();
 const full=x.getImageData(0,0,16,16).data; let bad=0;
 for(let y=0;y<16;y++) for(let xx=0;xx<16;xx++){ const one=x.getImageData(xx,y,1,1).data;
   const o=(y*16+xx)*4; for(let k=0;k<4;k++) if(full[o+k]!==one[k]) bad++; }
 return JSON.stringify({subrect_mismatch:bad}); }"""

CANVAS_TRANSPARENT = """() => { const c=document.createElement('canvas'); c.width=64; c.height=64;
 const x=c.getContext('2d'); x.fillStyle='rgba(255,0,0,0.5)'; x.beginPath();
 x.arc(32,32,20,0,7); x.fill();
 return JSON.stringify(Array.from(x.getImageData(0,0,64,64).data)); }"""

AUDIO_ROUNDTRIP = """() => { const ctx=new OfflineAudioContext(1,128,44100);
 const b=ctx.createBuffer(1,128,44100); b.copyToChannel(new Float32Array(128).fill(0.5),0);
 const out=new Float32Array(128); b.copyFromChannel(out,0);
 let diff=0; for(let i=0;i<128;i++) if(out[i]!==0.5) diff++; return diff; }"""

AUDIO_RENDER = """async () => { const ctx=new OfflineAudioContext(1,4410,44100);
 const o=ctx.createOscillator(); o.connect(ctx.destination); o.start();
 const buf=await ctx.startRendering(); const d=buf.getChannelData(0);
 let s=0; for(let i=0;i<d.length;i++) s+=Math.abs(d[i]); return s; }"""

MISC = """() => JSON.stringify({qlf: typeof window.queryLocalFonts,
 mtp: navigator.maxTouchPoints, intl: Intl.DateTimeFormat().resolvedOptions().locale,
 platform: navigator.platform})"""

BATTERY = """async () => { const b=await navigator.getBattery();
 return JSON.stringify({charging:b.charging, chargingTime:String(b.chargingTime)}); }"""

WEBGL = """() => { const g=document.createElement('canvas').getContext('webgl');
 if(!g) return 'nogl'; const list=g.getSupportedExtensions();
 return JSON.stringify({list, bogus: g.getExtension('WEBGL_bogus_not_real')===null,
   float: g.getExtension('OES_texture_float')!==null,
   every_listed_gets: list.every(n=>g.getExtension(n)!==null)}); }"""

MEDIA = """async () => { const d=await navigator.mediaDevices.enumerateDevices();
 const k={}; for(const x of d) k[x.kind]=(k[x.kind]||0)+1; return JSON.stringify(k); }"""


def one(config, expr, **kw):
    vals, err = lib_shell.session(
        None if config is None else json.dumps(config), [expr], **kw)
    if err:
        raise err
    return vals[0]


def main():
    url, _, stop = echo_server.start([])
    rows = {}
    notes = []

    def row(name, fn):
        try:
            ok, got = fn()
        except Exception as exc:  # noqa: BLE001 - any fault is a FAIL row
            ok, got = False, repr(exc)
        rows[name] = ok
        if not ok:
            notes.append(f"{name}: {got}")

    try:
        def seeded_canvas():
            s = json.loads(one({"canvas:seed": 4000000000, "canvas:noiseDensity": 1.0},
                               CANVAS_COUNT))
            u = json.loads(one(None, CANVAS_COUNT))
            diff = [i // 4 for i in range(0, len(s), 4) if s[i:i + 4] != u[i:i + 4]]
            outside = [p for p in diff if not (10 <= p % 64 < 54 and 10 <= p // 64 < 54)]
            at = (4 * 64 + 4) * 4  # interior solid pixel, >= 2px from arc and border
            inner = s[at:at + 4] == u[at:at + 4] == [100, 150, 200, 255]
            return len(diff) > 0 and not outside and inner, (len(diff), len(outside), inner)
        row("R1 seed 4000000000 noises the arc canvas, not the solid fill", seeded_canvas)
        shape = {}
        def canvas_shape():
            shape.update(json.loads(one(
                {"canvas:seed": 12345, "canvas:noiseDensity": 1.0},
                CANVAS_SHAPE)))
            return shape["subrect_mismatch"] == 0, shape
        row("R2 sub-rect getImageData agrees with full read", canvas_shape)
        def transparent():
            s = json.loads(one({"canvas:seed": 12345, "canvas:noiseDensity": 1.0},
                               CANVAS_TRANSPARENT))
            u = json.loads(one(None, CANVAS_TRANSPARENT))
            a0 = [i for i in range(0, len(s), 4) if s[i + 3] == 0]
            tinted = sum(1 for i in a0 if s[i] | s[i + 1] | s[i + 2])
            changed = sum(1 for i in range(0, len(s), 4) if s[i:i + 4] != u[i:i + 4])
            return tinted == 0 and a0 and changed > 0, (tinted, len(a0), changed)
        row("R3 half-transparent arc canvas has no RGB under alpha 0", transparent)
        row("R4 copyToChannel/copyFromChannel is an identity",
            lambda: (lambda n: (n == 0, n))(
                one({"audio:seed": 12345}, AUDIO_ROUNDTRIP)))
        def rendered():
            a = one({"audio:seed": 12345}, AUDIO_RENDER)
            b = one(None, AUDIO_RENDER)
            return a != b, (a, b)
        row("R5 rendered audio is still noised", rendered)
        # [SecureContext]: about:blank would read undefined on stock too.
        row("R6 queryLocalFonts present with no config",
            lambda: (lambda m: (m["qlf"] == "function", m))(
                json.loads(one(None, MISC, navigate_to=url))))
        def touch():
            real = json.loads(one(None, MISC))["mtp"]
            got = json.loads(one({"navigator.maxTouchPoints": -1}, MISC))["mtp"]
            return got == real, (got, real)
        row("R7 maxTouchPoints -1 falls back to real", touch)
        row("R8 navigator.languages alone sets Intl locale",
            lambda: (lambda m: (m["intl"] == "de-DE", m))(json.loads(
                one({"navigator.languages": ["de-DE", "de"]}, MISC))))
        row("R9 charging:false reports chargingTime Infinity",
            lambda: (lambda m: (m["chargingTime"] == "Infinity", m))(json.loads(
                one({"battery:charging": False}, BATTERY, navigate_to=url))))
        def webgl():
            m = json.loads(one({"webGl:supportedExtensions": [
                "WEBGL_bogus_not_real", "OES_texture_float",
                "WEBGL_debug_renderer_info"]}, WEBGL, extra_flags=GL))
            ok = ("WEBGL_bogus_not_real" not in m["list"] and m["bogus"]
                  and m["float"] and m["every_listed_gets"]
                  and set(m["list"]) <= {"OES_texture_float",
                                         "WEBGL_debug_renderer_info"})
            return ok, m
        row("R10 WebGL whitelist intersects the real set", webgl)
        row("R11 at most one device per kind before a grant",
            lambda: (lambda m: (m and max(m.values()) == 1, m))(json.loads(
                one({"mediaDevices:enabled": True, "mediaDevices:micros": 3,
                     "mediaDevices:seed": 7}, MEDIA, navigate_to=url))))
        def preset_os():
            vals, err = lib_shell.session(
                json.dumps({"ua:platform": "Windows"}), [MISC],
                preset=json.dumps({"milestone": 153, "os": "macOS"}))
            if err:
                raise err
            m = json.loads(vals[0])
            return m["platform"] == "Win32", m
        row("R12 explicit ua:platform over a macOS preset claims Windows",
            preset_os)
    finally:
        stop()

    for name, ok in rows.items():
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for n in notes:
        print("  ", n)
    expected = 12
    passed = sum(rows.values())
    print(f"{passed}/{expected} " + (
        "ALL_PASS" if passed == expected == len(rows) else "FAIL"))
    sys.exit(0 if passed == expected == len(rows) else 1)


if __name__ == "__main__":
    main()
