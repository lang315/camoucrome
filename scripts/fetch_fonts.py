#!/usr/bin/env python3
"""Downloads the open font bundle (settings/fonts.json `bundle`) into fonts/
(git-ignored), verifying each download's sha256; a blank sha256 is filled in
and printed on first fetch so it can be committed. Extracts only the listed
files into fonts/<family>/ and fetches each entry's licence beside them."""
import hashlib
import io
import json
import pathlib
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "camoucrome-fetch-fonts"})
    ctx = None
    try:  # the Mac's framework Python ships no CA bundle; certifi's is used when present
        import certifi
        import ssl
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    try:
        return urllib.request.urlopen(req, timeout=180, context=ctx).read()
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" not in str(e):
            raise
        # A system HTTPS proxy that re-signs TLS (a local VPN/inspection app) fails
        # verification; retry direct, still verified. The sha256 pins are the real gate.
        print(f"  {url.rsplit('/', 1)[1]}: TLS verification failed via the system proxy, retrying without it", file=sys.stderr)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx))
        return opener.open(req, timeout=180).read()


def fetch(entry, dest):
    d = dest / entry["family"]
    d.mkdir(parents=True, exist_ok=True)
    wanted = set(entry["files"])
    if "urls" in entry:  # one file per URL (google/fonts raw files); sha256 is a list aligned with urls
        digests = []
        for u in entry["urls"]:
            data = get(u)
            digests.append(hashlib.sha256(data).hexdigest())
            (d / pathlib.Path(urllib.request.unquote(u)).name).write_bytes(data)
        if entry["sha256"] and digests != entry["sha256"]:
            sys.exit(f"{entry['name']}: sha256 {digests} != {entry['sha256']}")
        (d / "LICENSE.txt").write_bytes(get(entry["licence_url"]))
        return digests
    data = get(entry["url"])
    digest = hashlib.sha256(data).hexdigest()
    if entry["sha256"] and digest != entry["sha256"]:
        sys.exit(f"{entry['name']}: sha256 {digest} != {entry['sha256']}")
    if entry["url"].endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for n in z.namelist():
                if pathlib.Path(n).name in wanted:
                    (d / pathlib.Path(n).name).write_bytes(z.read(n))
    elif entry["url"].endswith((".tar.gz", ".tgz", ".tar.xz")):
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            for m in t.getmembers():
                if m.isfile() and pathlib.Path(m.name).name in wanted:
                    (d / pathlib.Path(m.name).name).write_bytes(t.extractfile(m).read())
    else:
        name = pathlib.Path(urllib.request.unquote(entry["url"])).name
        (d / name).write_bytes(data)
    missing = [f for f in wanted if not (d / f).exists()]
    if missing:
        sys.exit(f"{entry['name']}: not in the download: {missing}")
    (d / "LICENSE.txt").write_bytes(get(entry["licence_url"]))
    return digest


def main():
    dest = pathlib.Path(sys.argv[sys.argv.index("--dest") + 1]) if "--dest" in sys.argv else ROOT / "fonts"
    p = ROOT / "settings" / "fonts.json"
    fonts = json.loads(p.read_text())
    filled = False
    for e in fonts["bundle"]:
        digest = fetch(e, dest)
        size = sum(f.stat().st_size for f in (dest / e["family"]).iterdir())
        print(f"{e['name']}: {str(digest)[:12]} {size // 1024} KB -> {dest / e['family']}")
        if not e["sha256"]:
            e["sha256"] = digest
            filled = True
    if filled:
        p.write_text(json.dumps(fonts, indent=1, ensure_ascii=False) + "\n")
        print("sha256 fields filled: commit settings/fonts.json")


if __name__ == "__main__":
    main()
