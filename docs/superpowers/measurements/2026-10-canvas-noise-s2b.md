# Canvas noise S2b: RED and cost before the change

Measurements for `docs/superpowers/specs/2026-10-06-canvas-noise-s2b-design.md`
and its implementation plan. This file holds the state of the build before S2b
(PR #27 head, box commit `55d16f07`): the new verify rows C21-C29 failing, and
the cost baseline. Later sections record the same after each task.

## 1. RED on the build before S2b (WSL, `55d16f07`)

`scripts/verify_sp3a.py` at branch commit `301ed1e`, 0-step build (the box
build is current). The 32 verdict lines, verbatim (sorted by name, as the
script prints them):

```
PASS  1  seeded toDataURL deterministic across two reads
PASS  10 accessors native + window keys unchanged
PASS  11 flat drawings read as unconfigured (solid, edge, 1px line, WebGL clear, worker)
PASS  12 putImageData round trip exact
PASS  13 drawImage and createImageBitmap copies agree with getImageData
PASS  14 oracle text (>=6) and shape (8) canvases vary over 8 seeds, none stock
PASS  15 text under ctx.scale(40,40) lands within 1 device px of unconfigured
PASS  16 decoded image drawn on an eligible canvas reads as unconfigured
PASS  17 readPixels at PACK_ALIGNMENT 8, odd width, agrees with the default layout
PASS  18 WebGL2 PACK_ROW_LENGTH/SKIP_PIXELS/SKIP_ROWS read agrees with the default read
PASS  19 readPixels rect past the buffer: in-buffer part equals the default read, not unconfigured
PASS  2  seeded toDataURL differs from stock
PASS  20 readPixels rejected by GL leaves the buffer untouched
FAIL  21 one arc at two whole-pixel offsets gets the same noise
FAIL  22 a draw elsewhere does not change a region's noise
FAIL  23 arc plus putImageData elsewhere: arc noised, pattern exact
FAIL  24a diagonal lineTo triangle carries noise
FAIL  24b round-cap stroke carries noise
FAIL  24c curved clip() + fillRect carries noise
FAIL  24d fillRect with shadowBlur carries noise
FAIL  25 a reused canvas reads like a fresh one
FAIL  26 createPattern alone marks nothing; a pattern fill reads exact
FAIL  27 checkerboard under a diagonal line stays exact (coverage, not bbox)
FAIL  28 WebGL readPixels sub-rect equals the full read's part, byte for byte
FAIL  29 WebGL toDataURL agrees with readPixels on every opaque pixel
PASS  3  unconfigured toDataURL byte-identical to stock
PASS  4  seeded toBlob deterministic and differs from stock
PASS  5  seeded getImageData deterministic, differs from stock, off==stock
PASS  6  seeded readPixels of a gradient triangle deterministic, differs from unconfigured
PASS  7  seeded OffscreenCanvas.convertToBlob deterministic, differs from unconfigured
PASS  8  worker OffscreenCanvas readback deterministic, differs from unconfigured (parity)
PASS  9  DevTools screenshot of a text-free scene identical seeded vs unconfigured
```

Notes for C21-C29, verbatim:

```
21 : seeded {'ha': 3183026031, 'hb': 882312527, 'e': 70}, unconfigured {'ha': 612045226, 'hb': 612045226, 'e': 70}
22 : seeded {'r1': 33446050, 'r2': 1417751380, 'e': 70}, unconfigured {'r1': 612045226, 'r2': 612045226, 'e': 70}
23 : seeded {'arc': 612045226, 'exact': True, 'e': 70}, unconfigured {'arc': 612045226, 'exact': True, 'e': 70}
24a: seeded {'h': 4071154615, 'e': 192}, unconfigured {'h': 4071154615, 'e': 192}
24b: seeded {'h': 504083845, 'e': 16}, unconfigured {'h': 504083845, 'e': 16}
24c: seeded {'h': 1193301648, 'e': 136}, unconfigured {'h': 1193301648, 'e': 136}
24d: seeded {'h': 2875827717, 'e': 164}, unconfigured {'h': 2875827717, 'e': 164}
25 : seeded {'h1': 1847293814, 'h2': 712641204, 'e': 78}, unconfigured {'h1': 1847293814, 'h2': 1847293814, 'e': 78}
26 : seeded {'p1': 1847293814, 'e': 78, 'hB': 3555660037}, unconfigured {'p1': 1847293814, 'e': 78, 'hB': 3555660037}
27 : seeded {'h': 23700512, 'e': 1444}, unconfigured {'h': 3912342789, 'e': 1444}
28 : seeded {'diff': 136, 'h': 4118271887}, unconfigured {'diff': 0, 'h': 1106472337}
29 : seeded {'diff': 207, 'opaque': 4096, 'h': 1317655965}, unconfigured {'diff': 0, 'opaque': 4096, 'h': 2741506969}
```

Result: `FAIL`, rc=1. C1-C20 PASS; C21-C29 FAIL (12 lines); no row is vacuous
(every unconfigured guard held, `e` > 0).

## 2. Cost before S2b

`scripts/measure_canvas_cost.py` on WSL `content_shell` (CPU raster,
SwiftShader GL), seeded against unconfigured. These are PR #27's costs:

```
draw: seeded median 35.70 ms, unconfigured median 24.90 ms, seeded/unconfigured ratio 1.43
readPixels 64x64: seeded median 0.40 ms, unconfigured median 0.30 ms, seeded/unconfigured ratio 1.33
readPixels 1024x1024: seeded median 28.60 ms, unconfigured median 1.80 ms, seeded/unconfigured ratio 15.89
```
