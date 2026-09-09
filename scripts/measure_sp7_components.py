"""Measures the page-observable consequences of a component updater that never
delivers (SP7 phone-home lever): what a page can see on THIS chrome versus what
it sees on a Chrome whose updater has fetched its components. Prints values, no
verdict -- the measurement doc says which value is the tell.

Run under ~/camoucrome-verify/venv/bin/python3 on the build box, chrome target.
"""
import os
import echo_server
import lib_shell

# Hyphenation: hyphens:auto needs the hyphen-data component on desktop
# (chrome/browser/component_updater/hyphenation_component_installer.cc). In a
# 60px box a long English word overflows unless it can be hyphenated, so
# scrollWidth(auto) < scrollWidth(manual) means a dictionary is loaded.
HYPHENS = """(() => {
  const mk = (h) => { const d = document.createElement('div');
    d.lang = 'en-us'; d.textContent = 'extraordinarily supercalifragilistic';
    d.style.cssText = 'width:60px;font:16px serif;hyphens:' + h + ';overflow-wrap:normal';
    document.body.appendChild(d); return d.scrollWidth; };
  return {auto: mk('auto'), manual: mk('manual'), clientWidth: 60};
})()"""

# EME: Widevine is a component on unbranded builds when enable_widevine is on
# (ENABLE_WIDEVINE_CDM_COMPONENT); ClearKey is built in and is the control.
EME = """(async () => {
  const cfg = [{initDataTypes:['cenc'], videoCapabilities:[{contentType:'video/mp4; codecs="avc1.42E01E"'}]}];
  const probe = (k) => navigator.requestMediaKeySystemAccess(k, cfg).then(() => 'granted', e => e.name);
  return {widevine: await probe('com.widevine.alpha'), clearkey: await probe('org.w3.clearkey')};
})()"""

if __name__ == "__main__":
    if not os.path.exists(lib_shell.CHROME):
        raise SystemExit(f"no chrome at {lib_shell.CHROME}")
    # EME is [SecureContext]; the initial about:blank is not one in headless
    # chrome (requestMediaKeySystemAccess is undefined there), a loopback page is.
    base_url, _, stop = echo_server.start(lib_shell.ACCEPT_CH)
    try:
        values, err = lib_shell.session(None, ["isSecureContext", HYPHENS, EME],
                                        navigate_to=base_url, shell=lib_shell.CHROME,
                                        extra_flags=lib_shell.CHROME_FLAGS)
    finally:
        stop()
    if err:
        raise SystemExit(f"session error: {err!r}")
    print("isSecureContext", values[0])
    print("hyphens", values[1])
    print("eme", values[2])
