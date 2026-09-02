"""SP7 codec build-flags verify: proprietary_codecs=true + ffmpeg_branding=Chrome.

C1 canPlayType H.264/AAC -> "probably" (was ""); C2 MSE.isTypeSupported -> true;
C3 functional H.264 decode of bear.mp4 (best-effort — headless may lack a decode
context); C4 no regression (VP9/Opus/AV1/MP3 still "probably").
"""
import http.server, json, os, sys, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell

HERE = os.path.dirname(os.path.abspath(__file__))
BEAR = os.path.join(HERE, "bear.mp4")


def start_media_server():
    with open(BEAR, "rb") as f:
        mp4 = f.read()

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/bear.mp4":
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(len(mp4)))
                self.end_headers()
                self.wfile.write(mp4)
            else:
                body = b"<!doctype html><title>codec</title>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}/", srv.shutdown


MATRIX = r"""(() => {
  const v = document.createElement('video');
  const a = document.createElement('audio');
  const cp = (t) => v.canPlayType(t) || a.canPlayType(t);
  const ms = (t) => window.MediaSource ? MediaSource.isTypeSupported(t) : null;
  const H264 = 'video/mp4; codecs="avc1.42E01E"';
  const AAC  = 'audio/mp4; codecs="mp4a.40.2"';
  return {
    h264_cp: cp(H264), h264_ms: ms(H264),
    aac_cp: cp(AAC),  aac_ms: ms(AAC),
    vp9_cp: cp('video/webm; codecs="vp9"'),
    opus_cp: cp('audio/webm; codecs="opus"'),
    av1_cp: cp('video/mp4; codecs="av01.0.04M.08"'),
    mp3_cp: cp('audio/mpeg'),
  };
})()"""

DECODE = r"""(async () => {
  const v = document.createElement('video');
  v.muted = true; v.src = '/bear.mp4';
  document.body.appendChild(v);
  return await new Promise((res) => {
    v.onloadeddata = () => res({ok:true, w:v.videoWidth, h:v.videoHeight, rs:v.readyState});
    v.onerror = () => res({ok:false, err: v.error ? v.error.code : 'unknown'});
    setTimeout(() => res({ok:false, timeout:true, rs:v.readyState, w:v.videoWidth}), 5000);
  });
})()"""


def main():
    url, stop = start_media_server()
    try:
        vals, err = lib_shell.session(None, [MATRIX, DECODE], navigate_to=url)
        if err:
            print("ERROR", err); sys.exit(1)
        m, d = vals[0], vals[1]
        print("matrix:", json.dumps(m))
        print("decode:", json.dumps(d))
        r = {}
        r["C1"] = m["h264_cp"] == "probably" and m["aac_cp"] == "probably"
        r["C2"] = m["h264_ms"] is True and m["aac_ms"] is True
        r["C3"] = bool(d.get("ok")) and d.get("w", 0) > 0   # best-effort (headless may fail)
        r["C4"] = (m["vp9_cp"] == "probably" and m["opus_cp"] == "probably"
                   and m["av1_cp"] == "probably" and m["mp3_cp"] == "probably")
        for k in ("C1", "C2", "C3", "C4"):
            print(f"{k}: {'PASS' if r[k] else 'FAIL'}")
        core = r["C1"] and r["C2"] and r["C4"]  # the build-has-codecs proof
        print(f"CORE(C1,C2,C4): {'PASS' if core else 'FAIL'}  C3(decode,best-effort): {'PASS' if r['C3'] else 'FAIL/headless'}")
        sys.exit(0 if core else 1)
    finally:
        stop()


if __name__ == "__main__":
    main()
