"""Verifies voices-ii pause/resume on the fake-completion path.

Real SpeechSynthesis pause() fires a 'pause' event, sets speechSynthesis.paused,
and stops boundary/end events until resume(); resume() fires 'resume' and
continues. On content_shell the fake path is PostDelayedTask-driven and pause()
routes through a null mojo backend, so before this fix pause() is inert: no
event, paused stays false, boundaries/end keep firing.

Behavioral RED (against the pre-fix binary): VP-STOP/VP-PAUSE-EVT/VP-PAUSED/
VP-END-DEFER/VP-RESUME-EVT all FAIL. After: all PASS. One session drives the
whole speak/pause/resume timeline.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell

ONE_VOICE = {"voices:list": [{"name": "Camou EN", "lang": "en-US",
                              "voiceURI": "urn:camou:en",
                              "localService": True, "default": True}]}

# ~40 chars -> ~3.2 s fake duration, so a 3.5 s paused window extends PAST the
# natural end -- that is what makes VP-END-DEFER discriminate (a pre-fix binary
# fires 'end' at ~3.2 s while "paused").
PROBE = r"""(async () => {
  const voices = speechSynthesis.getVoices();
  if (!voices.length) return {error:'no voice'};
  const u = new SpeechSynthesisUtterance('the quick brown fox jumps now here today');
  u.voice = voices[0]; u.rate = 1.0;
  let boundaries = 0, pauseEvt = 0, resumeEvt = 0, ended = false;
  u.onboundary = () => { boundaries++; };
  u.onpause = () => { pauseEvt++; };
  u.onresume = () => { resumeEvt++; };
  u.onend = () => { ended = true; };
  speechSynthesis.speak(u);
  await new Promise(r => setTimeout(r, 300));
  speechSynthesis.pause();
  await new Promise(r => setTimeout(r, 80));    // let the pause event task run
  const atPause = boundaries;
  const pausedFlag = speechSynthesis.paused;
  await new Promise(r => setTimeout(r, 4200));   // observe while paused, past end
  const afterPause = boundaries - atPause;
  const endedWhilePaused = ended;
  const pauseEvtAtResume = pauseEvt;
  speechSynthesis.resume();
  await new Promise(r => setTimeout(r, 80));
  const pausedAfterResume = speechSynthesis.paused;
  await new Promise(r => setTimeout(r, 4500));   // let deferred events complete
  return { afterPause, endedWhilePaused, pauseEvt: pauseEvtAtResume, resumeEvt,
           pausedFlag, pausedAfterResume, endedFinal: ended,
           boundariesFinal: boundaries };
})()"""

v, e = lib_shell.session(json.dumps(ONE_VOICE), [PROBE])
results = {}
notes = []
if e:
    for k in ("VP-STOP", "VP-PAUSE-EVT", "VP-PAUSED", "VP-END-DEFER",
              "VP-RESUME-EVT"):
        results[k] = False
    notes.append(f"session error: {type(e).__name__}: {e}")
elif not isinstance(v[0], dict) or "error" in v[0]:
    for k in ("VP-STOP", "VP-PAUSE-EVT", "VP-PAUSED", "VP-END-DEFER",
              "VP-RESUME-EVT"):
        results[k] = False
    notes.append(f"probe error: {v[0]}")
else:
    r = v[0]
    results["VP-STOP no boundary fires while paused"] = r["afterPause"] == 0
    results["VP-PAUSE-EVT pause event fired once"] = r["pauseEvt"] == 1
    results["VP-PAUSED paused flag true while paused"] = r["pausedFlag"] is True
    results["VP-END-DEFER end deferred past pause"] = r["endedWhilePaused"] is False
    # 8 words -> 8 boundary events. All must be delivered (the ones pending at
    # pause fire AFTER resume, before 'end'); a drop here means 'end' raced ahead
    # of the deferred boundaries and retired them.
    results["VP-RESUME-EVT resume fires, all 8 boundaries delivered, completes"] = (
        r["resumeEvt"] == 1 and r["endedFinal"] is True
        and r["pausedAfterResume"] is False and r["boundariesFinal"] == 8)
    notes.append(f"detail: {r}")

# --- VP-RESPEAK: pause -> cancel -> respeak must not wedge the new speak ---
# pause() queues a DidPauseSpeaking task. cancel() clears is_paused_ and the
# queue; the fresh speak bumps the generation. The stale task MUST be retired
# (generation + current-utterance guard), or it re-sets is_paused_ on a speak it
# never paused -- whose deferred boundary/finish tasks then poll forever (the new
# speak hangs, never fires 'end') -- and/or dispatches a spurious 'pause' on it.
RESPEAK = r"""(async () => {
  const voices = speechSynthesis.getVoices();
  if (!voices.length) return {error:'no voice'};
  const u1 = new SpeechSynthesisUtterance('the quick brown fox jumps now');
  u1.voice = voices[0]; u1.rate = 1.0;
  const u2 = new SpeechSynthesisUtterance('the lazy dog sleeps here today again');
  u2.voice = voices[0]; u2.rate = 1.0;
  let u2Pause = 0, u2End = false, u2Boundaries = 0;
  u2.onpause = () => { u2Pause++; };
  u2.onend = () => { u2End = true; };
  u2.onboundary = () => { u2Boundaries++; };
  speechSynthesis.speak(u1);
  await new Promise(r => setTimeout(r, 100));
  speechSynthesis.pause();
  speechSynthesis.cancel();
  speechSynthesis.speak(u2);
  await new Promise(r => setTimeout(r, 5000));   // u2 (~3 s) must complete
  return { u2Pause, u2End, u2Boundaries, paused: speechSynthesis.paused };
})()"""

v2, e2 = lib_shell.session(json.dumps(ONE_VOICE), [RESPEAK])
K = "VP-RESPEAK pause->cancel->respeak does not wedge the new speak"
if e2 or not isinstance(v2[0], dict) or "error" in v2[0]:
    results[K] = False
    notes.append(f"respeak session/probe error: {e2 or v2[0]}")
else:
    r2 = v2[0]
    # 7 words in u2 -> 7 boundaries; no pause event on u2; it completes; not paused.
    results[K] = (r2["u2Pause"] == 0 and r2["u2End"] is True
                  and r2["paused"] is False and r2["u2Boundaries"] == 7)
    notes.append(f"respeak detail: {r2}")

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)
