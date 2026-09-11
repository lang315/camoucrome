#!/usr/bin/env python3
"""The Windows host oracle: one page reads every cheap page-visible surface a
fingerprinter enumerates (window keys, Navigator prototype, screen, media
queries, Intl, audio, voices, WebGPU, codecs, permissions, keyboard, storage,
client hints...) on stock Chrome 153 on the box's Windows 10 host (headless
--dump-dom) -> baselines/chrome-8010-stock-oracle-windows.json.
verify_host_oracle.py renders the same page in the fork under a generated
Windows identity and diffs, so every remaining Windows-claim tell is a line."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "baselines" / "chrome-8010-stock-oracle-windows.json"

MEDIA = ["(pointer: fine)", "(pointer: coarse)", "(pointer: none)", "(hover: hover)", "(any-pointer: fine)", "(any-hover: hover)",
         "(prefers-color-scheme: dark)", "(prefers-reduced-motion: reduce)", "(prefers-contrast: more)", "(prefers-contrast: no-preference)",
         "(forced-colors: active)", "(color-gamut: srgb)", "(color-gamut: p3)", "(color-gamut: rec2020)", "(dynamic-range: high)",
         "(video-dynamic-range: high)", "(prefers-reduced-transparency: reduce)", "(inverted-colors: inverted)", "(scripting: enabled)",
         "(display-mode: browser)", "(update: fast)", "(overflow-block: scroll)", "(color: 8)", "(color: 10)", "(monochrome)",
         "(-webkit-min-device-pixel-ratio: 1)", "(resolution: 96dpi)", "(orientation: landscape)", "(prefers-reduced-data: reduce)"]
CODECS = ['video/mp4; codecs="avc1.42E01E"', 'video/mp4; codecs="hev1.1.6.L93.B0"', 'video/mp4; codecs="av01.0.05M.08"', 'video/webm; codecs="vp9"',
          'video/webm; codecs="vp8"', 'audio/mp4; codecs="mp4a.40.2"', 'audio/mpeg', 'audio/ogg; codecs="opus"', 'audio/flac', 'video/mp4; codecs="ac-3"',
          'video/mp4; codecs="ec-3"', 'video/x-matroska; codecs="avc1"', 'application/vnd.apple.mpegurl', 'audio/wav']
PERMS = ["geolocation", "notifications", "camera", "microphone", "clipboard-read", "clipboard-write", "midi", "persistent-storage", "screen-wake-lock",
         "accelerometer", "gyroscope", "magnetometer", "background-sync", "payment-handler", "storage-access", "window-management", "local-fonts"]


def page():
    return """<!doctype html><title>oracle</title><pre id="o"></pre><pre id="p" hidden></pre><canvas id="c" width="220" height="40"></canvas><script>
const MEDIA=%s,CODECS=%s,PERMS=%s;
const out={};
const emit=(final)=>{document.getElementById(final?'o':'p').textContent=JSON.stringify(out).replace(/[\\u0080-\\uffff]/g,ch=>'\\\\u'+ch.charCodeAt(0).toString(16).padStart(4,'0'))};
const names=o=>{try{return Object.getOwnPropertyNames(o)}catch(e){return [String(e)]}};
const fnv=s=>{let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)>>>0}return h.toString(16)};
const pick=(o,ks)=>Object.fromEntries(ks.map(k=>{try{const v=o[k];return [k,typeof v==='function'?'function':(v&&typeof v==='object'&&!Array.isArray(v)?'object':v)]}catch(e){return [k,'throws']}}));
const step=async(name,fn,ms)=>{try{out[name]=await Promise.race([Promise.resolve().then(fn),new Promise(r=>setTimeout(()=>r('timeout'),ms||8000))])}catch(e){out[name]='throws:'+(e&&e.name||e)+':'+(e&&e.message||'')}emit()};
window.onerror=(m,src,l,c)=>{out.pageError=m+' @'+l+':'+c;emit(true)};
(async()=>{
await step('ua',()=>navigator.userAgent);
await step('windowKeys',()=>Object.keys(window));
await step('navProto',()=>names(Navigator.prototype));
await step('windowNames',()=>names(window).filter(n=>!/^(on|webkit)/.test(n)));
await step('nav',()=>pick(navigator,['platform','vendor','vendorSub','product','productSub','appName','appVersion','appCodeName','language','languages','doNotTrack','maxTouchPoints','pdfViewerEnabled','hardwareConcurrency','deviceMemory','webdriver','cookieEnabled','onLine','share','canShare','setAppBadge','clearAppBadge','keyboard','virtualKeyboard','windowControlsOverlay','ink','connection','bluetooth','hid','serial','usb','xr','gpu','scheduling','login','devicePosture','contacts','getInstalledRelatedApps','requestMIDIAccess','wakeLock','mediaSession','presentation','credentials','locks','userActivation','managed','protectedAudience','getBattery','vibrate','sendBeacon','clipboard','mediaCapabilities','permissions','storage','serviceWorker','geolocation','mediaDevices']));
await step('navConnection',()=>navigator.connection?pick(navigator.connection,['effectiveType','rtt','downlink','saveData','type']):null);
await step('uad',()=>{const ud=navigator.userAgentData;return ud?{brands:ud.brands,mobile:ud.mobile,platform:ud.platform}:null});
await step('uadHigh',()=>navigator.userAgentData.getHighEntropyValues(['architecture','bitness','model','platformVersion','uaFullVersion','fullVersionList','wow64','formFactors']));
await step('screen',()=>pick(screen,['width','height','availWidth','availHeight','availLeft','availTop','colorDepth','pixelDepth','isExtended']));
await step('screenOrientation',()=>({type:screen.orientation.type,angle:screen.orientation.angle}));
await step('win',()=>({dpr:devicePixelRatio,outerMinusInnerW:outerWidth-innerWidth,outerMinusInnerH:outerHeight-innerHeight,screenX,screenY,external:typeof external,styleMedia:typeof styleMedia,chrome:typeof chrome,showOpenFilePicker:typeof showOpenFilePicker,launchQueue:typeof launchQueue,queryLocalFonts:typeof queryLocalFonts,getScreenDetails:typeof getScreenDetails,showSaveFilePicker:typeof showSaveFilePicker,openDatabase:typeof openDatabase,PaymentRequest:typeof PaymentRequest,speechSynthesis:typeof speechSynthesis,DeviceMotionEvent:typeof DeviceMotionEvent,ondeviceorientation:'ondeviceorientation' in window,ontouchstart:'ontouchstart' in window,SharedWorker:typeof SharedWorker,Notification:typeof Notification}));
await step('media',()=>Object.fromEntries(MEDIA.map(q=>[q,matchMedia(q).matches])));
await step('intl',()=>({dtf:Intl.DateTimeFormat().resolvedOptions(),nf:Intl.NumberFormat().resolvedOptions(),date0:new Date(0).toString(),tzCount:Intl.supportedValuesOf('timeZone').length,collator:Intl.Collator().resolvedOptions().locale,segmenter:typeof Intl.Segmenter,durationFormat:typeof Intl.DurationFormat}));
await step('audio',async()=>{const ac=new AudioContext();const r={sampleRate:ac.sampleRate,baseLatency:ac.baseLatency,outputLatency:ac.outputLatency,maxChannelCount:ac.destination.maxChannelCount,channelCount:ac.destination.channelCount,state:ac.state};await ac.close();return r});
await step('audioFp',async()=>{const oc=new OfflineAudioContext(1,5000,44100);const osc=oc.createOscillator();const comp=oc.createDynamicsCompressor();osc.connect(comp);comp.connect(oc.destination);osc.start();const buf=await oc.startRendering();const d=buf.getChannelData(0);let s=0;for(let i=4000;i<5000;i++)s+=Math.abs(d[i]);return s.toFixed(6)},5000);
await step('voices',()=>new Promise(res=>{const get=()=>speechSynthesis.getVoices().map(v=>[v.name,v.lang,v.localService,v.default]);let v=get();if(v.length)return res(v);speechSynthesis.onvoiceschanged=()=>res(get());setTimeout(()=>res(get()),1500)}));
await step('gpu',async()=>{const a=await navigator.gpu.requestAdapter();return a?{info:{vendor:a.info.vendor,architecture:a.info.architecture,device:a.info.device,description:a.info.description},features:[...a.features].sort(),limits:{maxTextureDimension2D:a.limits.maxTextureDimension2D,maxBufferSize:a.limits.maxBufferSize,maxStorageBufferBindingSize:a.limits.maxStorageBufferBindingSize,maxComputeWorkgroupSizeX:a.limits.maxComputeWorkgroupSizeX,maxBindGroups:a.limits.maxBindGroups},isFallback:a.isFallbackAdapter}:null},5000);
await step('codecs',()=>{const v=document.createElement('video');return Object.fromEntries(CODECS.map(c=>[c,[v.canPlayType(c),typeof MediaSource!=='undefined'&&MediaSource.isTypeSupported(c)]]))});
await step('mediaCap',()=>navigator.mediaCapabilities.decodingInfo({type:'file',video:{contentType:'video/mp4; codecs="avc1.42E01E"',width:1920,height:1080,bitrate:5000000,framerate:30}}).then(r=>[r.supported,r.smooth,r.powerEfficient]));
await step('perms',async()=>{const r={};for(const p of PERMS){try{r[p]=(await navigator.permissions.query({name:p})).state}catch(e){r[p]='throws:'+e.name}}return r});
await step('keyboard',async()=>{const m=await navigator.keyboard.getLayoutMap();return {size:m.size,KeyA:m.get('KeyA'),KeyQ:m.get('KeyQ'),Backquote:m.get('Backquote'),Digit1:m.get('Digit1')}});
await step('storage',async()=>{const e=await navigator.storage.estimate();return {quotaGiB:Math.round(e.quota/2**30),usage:e.usage,persisted:await navigator.storage.persisted()}});
await step('perfMem',()=>performance.memory?{jsHeapSizeLimit:performance.memory.jsHeapSizeLimit}:null);
await step('mediaDevices',()=>navigator.mediaDevices.enumerateDevices().then(ds=>ds.map(d=>[d.kind,d.label,d.deviceId.length,d.groupId.length])));
await step('canvas',()=>{const c=document.getElementById('c'),x=c.getContext('2d');x.font='16px Arial';x.fillText('Cwm fjordbank glyphs vext quiz 1234',4,26);x.font='16px "Segoe UI"';x.fillText('Cwm fjordbank glyphs vext quiz',4,38);const t=fnv(c.toDataURL());x.clearRect(0,0,220,40);x.fillStyle='#f60';x.beginPath();x.arc(50,20,15,0,7);x.fill();x.fillStyle='rgba(0,80,255,.5)';x.fillRect(40,10,60,20);return {text:t,shape:fnv(c.toDataURL())}});
await step('fonts',()=>({segoe:document.fonts.check('12px "Segoe UI"'),calibri:document.fonts.check('12px Calibri'),dejavu:document.fonts.check('12px "DejaVu Sans"')}));
await step('err',()=>({stack:(new Error('x')).stack.split('\\n')[1].trim().replace(/:\\d+:\\d+\\)?$/,''),toStringLen:Function.prototype.toString.call(navigator.getBattery).length}));
await step('protoCounts',()=>({Window:names(window).length,Document:names(Document.prototype).length,HTMLElement:names(HTMLElement.prototype).length,CSSStyleDeclaration:names(CSSStyleDeclaration.prototype).length,Element:names(Element.prototype).length,cssProps:names(document.body.style).length}));
out.done=true;emit(true);
})();
</script>""" % (json.dumps(MEDIA), json.dumps(CODECS), json.dumps(PERMS))


def main():
    import winhost
    headless = winhost.dump_dom(page(), args=("--virtual-time-budget=60000", "--use-gl=angle", "--use-angle=d3d11"), timeout_s=180)
    raw = winhost.cdp_eval(page(), "document.getElementById('o').textContent", args=("--use-gl=angle", "--use-angle=d3d11"), headed=True, wait_ms=25000)
    headed = json.loads(raw) if isinstance(raw, str) else raw
    OUT.write_text(json.dumps({"chrome": "153.0.8010.36", "where": "stock Google Chrome on the build box's Windows 10 host (build 19045), temp profile; headed through the host CDP client, headless --dump-dom",
                               "headed": headed, "headless": headless}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for label, r in (("headed", headed), ("headless", headless)):
        print(label, "done", r.get("done"), "pageError", r.get("pageError"), {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in r.items() if k in ("perms", "storage", "keyboard", "gpu", "voices", "mediaDevices", "audioFp", "canvas")})


if __name__ == "__main__":
    main()
