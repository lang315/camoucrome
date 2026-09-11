#!/usr/bin/env python3
"""OpenType name-table reader, stdlib only (it also runs on the Windows host's
Python 3.9 through winhost.powershell). faces(data) -> one dict per face:
family (ID 1), style (ID 2, normalised), full (ID 4), ps (ID 6); Windows
platform 3 en-US first, the Mac platform 1 English record as fallback (Apple's
system fonts carry these IDs there only). Handles .ttf/.otf/.ttc."""
import struct

STYLES = {"regular": "Regular", "normal": "Regular", "bold": "Bold", "italic": "Italic", "oblique": "Italic",
          "bold italic": "Bold Italic", "bold oblique": "Bold Italic"}


def _names(data, off):
    num = struct.unpack(">H", data[off + 4:off + 6])[0]
    for i in range(num):
        tag, _, to, ln = struct.unpack(">4sIII", data[off + 12 + 16 * i:off + 28 + 16 * i])
        if tag == b"name":
            n = data[to:to + ln]
            _, count, so = struct.unpack(">HHH", n[:6])
            out, mac = {}, {}
            for r in range(count):
                pid, _, lid, nid, l, o = struct.unpack(">HHHHHH", n[6 + 12 * r:18 + 12 * r])
                if nid not in (1, 2, 4, 6):
                    continue
                if pid == 3 and lid == 0x409 and nid not in out:
                    out[nid] = n[so + o:so + o + l].decode("utf-16-be", "replace")
                elif pid == 1 and lid == 0 and nid not in mac:  # Apple's system fonts carry 1/4/6 on the Mac platform only
                    mac[nid] = n[so + o:so + o + l].decode("mac_roman", "replace")
            return {**mac, **out}
    return {}


def faces(data):
    offs = [struct.unpack(">I", data[12 + 4 * i:16 + 4 * i])[0] for i in range(struct.unpack(">I", data[8:12])[0])] if data[:4] == b"ttcf" else [0]
    out = []
    for off in offs:
        n = _names(data, off)
        if n.get(1):
            sub = n.get(2, "Regular")
            out.append({"family": n[1], "style": STYLES.get(sub.lower(), sub), "full": n.get(4, n[1]), "ps": n.get(6, "")})
    return out


def faces_of_file(path):
    with open(path, "rb") as f:
        return faces(f.read())


if __name__ == "__main__":  # python3 fontnames.py <file>...  (the Windows host driver prints JSON per file)
    import json
    import sys
    print(json.dumps({p: faces_of_file(p) for p in sys.argv[1:]}))
