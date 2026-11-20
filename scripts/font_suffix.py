"""Chromium's Windows weight/stretch suffix fallback, as the fonts:list gate mirrors it
(specs/2026-11-20-font-weight-suffix-gate-design.md).

Stock Windows Chrome (font_cache_skia_win.cc, FontCache::CreateFontPlatformData) resolves a family name that is not a
real family by stripping ONE suffix -- the weight table first, then the stretch table, first match in table order --
and looking the rest up at that weight or stretch. The camoucfg copy (additions/camoucfg/mask_config.cc) and these
tuples are held equal by scripts/test_font_suffix.py, and to Chromium's text when CAMOU_CHROMIUM_SRC is set."""

WEIGHT_SUFFIXES = (" thin", " extralight", " ultralight", " light", " regular", " medium", " demibold", " semibold",
                   " extrabold", " ultrabold", " black", " heavy")
STRETCH_SUFFIXES = (" ultracondensed", " extracondensed", " condensed", " narrow", " semicondensed", " semiexpanded",
                    " expanded", " extraexpanded", " ultraexpanded")
TOL = 1.0  # px, as verify_windows_fonts.JITTER_TOL


def strip_suffix(name):
    """The name without its one Chromium suffix (weight table first), or None when it has none."""
    low = name.lower()
    for table in (WEIGHT_SUFFIXES, STRETCH_SUFFIXES):
        for s in table:
            if low.endswith(s):
                return name[:-len(s)]
    return None


def collisions(fonts):
    """(os, family, base) for every family a draw can hide whose suffix base is always listed or sits in another
    optional group: hiding it would not hide it, because the gate admits the name through its base and Windows then
    resolves the real face. settings/fonts.json must give []."""
    out = []
    for os_name, fam in fonts["families"].items():
        if not isinstance(fam, dict) or "base" not in fam:
            continue  # no draw: every captured family is listed
        always = {f.casefold(): f for f in list(fam["base"]) + list(fonts.get("extra_allowed", {}).get(os_name, []))}
        groups = {g: v["families"] for g, v in sorted(fam.get("groups", {}).items())}
        if "win11" in fam:
            groups["win11"] = fam["win11"]["families"]
        grouped = {f.casefold() for fs in groups.values() for f in fs}
        never = [f for f in fam["list"] if f.casefold() not in always and f.casefold() not in grouped]
        if never:  # captured, in neither base nor a group: every draw hides it
            groups["never-drawn"] = never
        where = {f.casefold(): (g, f) for g, fs in groups.items() for f in fs}
        for g, families in groups.items():
            for f in families:
                base = strip_suffix(f)
                if base is None:
                    continue
                if base.casefold() in always:
                    out.append((os_name, f, always[base.casefold()]))
                elif base.casefold() in where and where[base.casefold()][0] != g:
                    out.append((os_name, f, where[base.casefold()][1]))
    return out


def f6a(fm, fw, sm, names, resolved):
    """Suffix names of listed families resolve in the fork's window and worker wherever stock resolves them; stock
    must resolve every one, or the row measured nothing."""
    return (fm is not None and fw is not None and sm is not None and all(resolved(sm, n) for n in names)
            and all(resolved(fm, n) and resolved(fw, n) for n in names))


def f6b(fm, fw, sm, name, resolved):
    """An unlisted host family plus a suffix stays hidden from the fork while stock resolves it."""
    return (fm is not None and fw is not None and sm is not None and resolved(sm, name)
            and not resolved(fm, name) and not resolved(fw, name))


def f6c(fm, sm, claimed, resolved, tol=TOL):
    """True/False: under a list with Arial and without Arial Narrow, "Arial Narrow" measures as plain Arial -- what
    stock's suffix path renders on a machine without the face, Arial having no condensed face. None: NOT MEASURED --
    the host has no Arial Narrow face distinct from Arial, or the list shows it."""
    listed = {f.casefold() for f in claimed}
    if (fm is None or sm is None or "arial" not in listed or "arial narrow" in listed
            or not resolved(sm, "Arial Narrow") or abs(sm["__narrow"] - sm["__arial"]) <= tol):
        return None
    return abs(fm["__narrow"] - fm["__arial"]) <= tol


def f6d(fm, fw, sm, name, resolved):
    """Under a macOS identity (which keeps fonts:alias) on a Windows build, a suffix name of a listed family stays
    blocked while stock resolves it: the suffix path runs only under a Windows claim, else "Arial Medium" would reach
    the host's real Arial while "Arial" renders its alias target."""
    return (fm is not None and fw is not None and sm is not None and resolved(sm, name)
            and not resolved(fm, name) and not resolved(fw, name))
