"""Captures a preset -- the minimum identifying set of THIS machine as the
fork reports it with no configuration -- in the shape preset_loader.cc
expands (see its field table). Prints the JSON; redirect it into
settings/presets/chromium-<milestone>.json.

Everything in the file is observed, nothing asserted: the milestone comes
from the UA-CH fullVersionList, the OS from userAgentData.platform (so this
needs the `chrome` binary -- content_shell reports platform "Unknown"), the
GPU strings from WEBGL_debug_renderer_info and the parameter table from
getParameter over a fixed numeric pname list. Fonts are omitted: nothing in a
page can enumerate installed fonts without a permission prompt. dpr and
sampleRate are recorded as provenance only; the loader does not emit them.

A capture on the build box is a SMOKE preset (headless, SwiftShader), useful
for exercising the loader end to end and nothing else. A distributable
preset is A3 #2's job: captured on real hardware, on the OS it claims.
"""
import datetime
import json
import sys

import echo_server
import lib_shell

GL_FLAGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]

# Numeric pnames the fork replays through webGl:parameters; string pnames
# (VENDOR, RENDERER, VERSION, SHADING_LANGUAGE_VERSION) are identity, held by
# gpu.vendor / gpu.renderer instead.
PNAMES = [0x0D33, 0x8869, 0x8DFB, 0x8DFC, 0x8DFD, 0x8B4D, 0x8872, 0x8B4C,
          0x851C, 0x84E8, 0x0D3A, 0x846E, 0x846D]

PROBE = """async () => {
  const c = document.createElement('canvas');
  const gl = c.getContext('webgl');
  if (!gl) return { err: 'no-context' };
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  if (!ext) return { err: 'no-debug-renderer-info-ext' };
  const parameters = {};
  for (const p of %s) {
    const v = gl.getParameter(p);
    parameters[String(p)] = ArrayBuffer.isView(v) ? Array.from(v) : v;
  }
  const he = await navigator.userAgentData.getHighEntropyValues(
      ['platformVersion', 'fullVersionList']);
  const chromium = he.fullVersionList.find(b => b.brand === 'Chromium');
  return {
    milestone: chromium ? parseInt(chromium.version.split('.')[0], 10) : null,
    os: navigator.userAgentData.platform,
    platformVersion: he.platformVersion,
    gpu: { vendor: gl.getParameter(0x9245), renderer: gl.getParameter(0x9246),
           parameters },
    screen: { width: screen.width, height: screen.height,
              availWidth: screen.availWidth, availHeight: screen.availHeight },
    locale: navigator.language,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    dpr: window.devicePixelRatio,
    sampleRate: new AudioContext().sampleRate,
  };
}""" % json.dumps(PNAMES)

flags = lib_shell.CHROME_FLAGS + GL_FLAGS
# userAgentData exists only in a secure context; a loopback page is one,
# about:blank is not.
base_url, _, stop = echo_server.start(lib_shell.ACCEPT_CH)
try:
    values, err = lib_shell.session(None, [PROBE], navigate_to=base_url,
                                    shell=lib_shell.CHROME, extra_flags=flags)
finally:
    stop()
observed = values[0] if values else None
if err is not None or "err" in observed or observed["milestone"] is None:
    print(f"capture failed: {err or observed}", file=sys.stderr)
    sys.exit(1)

if not observed["platformVersion"]:
    # Linux reports "" here; an empty claim is no claim, so leave the key
    # out rather than have the loader emit an empty ua:platformVersion.
    del observed["platformVersion"]
observed["provenance"] = {
    "binary": lib_shell.CHROME,
    "flags": flags,
    "captured": datetime.date.today().isoformat(),
    "kind": "smoke preset: the build box's own headless SwiftShader identity, "
            "for exercising the loader; not a distributable device identity",
    "fonts": "omitted, no enumeration without a permission prompt",
    "dpr_and_sampleRate": "recorded only; the loader emits neither",
}
print(json.dumps(observed, indent=2, sort_keys=True))
