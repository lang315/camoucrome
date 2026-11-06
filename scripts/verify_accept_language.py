"""B5: Accept-Language follows the config with no launcher flag.

Raw `chrome` with CAMOU_CONFIG and no --accept-lang. Header and JS come from the
same session (lib_shell has no launcher in it). RED on a build without the
accept-language-from-config patch: A1 and A2 send en-US,en;q=0.9.

A1 navigator.languages decides the header, and JS agrees with it.
A2 only locale:tag: the header follows it.
A3 an explicit --accept-lang wins over the config.
A4 no config: the real default (rule 5).
A5 a language with a CR LF in it is ignored: the browser starts, the header is
   the default (bad config never crashes).
"""
import json
import sys

import echo_server
import lib_shell

EXPECTED_ROWS = 5
LANGS = "navigator.languages.join()"
DEFAULT = "en-US,en;q=0.9"


def run(config, extra=()):
    base_url, headers_for, stop = echo_server.start(lib_shell.ACCEPT_CH)
    try:
        values, err = lib_shell.session(json.dumps(config), [LANGS], navigate_to=base_url, shell=lib_shell.CHROME,
                                        extra_flags=lib_shell.CHROME_FLAGS + list(extra))
        if err is not None:
            return None, None, str(err)[:200]
        wire = headers_for("/probe.js") or {}
    finally:
        stop()
    return values[0], {k.lower(): v for k, v in wire.items()}.get("accept-language"), None


def rows():
    fr = {"locale:tag": "fr-FR", "navigator.language": "fr-FR", "navigator.languages": ["fr-FR", "fr"]}
    js, al, err = run(fr)
    yield "A1 navigator.languages decides the header; JS agrees", al == "fr-FR,fr;q=0.9" and js == "fr-FR,fr", (js, al, err)
    js, al, err = run({"locale:tag": "de-DE"})
    yield "A2 locale:tag alone decides the header", bool(al) and al.startswith("de-DE"), (js, al, err)
    js, al, err = run(fr, ["--accept-lang=ja"])
    yield "A3 an explicit --accept-lang wins", bool(al) and al.startswith("ja"), (js, al, err)
    js, al, err = run({})
    yield "A4 no config: the real default", al == DEFAULT, (js, al, err)
    js, al, err = run({"navigator.languages": ["fr\r\nX-Bad: 1"]})
    yield "A5 a bad language is ignored, no crash", err is None and al == DEFAULT, (js, al, err)


def main():
    results = list(rows())
    for name, ok, seen in results:
        print(f"{'PASS' if ok else 'FAIL'} {name}" + ("" if ok else f" (js, header, error) = {seen!r}"))
    if len(results) != EXPECTED_ROWS:
        print(f"FAIL expected {EXPECTED_ROWS} rows, ran {len(results)}")
        return 1
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
