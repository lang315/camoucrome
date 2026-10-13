"""S5 host probe: speechSynthesis on stock Chrome 154 (and the fork) on the Windows host.
Run only through W8 (a session-1 interactive scheduled task). Per launch: chrome://gpu crash
count (non-zero = UNMEASURED), the voices timeline, then speak() cells on a Google and a local
voice after one real CDP click (user activation). Prints kinds, counts, error names and ms only.

Usage: measure_remote_voices.py OUT.jsonl N ARMS   (ARMS: stock,fork,stock-fr)"""
import json, os, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
TREE = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TREE, "client", "python"))
sys.path.insert(0, HERE)
import camoucrome  # noqa: E402
assert os.path.abspath(camoucrome.__file__).startswith(TREE), f"camoucrome from {camoucrome.__file__}, not {TREE}"
import measure_step2 as m2  # noqa: E402
from camoucrome.launcher import remove_dir  # noqa: E402
from patchright.sync_api import sync_playwright  # noqa: E402

PAGE = b"""<!doctype html><title>s5</title><pre id=o></pre><pre id=p></pre><script>
const T0 = performance.now(), t = () => Math.round(performance.now() - T0);
const out = {arrivals: []};
const snap = () => { const v = speechSynthesis.getVoices(); out.arrivals.push([t(), v.length, v.filter(x => !x.localService).length]); };
snap(); speechSynthesis.onvoiceschanged = snap;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const TXT = n => 'The quick brown fox jumps over the lazy dog. '.repeat(20).slice(0, n);
function say(voice, n, rate, act) {
  return new Promise(res => {
    const ev = [], u = new SpeechSynthesisUtterance(TXT(n)), s = performance.now();
    const at = () => Math.round(performance.now() - s);
    u.voice = voice; u.lang = voice.lang; u.volume = 0; u.rate = rate;
    for (const k of ['start', 'end', 'error', 'boundary', 'pause', 'resume'])
      u.addEventListener(k, e => ev.push([k, at(), e.error || '']));
    let done = false; const fin = x => { if (!done) { done = true; setTimeout(() => res({v: voice.localService ? 'local' : 'remote', n, rate, act, ev, ...x}), 80); } };
    u.addEventListener('end', () => fin({})); u.addEventListener('error', () => fin({}));
    // cancel/pause 1 s after 'start', not after speak(): a remote voice starts late
    u.addEventListener('start', () => {
      if (act === 'cancel') setTimeout(() => speechSynthesis.cancel(), 1000);
      if (act === 'pause') setTimeout(() => { speechSynthesis.pause(); setTimeout(() => speechSynthesis.resume(), 1000); }, 1000);
    }, {once: true});
    speechSynthesis.speak(u);
    setTimeout(() => { ev.push(['timeout', at(), '']); speechSynthesis.cancel(); fin({}); }, 30000);
  });
}
async function cells() {
  await sleep(3000);
  const v = speechSynthesis.getVoices();
  out.list = v.map(x => [x.name, x.lang, x.localService, x.default, x.voiceURI === x.name]);
  const g = v.find(x => x.name === 'Google US English'), l = v.find(x => x.localService && x.lang === 'en-US');
  out.speak = [];
  if (location.search === '?list') { document.getElementById('o').textContent = JSON.stringify(out); return; }
  for (const voice of [g, l]) {
    if (!voice) continue;
    for (const [n, rate, act] of [[43, 1, ''], [200, 1, ''], [540, 1, ''], [43, 2, ''], [200, 1, 'cancel'], [200, 1, 'pause']])
      { out.speak.push(await say(voice, n, rate, act)); document.getElementById('p').textContent = JSON.stringify(out); }
  }
  document.getElementById('o').textContent = JSON.stringify(out);
}
// no activation yet: speak must say not-allowed
(() => { const v = speechSynthesis.getVoices(); const u = new SpeechSynthesisUtterance('x'); u.volume = 0;
  u.onerror = e => out.noact = e.error; u.onstart = () => out.noact = 'started'; speechSynthesis.speak(u); })();
document.addEventListener('click', () => { cells(); }, {once: true});
</script>"""


def gpu_crash_count(ctx):
    """chrome://gpu "GPU process crash count", as S4's gpu_page read it; None if unread."""
    p = ctx.new_page()
    try:
        p.goto("chrome://gpu", wait_until="load", timeout=15000)
        for _ in range(20):
            txt = p.evaluate("(()=>{const o=[];const w=r=>{for(const e of r.querySelectorAll('*')){if(e.tagName==='LI'||e.tagName==='TR')o.push(e.textContent.replace(/\\s+/g,' ').trim());if(e.shadowRoot)w(e.shadowRoot)}};w(document);return o.join('\\n')})()")
            line = next((l for l in txt.splitlines() if l.startswith("GPU process crash count")), None)
            if line:
                return line.rpartition(":")[2].strip()
            time.sleep(0.25)
        return None
    finally:
        p.close()


def one(pw, arm, mode):
    udd = tempfile.mkdtemp(prefix="s5-", dir=r"D:\camou-win\cn\s5\p")
    rec = {"arm": arm.name, "mode": mode}
    try:
        with m2.serve(PAGE) as url, m2.opened(pw, arm, mode, user_data_dir=udd) as ctx:
            page = m2.first_page(ctx)
            page.goto(url + ("?list" if arm.name == "stock-fr" else ""), wait_until="load")
            page.wait_for_timeout(500)
            page.mouse.click(5, 5)  # real input over CDP: user activation for speak()
            try:
                page.wait_for_function("document.getElementById('o').textContent !== ''", timeout=600000)
                rec.update(json.loads(page.locator("#o").text_content()))
            except Exception as e:  # noqa: BLE001 - keep the cells that did finish (#p, written per cell)
                rec["error"] = f"{type(e).__name__}: {str(e)[:120]}"
                rec.update(json.loads(page.locator("#p").text_content() or "{}"))
            rec["crash"] = gpu_crash_count(ctx)
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        remove_dir(udd)
    rec["unmeasured"] = rec.get("crash") != "0"
    return rec


def main():
    out, n, arms = sys.argv[1], int(sys.argv[2]), sys.argv[3].split(",")
    os.makedirs(r"D:\camou-win\cn\s5\p", exist_ok=True)
    stock = os.path.join(m2.STOCK_APP, "chrome.exe")
    # The run is unattended on the owner's RDP desktop, where the window can be occluded or the
    # client minimised; Chrome then throttles the page's timers to about one wake a minute and the
    # cells never finish (smoke2, 2026-10-14). Every arm gets the same three scheduling flags.
    # They change when timers fire, not what the speech engine reports.
    awake = ["--disable-background-timer-throttling", "--disable-renderer-backgrounding",
             "--disable-backgrounding-occluded-windows"]
    table = {"stock": m2.Arm("stock", stock, None, awake),
             "stock-fr": m2.Arm("stock-fr", stock, None, ["--lang=fr", *awake]),
             "fork": m2.Arm("fork", os.environ.get("CAMOU_FORK_EXE", ""), m2.identity(1), awake)}
    with sync_playwright() as pw, open(out, "a", encoding="utf-8") as f:
        for i in range(n):
            for a in arms:
                rec = one(pw, table[a], "headed")
                rec["i"] = i
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                print(i, a, rec.get("crash"), rec.get("noact"), len(rec.get("list", [])), rec.get("error", ""), flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
