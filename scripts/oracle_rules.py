"""The host oracle's comparison vocabulary, shared by verify_host_oracle.py
(the fork against the committed stock baseline) and step2_rows.py (the fork
against stock live, roadmap step 2). Pure: no browser, no host."""

# Values that legitimately follow the identity or the machine: compare type only.
SHAPE_ONLY = {"nav.hardwareConcurrency", "nav.deviceMemory", "nav.language", "nav.languages", "screen.width", "screen.height", "screen.availWidth",
              "screen.availHeight", "screen.availLeft", "screen.availTop", "win.dpr", "win.screenX", "win.screenY", "win.outerMinusInnerW",
              "win.outerMinusInnerH", "intl.dtf.timeZone", "intl.dtf.locale", "intl.nf.locale", "intl.collator", "intl.date0", "storage.quotaGiB",
              "storage.usage", "perfMem.jsHeapSizeLimit", "audio.baseLatency", "audio.outputLatency", "audioFp", "canvas.text", "canvas.shape",
              "gpu.info.description", "gpu.info.device", "gpu.info.vendor", "gpu.info.architecture", "gpu.limits.maxBufferSize",
              "gpu.limits.maxStorageBufferBindingSize", "gpu.features", "mediaDevices", "voices", "err.stack", "uadHigh.uaFullVersion",
              "uadHigh.fullVersionList", "uad.brands", "navConnection.rtt", "navConnection.downlink", "media.(color-gamut: p3)",
              "media.(dynamic-range: high)", "media.(video-dynamic-range: high)", "media.(prefers-color-scheme: dark)", "keyboard.size"}


def flatten(v, prefix=""):
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            out.update(flatten(x, f"{prefix}.{k}" if prefix else k))
        return out
    return {prefix: v}


# The brands whose version is the browser build's own. A GREASE brand ("Not:A-Brand";v="8.0.0.0") is not.
BUILD_BRANDS = ("Chromium", "Google Chrome")


def read_pin(upstream_env_text):
    """CHROMIUM_TAG from upstream.env: the full version the fork reports (never hard-coded here)."""
    for line in upstream_env_text.splitlines():
        if line.startswith("CHROMIUM_TAG="):
            return line.split("=", 1)[1].strip().strip('"')
    raise ValueError("no CHROMIUM_TAG in upstream.env")


def expected_full_list(host_full, pin):
    """The full-version list the fork must report: the host stock's list, brands and order exact, GREASE exact,
    with only the Chromium / Google Chrome entries' version replaced by the pin's full version. The stock control
    may be another patch of the pin's build (the frozen .80 against the .48 pin), so its own patch number is
    not the fork's to copy -- and a fork that reports 156.0.8078.0 must not pass."""
    return [{**i, "version": pin} if i["brand"] in BUILD_BRANDS else dict(i) for i in host_full]
