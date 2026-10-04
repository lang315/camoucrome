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
