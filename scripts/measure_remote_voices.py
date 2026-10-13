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
function say(voice, n, rate, act, cap = 45000) {
  return new Promise(res => {
    const ev = [], u = new SpeechSynthesisUtterance(TXT(n)), s = performance.now();
    const at = () => Math.round(performance.now() - s);
    u.voice = voice; u.lang = voice.lang; u.volume = 0; u.rate = rate;
    for (const k of ['start', 'end', 'error', 'boundary', 'pause', 'resume'])
      u.addEventListener(k, e => ev.push([k, at(), e.error || '']));
    // every timer this cell sets is cleared when it ends, so none can cancel()/pause() a later cell
    const timers = [], later = (f, ms) => timers.push(setTimeout(f, ms));
    let done = false; const fin = x => { if (!done) { done = true; timers.forEach(clearTimeout); setTimeout(() => res({v: voice.localService ? 'local' : 'remote', n, rate, act, ev: ev.slice(), ...x}), 80); } };
    u.addEventListener('end', () => fin({})); u.addEventListener('error', () => fin({}));
    // cancel/pause 1 s after 'start', not after speak(): a remote voice starts late
    u.addEventListener('start', () => {
      if (act === 'cancel') later(() => speechSynthesis.cancel(), 1000);
      if (act === 'pause') later(() => { speechSynthesis.pause(); later(() => speechSynthesis.resume(), 1000); }, 1000);
    }, {once: true});
    speechSynthesis.speak(u);
    later(() => { ev.push(['timeout', at(), '']); speechSynthesis.cancel(); fin({}); }, cap);
  });
}
const mark = s => { (out.marks = out.marks || []).push([t(), s]); document.getElementById('p').textContent = JSON.stringify(out); };
async function cells() {
  mark('clicked ' + document.visibilityState + ' focus=' + document.hasFocus());
  await sleep(3000);
  mark('slept');
  const v = speechSynthesis.getVoices();
  out.list = v.map(x => [x.name, x.lang, x.localService, x.default, x.voiceURI === x.name]);
  const g = v.find(x => x.name === 'Google US English'), l = v.find(x => x.localService && x.lang === 'en-US');
  out.speak = [];
  if (location.search === '?list') { document.getElementById('o').textContent = JSON.stringify(out); return; }
  if (location.search === '?paused') {  // final review: speechSynthesis.paused around pause()/resume(); repeated starts
    if (g) {
      out.paused = await new Promise(res => {
        const u = new SpeechSynthesisUtterance(TXT(200)), rd = {}; u.voice = g; u.volume = 0;
        const ev = []; for (const k of ['start','end','error','pause','resume']) u.addEventListener(k, () => ev.push(k));
        u.addEventListener('start', () => setTimeout(() => {
          rd.before = speechSynthesis.paused; speechSynthesis.pause(); rd.sync = speechSynthesis.paused;
          setTimeout(() => { rd.after200 = speechSynthesis.paused; rd.speaking = speechSynthesis.speaking;
            speechSynthesis.resume(); rd.resumeSync = speechSynthesis.paused;
            setTimeout(() => { rd.resume200 = speechSynthesis.paused; }, 200); }, 1000);
        }, 1000), {once: true});
        u.addEventListener('end', () => setTimeout(() => res({...rd, ev, end: speechSynthesis.paused}), 300));
        u.addEventListener('error', () => setTimeout(() => res({...rd, ev}), 300));
        speechSynthesis.speak(u); setTimeout(() => { speechSynthesis.cancel(); res({...rd, ev, timeout: true}); }, 40000);
      });
      out.reps = [];
      for (let i = 0; i < 4; i++) out.reps.push(await say(g, 43, 1, ''));
    }
    document.getElementById('o').textContent = JSON.stringify(out); return;
  }
  if (location.search === '?rates') {  // rate sweep: the remote voice only, 43 chars (Task 5)
    for (const rate of [0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 2.25, 2.5, 2.75, 3, 4])
      if (g) { out.speak.push(await say(g, 43, rate, '', 20000)); mark('cell ' + out.speak.length); }
    document.getElementById('o').textContent = JSON.stringify(out); return;
  }
  for (const voice of [g, l]) {
    if (!voice) continue;
    for (const [n, rate, act] of [[43, 1, ''], [200, 1, ''], [540, 1, ''], [43, 2, ''], [43, 0.5, ''], [43, 1.5, ''], [43, 3, ''], [200, 1, 'cancel'], [200, 1, 'pause']])
      { out.speak.push(await say(voice, n, rate, act)); mark('cell ' + out.speak.length); }
  }
  // stock's Google voices do not arrive on every launch (smoke6): read the list again at the end
  out.list_end = speechSynthesis.getVoices().map(x => [x.name, x.lang, x.localService, x.default, x.voiceURI === x.name]);
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
            page.goto(url + {"stock-fr": "?list", "stock-rates": "?rates", "stock-paused": "?paused"}.get(arm.name, ""), wait_until="load")
            page.wait_for_timeout(500)
            page.bring_to_front()
            # real input over CDP: user activation for speak(). The first launch in a fresh
            # interactive session can drop the first click (smoke1/3/4), so click until the page
            # marks it, and record how many tries that took.
            for tries in range(1, 6):
                page.mouse.click(5, 5)
                try:
                    page.wait_for_function("document.getElementById('p').textContent.includes('clicked')",
                                           timeout=3000, polling=200)
                    break
                except Exception:  # noqa: BLE001
                    continue
            rec["click_tries"] = tries
            try:
                page.wait_for_function("document.getElementById('o').textContent !== ''", timeout=600000, polling=1000)
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
    # cells never finish (smoke2, 2026-10-13). Every arm gets the same three scheduling flags.
    # They change when timers fire, not what the speech engine reports.
    awake = ["--disable-background-timer-throttling", "--disable-renderer-backgrounding",
             "--disable-backgrounding-occluded-windows"]
    table = {"stock": m2.Arm("stock", stock, None, awake),
             "stock-fr": m2.Arm("stock-fr", stock, None, ["--lang=fr", *awake]),
             "stock-rates": m2.Arm("stock-rates", stock, None, awake),
             "stock-paused": m2.Arm("stock-paused", stock, None, awake),
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
