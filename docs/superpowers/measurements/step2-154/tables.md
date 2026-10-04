# Step 2 tables

Run `20261004-225915`; control 154.0.8037.93, fork 154.0.8037.93; flags {}.

## oracle / headed
24 differing rows: 21 expected, 3 volatile

| row | control | fork | label | reason |
|---|---|---|---|---|
| oracle.audioFp | "384.810240" | "384.806327" | expected | identity- or machine-bound; compared by type |
| oracle.err.stack | "at http://127.0.0.1:63489/" | "at http://127.0.0.1:63509/" | volatile | names the page's server, whose port changes per launch |
| oracle.intl.date0 | "Thu Jan 01 1970 08:00:00 GMT+0800 (Indochina Time)" | "Wed Dec 31 1969 18:00:00 GMT-0600 (Central Standard Time)" | expected | identity- or machine-bound; compared by type |
| oracle.intl.dtf.timeZone | "Asia/Saigon" | "America/Chicago" | expected | identity- or machine-bound; compared by type |
| oracle.media.(any-hover: hover) | false | true | expected | d-pointer-touch: a Windows claim reports a mouse; the host has none |
| oracle.media.(any-pointer: fine) | false | true | expected | d-pointer-touch: a Windows claim reports a mouse; the host has none |
| oracle.media.(hover: hover) | false | true | expected | d-pointer-touch: a Windows claim reports a mouse; the host has none |
| oracle.media.(pointer: fine) | false | true | expected | d-pointer-touch: a Windows claim reports a mouse; the host has none |
| oracle.media.(pointer: none) | true | false | expected | d-pointer-touch: a Windows claim reports a mouse; the host has none |
| oracle.mediaDevices | [["audiooutput", "", 0, 0]] | [["audioinput", "", 0, 0], ["videoinput", "", 0, 0], ["audiooutput", "", 0, 0]] | expected | identity- or machine-bound; compared by type |
| oracle.nav.deviceMemory | 32 | 8 | expected | identity- or machine-bound; compared by type |
| oracle.nav.hardwareConcurrency | 16 | 12 | expected | identity- or machine-bound; compared by type |
| oracle.nav.languages | ["en-US", "en"] | ["en-US"] | expected | identity- or machine-bound; compared by type |
| oracle.nav.webdriver | true | false | expected | SP2: the fork hides automation; stock under the same driver reports true |
| oracle.navConnection.downlink | 1.65 | 1.6 | volatile | a network estimate; 1.75 vs 1.6 between two stock launches |
| oracle.screen.availHeight | 768 | 1152 | expected | identity- or machine-bound; compared by type |
| oracle.screen.availWidth | 1024 | 1920 | expected | identity- or machine-bound; compared by type |
| oracle.screen.height | 768 | 1200 | expected | identity- or machine-bound; compared by type |
| oracle.screen.width | 1024 | 1920 | expected | identity- or machine-bound; compared by type |
| oracle.voices | [["Microsoft David - English (United States)", "en-US", true, true], ["Micros... | [["Microsoft David - English (United States)", "en-US", true, true], ["Micros... | volatile | speechSynthesis loads asynchronously; stock's list differed between launches of one profile |
| oracle.win.outerMinusInnerH | 95 | 459 | expected | identity- or machine-bound; compared by type |
| oracle.win.outerMinusInnerW | 16 | 892 | expected | identity- or machine-bound; compared by type |
| oracle.win.screenX | 10 | 0 | expected | identity- or machine-bound; compared by type |
| oracle.win.screenY | 10 | 0 | expected | identity- or machine-bound; compared by type |

## oracle / headless
23 differing rows: 21 expected, 2 volatile

| row | control | fork | label | reason |
|---|---|---|---|---|
| oracle.audioFp | "384.810240" | "384.806327" | expected | identity- or machine-bound; compared by type |
| oracle.err.stack | "at http://127.0.0.1:63514/" | "at http://127.0.0.1:63537/" | volatile | names the page's server, whose port changes per launch |
| oracle.intl.date0 | "Thu Jan 01 1970 08:00:00 GMT+0800 (Indochina Time)" | "Wed Dec 31 1969 18:00:00 GMT-0600 (Central Standard Time)" | expected | identity- or machine-bound; compared by type |
| oracle.intl.dtf.timeZone | "Asia/Saigon" | "America/Chicago" | expected | identity- or machine-bound; compared by type |
| oracle.media.(any-hover: hover) | false | true | expected | d-pointer-touch: a Windows claim reports a mouse; the host has none |
| oracle.media.(any-pointer: fine) | false | true | expected | d-pointer-touch: a Windows claim reports a mouse; the host has none |
| oracle.media.(hover: hover) | false | true | expected | d-pointer-touch: a Windows claim reports a mouse; the host has none |
| oracle.media.(pointer: fine) | false | true | expected | d-pointer-touch: a Windows claim reports a mouse; the host has none |
| oracle.media.(pointer: none) | true | false | expected | d-pointer-touch: a Windows claim reports a mouse; the host has none |
| oracle.mediaDevices | [["audiooutput", "", 0, 0]] | [["audioinput", "", 0, 0], ["videoinput", "", 0, 0], ["audiooutput", "", 0, 0]] | expected | identity- or machine-bound; compared by type |
| oracle.nav.appVersion | "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Hea... | "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chr... | expected | the identity's User-Agent; stock headless says HeadlessChrome |
| oracle.nav.deviceMemory | 32 | 8 | expected | identity- or machine-bound; compared by type |
| oracle.nav.hardwareConcurrency | 16 | 12 | expected | identity- or machine-bound; compared by type |
| oracle.nav.languages | ["en-US", "en"] | ["en-US"] | expected | identity- or machine-bound; compared by type |
| oracle.nav.webdriver | true | false | expected | SP2: the fork hides automation; stock under the same driver reports true |
| oracle.navConnection.downlink | 1.7 | 1.5 | volatile | a network estimate; 1.75 vs 1.6 between two stock launches |
| oracle.screen.availHeight | 600 | 1152 | expected | identity- or machine-bound; compared by type |
| oracle.screen.availWidth | 800 | 1920 | expected | identity- or machine-bound; compared by type |
| oracle.screen.height | 600 | 1200 | expected | identity- or machine-bound; compared by type |
| oracle.screen.width | 800 | 1920 | expected | identity- or machine-bound; compared by type |
| oracle.ua | "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge... | "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge... | expected | the identity's User-Agent; stock headless says HeadlessChrome |
| oracle.win.screenX | 10 | 0 | expected | identity- or machine-bound; compared by type |
| oracle.win.screenY | 10 | 0 | expected | identity- or machine-bound; compared by type |

## noise / headed
2 differing rows: 2 unexpected

| row | control | fork | label | reason |
|---|---|---|---|---|
| noise.canvas2d | 1 | 3 | unexpected |  |
| noise.webgl | 1 | 5 | unexpected |  |

## noise / headless
2 differing rows: 2 unexpected

| row | control | fork | label | reason |
|---|---|---|---|---|
| noise.canvas2d | 1 | 3 | unexpected |  |
| noise.webgl | 1 | 5 | unexpected |  |

## network / headed
1 differing rows: 1 volatile

| row | control | fork | label | reason |
|---|---|---|---|---|
| net.ja3 | "771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-4... | "771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-4... | volatile | Chrome permutes its TLS extension order per connection |

## network / headless
2 differing rows: 1 expected, 1 volatile

| row | control | fork | label | reason |
|---|---|---|---|---|
| net.ja3 | "771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-4... | "771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-4... | volatile | Chrome permutes its TLS extension order per connection |
| net.user_agent | "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge... | "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge... | expected | the identity's User-Agent |

## stability / headed
0 differing rows: 

## stability / headless
1 differing rows: 1 unexpected

| row | control | fork | label | reason |
|---|---|---|---|---|
| stab.changed | [] | ["codecs.video/mp4; codecs=\"hev1.1.6.L93.B0\""] | unexpected |  |

## linkability / headed
1 differing rows: 1 expected

| row | control | fork | label | reason |
|---|---|---|---|---|
| link.shared | ["audio.baseLatency", "audio.channelCount", "audio.maxChannelCount", "audio.o... | ["audio.baseLatency", "audio.channelCount", "audio.maxChannelCount", "audio.o... | expected | a record of what two profiles share, not a fork-vs-control finding |

Leaves the two fork profiles share (216 of 234):

`audio.baseLatency`, `audio.channelCount`, `audio.maxChannelCount`, `audio.outputLatency`, `audio.sampleRate`, `audio.state`, `canvas.text`, `codecs.application/vnd.apple.mpegurl`, `codecs.audio/flac`, `codecs.audio/mp4; codecs="mp4a.40.2"`, `codecs.audio/mpeg`, `codecs.audio/ogg; codecs="opus"`, `codecs.audio/wav`, `codecs.video/mp4; codecs="ac-3"`, `codecs.video/mp4; codecs="av01.0.05M.08"`, `codecs.video/mp4; codecs="avc1.42E01E"`, `codecs.video/mp4; codecs="ec-3"`, `codecs.video/mp4; codecs="hev1.1.6.L93.B0"`, `codecs.video/webm; codecs="vp8"`, `codecs.video/webm; codecs="vp9"`, `codecs.video/x-matroska; codecs="avc1"`, `done`, `err.toStringLen`, `fonts.calibri`, `fonts.dejavu`, `fonts.segoe`, `gpu.features`, `gpu.info.architecture`, `gpu.info.description`, `gpu.info.device`, `gpu.info.vendor`, `gpu.limits.maxBindGroups`, `gpu.limits.maxBufferSize`, `gpu.limits.maxComputeWorkgroupSizeX`, `gpu.limits.maxStorageBufferBindingSize`, `gpu.limits.maxTextureDimension2D`, `intl.collator`, `intl.dtf.calendar`, `intl.dtf.day`, `intl.dtf.locale`, `intl.dtf.month`, `intl.dtf.numberingSystem`, `intl.dtf.year`, `intl.durationFormat`, `intl.nf.locale`, `intl.nf.maximumFractionDigits`, `intl.nf.minimumFractionDigits`, `intl.nf.minimumIntegerDigits`, `intl.nf.notation`, `intl.nf.numberingSystem`, `intl.nf.roundingIncrement`, `intl.nf.roundingMode`, `intl.nf.roundingPriority`, `intl.nf.signDisplay`, `intl.nf.style`, `intl.nf.trailingZeroDisplay`, `intl.nf.useGrouping`, `intl.segmenter`, `intl.tzCount`, `keyboard.size`, `media.(-webkit-min-device-pixel-ratio: 1)`, `media.(any-hover: hover)`, `media.(any-pointer: fine)`, `media.(color-gamut: p3)`, `media.(color-gamut: rec2020)`, `media.(color-gamut: srgb)`, `media.(color: 10)`, `media.(color: 8)`, `media.(display-mode: browser)`, `media.(dynamic-range: high)`, `media.(forced-colors: active)`, `media.(hover: hover)`, `media.(inverted-colors: inverted)`, `media.(monochrome)`, `media.(orientation: landscape)`, `media.(overflow-block: scroll)`, `media.(pointer: coarse)`, `media.(pointer: fine)`, `media.(pointer: none)`, `media.(prefers-color-scheme: dark)`, `media.(prefers-contrast: more)`, `media.(prefers-contrast: no-preference)`, `media.(prefers-reduced-data: reduce)`, `media.(prefers-reduced-motion: reduce)`, `media.(prefers-reduced-transparency: reduce)`, `media.(scripting: enabled)`, `media.(update: fast)`, `media.(video-dynamic-range: high)`, `mediaCap`, `nav.appCodeName`, `nav.appName`, `nav.appVersion`, `nav.bluetooth`, `nav.canShare`, `nav.clearAppBadge`, `nav.clipboard`, `nav.connection`, `nav.cookieEnabled`, `nav.credentials`, `nav.deviceMemory`, `nav.devicePosture`, `nav.doNotTrack`, `nav.geolocation`, `nav.getBattery`, `nav.getInstalledRelatedApps`, `nav.gpu`, `nav.hid`, `nav.ink`, `nav.keyboard`, `nav.language`, `nav.languages`, `nav.locks`, `nav.login`, `nav.managed`, `nav.maxTouchPoints`, `nav.mediaCapabilities`, `nav.mediaDevices`, `nav.mediaSession`, `nav.onLine`, `nav.pdfViewerEnabled`, `nav.permissions`, `nav.platform`, `nav.presentation`, `nav.product`, `nav.productSub`, `nav.protectedAudience`, `nav.requestMIDIAccess`, `nav.scheduling`, `nav.sendBeacon`, `nav.serial`, `nav.serviceWorker`, `nav.setAppBadge`, `nav.share`, `nav.storage`, `nav.usb`, `nav.userActivation`, `nav.vendor`, `nav.vendorSub`, `nav.vibrate`, `nav.virtualKeyboard`, `nav.wakeLock`, `nav.webdriver`, `nav.windowControlsOverlay`, `nav.xr`, `navConnection.effectiveType`, `navConnection.saveData`, `navProto`, `perfMem.jsHeapSizeLimit`, `perms.accelerometer`, `perms.background-sync`, `perms.camera`, `perms.clipboard-read`, `perms.clipboard-write`, `perms.geolocation`, `perms.gyroscope`, `perms.local-fonts`, `perms.magnetometer`, `perms.microphone`, `perms.midi`, `perms.notifications`, `perms.payment-handler`, `perms.persistent-storage`, `perms.screen-wake-lock`, `perms.storage-access`, `perms.window-management`, `protoCounts.CSSStyleDeclaration`, `protoCounts.Document`, `protoCounts.Element`, `protoCounts.HTMLElement`, `protoCounts.Window`, `protoCounts.cssProps`, `screen.availLeft`, `screen.availTop`, `screen.colorDepth`, `screen.isExtended`, `screen.pixelDepth`, `screenOrientation.angle`, `screenOrientation.type`, `storage.persisted`, `storage.quotaGiB`, `storage.usage`, `ua`, `uad.brands`, `uad.mobile`, `uad.platform`, `uadHigh.architecture`, `uadHigh.bitness`, `uadHigh.brands`, `uadHigh.formFactors`, `uadHigh.fullVersionList`, `uadHigh.mobile`, `uadHigh.model`, `uadHigh.platform`, `uadHigh.platformVersion`, `uadHigh.uaFullVersion`, `uadHigh.wow64`, `win.DeviceMotionEvent`, `win.Notification`, `win.PaymentRequest`, `win.SharedWorker`, `win.chrome`, `win.external`, `win.getScreenDetails`, `win.launchQueue`, `win.ondeviceorientation`, `win.ontouchstart`, `win.openDatabase`, `win.queryLocalFonts`, `win.screenX`, `win.screenY`, `win.showOpenFilePicker`, `win.showSaveFilePicker`, `win.speechSynthesis`, `win.styleMedia`, `windowKeys`, `windowNames`

## linkability / headless
1 differing rows: 1 expected

| row | control | fork | label | reason |
|---|---|---|---|---|
| link.shared | ["audio.baseLatency", "audio.channelCount", "audio.maxChannelCount", "audio.o... | ["audio.baseLatency", "audio.channelCount", "audio.maxChannelCount", "audio.o... | expected | a record of what two profiles share, not a fork-vs-control finding |

Leaves the two fork profiles share (218 of 234):

`audio.baseLatency`, `audio.channelCount`, `audio.maxChannelCount`, `audio.outputLatency`, `audio.sampleRate`, `audio.state`, `canvas.text`, `codecs.application/vnd.apple.mpegurl`, `codecs.audio/flac`, `codecs.audio/mp4; codecs="mp4a.40.2"`, `codecs.audio/mpeg`, `codecs.audio/ogg; codecs="opus"`, `codecs.audio/wav`, `codecs.video/mp4; codecs="ac-3"`, `codecs.video/mp4; codecs="av01.0.05M.08"`, `codecs.video/mp4; codecs="avc1.42E01E"`, `codecs.video/mp4; codecs="ec-3"`, `codecs.video/mp4; codecs="hev1.1.6.L93.B0"`, `codecs.video/webm; codecs="vp8"`, `codecs.video/webm; codecs="vp9"`, `codecs.video/x-matroska; codecs="avc1"`, `done`, `err.toStringLen`, `fonts.calibri`, `fonts.dejavu`, `fonts.segoe`, `gpu.features`, `gpu.info.architecture`, `gpu.info.description`, `gpu.info.device`, `gpu.info.vendor`, `gpu.limits.maxBindGroups`, `gpu.limits.maxBufferSize`, `gpu.limits.maxComputeWorkgroupSizeX`, `gpu.limits.maxStorageBufferBindingSize`, `gpu.limits.maxTextureDimension2D`, `intl.collator`, `intl.dtf.calendar`, `intl.dtf.day`, `intl.dtf.locale`, `intl.dtf.month`, `intl.dtf.numberingSystem`, `intl.dtf.year`, `intl.durationFormat`, `intl.nf.locale`, `intl.nf.maximumFractionDigits`, `intl.nf.minimumFractionDigits`, `intl.nf.minimumIntegerDigits`, `intl.nf.notation`, `intl.nf.numberingSystem`, `intl.nf.roundingIncrement`, `intl.nf.roundingMode`, `intl.nf.roundingPriority`, `intl.nf.signDisplay`, `intl.nf.style`, `intl.nf.trailingZeroDisplay`, `intl.nf.useGrouping`, `intl.segmenter`, `intl.tzCount`, `keyboard.size`, `media.(-webkit-min-device-pixel-ratio: 1)`, `media.(any-hover: hover)`, `media.(any-pointer: fine)`, `media.(color-gamut: p3)`, `media.(color-gamut: rec2020)`, `media.(color-gamut: srgb)`, `media.(color: 10)`, `media.(color: 8)`, `media.(display-mode: browser)`, `media.(dynamic-range: high)`, `media.(forced-colors: active)`, `media.(hover: hover)`, `media.(inverted-colors: inverted)`, `media.(monochrome)`, `media.(orientation: landscape)`, `media.(overflow-block: scroll)`, `media.(pointer: coarse)`, `media.(pointer: fine)`, `media.(pointer: none)`, `media.(prefers-color-scheme: dark)`, `media.(prefers-contrast: more)`, `media.(prefers-contrast: no-preference)`, `media.(prefers-reduced-data: reduce)`, `media.(prefers-reduced-motion: reduce)`, `media.(prefers-reduced-transparency: reduce)`, `media.(scripting: enabled)`, `media.(update: fast)`, `media.(video-dynamic-range: high)`, `mediaCap`, `nav.appCodeName`, `nav.appName`, `nav.appVersion`, `nav.bluetooth`, `nav.canShare`, `nav.clearAppBadge`, `nav.clipboard`, `nav.connection`, `nav.cookieEnabled`, `nav.credentials`, `nav.deviceMemory`, `nav.devicePosture`, `nav.doNotTrack`, `nav.geolocation`, `nav.getBattery`, `nav.getInstalledRelatedApps`, `nav.gpu`, `nav.hid`, `nav.ink`, `nav.keyboard`, `nav.language`, `nav.languages`, `nav.locks`, `nav.login`, `nav.managed`, `nav.maxTouchPoints`, `nav.mediaCapabilities`, `nav.mediaDevices`, `nav.mediaSession`, `nav.onLine`, `nav.pdfViewerEnabled`, `nav.permissions`, `nav.platform`, `nav.presentation`, `nav.product`, `nav.productSub`, `nav.protectedAudience`, `nav.requestMIDIAccess`, `nav.scheduling`, `nav.sendBeacon`, `nav.serial`, `nav.serviceWorker`, `nav.setAppBadge`, `nav.share`, `nav.storage`, `nav.usb`, `nav.userActivation`, `nav.vendor`, `nav.vendorSub`, `nav.vibrate`, `nav.virtualKeyboard`, `nav.wakeLock`, `nav.webdriver`, `nav.windowControlsOverlay`, `nav.xr`, `navConnection.effectiveType`, `navConnection.saveData`, `navProto`, `perfMem.jsHeapSizeLimit`, `perms.accelerometer`, `perms.background-sync`, `perms.camera`, `perms.clipboard-read`, `perms.clipboard-write`, `perms.geolocation`, `perms.gyroscope`, `perms.local-fonts`, `perms.magnetometer`, `perms.microphone`, `perms.midi`, `perms.notifications`, `perms.payment-handler`, `perms.persistent-storage`, `perms.screen-wake-lock`, `perms.storage-access`, `perms.window-management`, `protoCounts.CSSStyleDeclaration`, `protoCounts.Document`, `protoCounts.Element`, `protoCounts.HTMLElement`, `protoCounts.Window`, `protoCounts.cssProps`, `screen.availLeft`, `screen.availTop`, `screen.colorDepth`, `screen.isExtended`, `screen.pixelDepth`, `screenOrientation.angle`, `screenOrientation.type`, `storage.persisted`, `storage.quotaGiB`, `storage.usage`, `ua`, `uad.brands`, `uad.mobile`, `uad.platform`, `uadHigh.architecture`, `uadHigh.bitness`, `uadHigh.brands`, `uadHigh.formFactors`, `uadHigh.fullVersionList`, `uadHigh.mobile`, `uadHigh.model`, `uadHigh.platform`, `uadHigh.platformVersion`, `uadHigh.uaFullVersion`, `uadHigh.wow64`, `win.DeviceMotionEvent`, `win.Notification`, `win.PaymentRequest`, `win.SharedWorker`, `win.chrome`, `win.external`, `win.getScreenDetails`, `win.launchQueue`, `win.ondeviceorientation`, `win.ontouchstart`, `win.openDatabase`, `win.outerMinusInnerH`, `win.outerMinusInnerW`, `win.queryLocalFonts`, `win.screenX`, `win.screenY`, `win.showOpenFilePicker`, `win.showSaveFilePicker`, `win.speechSynthesis`, `win.styleMedia`, `windowKeys`, `windowNames`

## detectors / headed
31 differing rows: 20 expected, 6 unexpected, 5 volatile

| row | control | fork | label | reason |
|---|---|---|---|---|
| det.creepjs.....avail | "1024 x 768" | "1920 x 1152" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs....screen | "1024 x 768" | "1920 x 1200" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.0% headless | "<absent>" | "52defe05" | unexpected |  |
| det.creepjs.25% like headless | "<absent>" | "fafdf9d1" | unexpected |  |
| det.creepjs.31% like headless | "eea7f026" | "<absent>" | unexpected |  |
| det.creepjs.33% headless | "a427e0b8" | "<absent>" | unexpected |  |
| det.creepjs.@media | "add1a585" | "0bb692ca" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.FP ID | "05161282d9fef367464c0d513a597bce4243be9fd29acc8a2d88744f928994b6" | "8800a54ad3e1483016ba9735441291146cea679381decedb34d6191aaea67593" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.Fuzzy | "433ab54433258616bce949f74de0cda8ffba498f8aee38fe1011000000000000" | "797ab544392586111c1949303de0c281ff57d9f369be00feb011000000000000" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.candidate | "2361435819 1 udp 2113937151 49858544-fe6a-40af-ab3d-b3f491aa9372.local 61795... | "1411714510 1 udp 2113937151 820d3a61-f94d-48cf-82ad-efaae8a23fea.local 52628... | volatile | a WebRTC candidate: per-load id and port |
| det.creepjs.copy | "f5d91537" | "6cc8f515" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.cores | "16, ram: 32" | "12, ram: 8" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.data | "bb870cc4" | "9c3054bd" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.freq | "164539.10744857788" | "164539.18825531006" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.lang | "en-US, en (en-US)" | "en-US (en-US)" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.lang (1) | "<absent>" | "en-US" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.lang (18) | "d185f3e1" | "<absent>" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.level | "100%" | "75%" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.matchMedia | "add1a585" | "0bb692ca" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.remote (0) | "<absent>" | "unsupported" | unexpected |  |
| det.creepjs.remote (19) | "036f6dce" | "<absent>" | unexpected |  |
| det.creepjs.rtt | "100, downlink: 1.55" | "100, downlink: 1.45" | volatile | a network estimate |
| det.creepjs.screen query | "1024 x 768" | "1920 x 1200" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.stack | "17781" | "17803" | volatile | stack depth, differed between two stock loads |
| det.creepjs.sum | "124.04347776696522" | "124.04199268739467" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.time | "502.59992877283" | "502.5976674908088" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.trap | "0.7317630114296103" | "0.004174826661066056" | volatile | a random value per load |
| det.creepjs.type & base ip | "2361435819" | "1411714510" | volatile | a WebRTC candidate hash, per load |
| det.sannysoft.navigator.mediaDevices | "audiooutput: id =" | "audioinput: id =" | expected | the identity's value, or a detector hash over identity values |
| det.sannysoft.screen.height | "768" | "1200" | expected | the identity's value, or a detector hash over identity values |
| det.sannysoft.screen.width | "1024" | "1920" | expected | the identity's value, or a detector hash over identity values |

## detectors / headless
33 differing rows: 23 expected, 6 unexpected, 4 volatile

| row | control | fork | label | reason |
|---|---|---|---|---|
| det.creepjs.....avail | "800 x 600" | "1920 x 1152" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs....screen | "800 x 600" | "1920 x 1200" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.0% headless | "<absent>" | "52defe05" | unexpected |  |
| det.creepjs.100% headless | "44172120" | "<absent>" | unexpected |  |
| det.creepjs.25% like headless | "<absent>" | "fafdf9d1" | unexpected |  |
| det.creepjs.31% like headless | "eea7f026" | "<absent>" | unexpected |  |
| det.creepjs.@media | "15a21ebb" | "0bb692ca" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.FP ID | "c7202d5be991a16e9dd41b28e0a24b785f56679a31768d2815e6f5090d2f69ca" | "8800a54ad3e1483016ba9735441291146cea679381decedb34d6191aaea67593" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.Fuzzy | "433ab5443625861ebce948f74de4cda8ff96a98f8aee38fe1411000000000000" | "797ab544392586111c1949303de0c281ff57d9f369be00feb011000000000000" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.candidate | "2393995338 1 udp 2113937151 b2ae8d3f-185e-4d9f-97c2-37b23174db4b.local 51474... | "3347564150 1 udp 2113937151 ea222f1d-8c1c-466f-9df8-03fbe57b98b9.local 53174... | volatile | a WebRTC candidate: per-load id and port |
| det.creepjs.copy | "f5d91537" | "6cc8f515" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.cores | "16, ram: 32" | "12, ram: 8" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.data | "bb870cc4" | "9c3054bd" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.freq | "164539.10744857788" | "164539.18825531006" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.lang | "en-US, en (en-US)" | "en-US (en-US)" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.lang (1) | "<absent>" | "en-US" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.lang (18) | "d185f3e1" | "<absent>" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.level | "100%" | "75%" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.matchMedia | "15a21ebb" | "0bb692ca" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.remote (0) | "<absent>" | "unsupported" | unexpected |  |
| det.creepjs.remote (19) | "036f6dce" | "<absent>" | unexpected |  |
| det.creepjs.screen query | "800 x 600" | "1920 x 1200" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.stack | "17787" | "17789" | volatile | stack depth, differed between two stock loads |
| det.creepjs.sum | "124.04347776696522" | "124.04199268739467" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.time | "502.59992877283" | "502.5976674908088" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.trap | "0.9514102393854017" | "0.5679774924700104" | volatile | a random value per load |
| det.creepjs.type & base ip | "2393995338" | "3347564150" | volatile | a WebRTC candidate hash, per load |
| det.sannysoft.CHR_MEMORY | "FAIL \| " | "ok \| " | expected | stock headless fails it (deviceMemory absent); the identity sets it |
| det.sannysoft.HEADCHR_UA | "FAIL \| " | "ok \| " | expected | stock headless says HeadlessChrome; the identity UA does not |
| det.sannysoft.navigator.mediaDevices | "audiooutput: id =" | "audioinput: id =" | expected | the identity's value, or a detector hash over identity values |
| det.sannysoft.navigator.userAgent | "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge... | "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge... | expected | the identity's value, or a detector hash over identity values |
| det.sannysoft.screen.height | "600" | "1200" | expected | the identity's value, or a detector hash over identity values |
| det.sannysoft.screen.width | "800" | "1920" | expected | the identity's value, or a detector hash over identity values |

## detector text browserscan / headed
control only (12):
- `"1024×768"`
- `"1024×768"`
- `"16"`
- `"32"`
- `"Asia/Saigon"`
- `"Bot Control"`
- `"Fonts listShow all fonts(132)"`
- `"What is a robot?"`
- `"Yes"`
- `"YesDetection"`
- `"Your browser environment appears to be controlled by a robot."`
- `"en-US,en"`
fork only (10):
- `"12"`
- `"1920×1152"`
- `"1920×1200"`
- `"8"`
- `"America/Chicago"`
- `"Fonts listShow all fonts(95)"`
- `"No"`
- `"NoDetection"`
- `"WebGL exception"`
- `"en-US"`

## detector text browserscan / headless
control only (16):
- `"16"`
- `"32"`
- `"800×600"`
- `"800×600"`
- `"Asia/Saigon"`
- `"Bot Control"`
- `"Chrome Headless"`
- `"Chrome Headless 154.0.8037.93 Detection"`
- `"Fonts listShow all fonts(132)"`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"What is a robot?"`
- `"Yes"`
- `"YesDetection"`
- `"Your browser environment appears to be controlled by a robot."`
- `"en-US,en"`
fork only (17):
- `"12"`
- `"1920×1152"`
- `"1920×1200"`
- `"8"`
- `"America/Chicago"`
- `"Chrome"`
- `"Chrome 154.0.8037.93 Detection"`
- `"EN"`
- `"Fonts listShow all fonts(95)"`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"No"`
- `"NoDetection"`
- `"WebGL exception"`
- `"blog"`
- `"en-US"`
- `"privacy"`

## detector text creepjs / headed
control only (47):
- `"-27028710390000"`
- `"-420"`
- `"....avail: 1024 x 768"`
- `"...screen: 1024 x 768"`
- `"0.01796726806640625"`
- `"1004"`
- `"31% like headless: eea7f026"`
- `"33% headless: a427e0b8"`
- `"653"`
- `"653"`
- `"748"`
- `"973"`
- `"988"`
- `"@media: add1a585"`
- `"Asia, Saigon"`
- `"Asia/Saigon (-420)"`
- `"Audiod0c60a78"`
- `"CSS Media Queries18cddf77"`
- `"Canvas 2dd3a7e3d4"`
- `"FP ID: 05161282d9fef367464c0d513a597bce4243be9fd29acc8a2d88744f928994b6"`
- `"Fuzzy: 433ab54433258616bce949f74de0cda8ffba498f8aee38fe1011000000000000"`
- `"Headless00d6032f"`
- `"Indochina Time"`
- `"Intl4b9c0772"`
- `"July at Indochina Time"`
- `"Navigatore8cbab8b"`
- `"Screenba0b0baf"`
- `"Speech77bd6c70"`
- `"Timezone1d1c75e3"`
- `"Workera005e692"`
- `"audio"`
- `"copy:f5d91537"`
- `"cores: 16, ram: 32"`
- `"cores: 16, ram: 32, touch: 0, bluetooth"`
- `"data: bb870cc4"`
- `"data:f5d91537"`
- `"devices (1):"`
- `"freq: 164539.10744857788"`
- `"lang (18): d185f3e1"`
- `"lang: en-US, en (en-US)"`
- `"level: 100%"`
- `"matchMedia: add1a585"`
- `"remote (19): 036f6dce"`
- `"screen query: 1024 x 768"`
- `"sum: 124.04347776696522"`
- `"time: 502.59992877283"`
- `"😀🤵‍♂️⚧...✌☝❄"`
fork only (47):
- `"-27028663764000"`
- `"....avail: 1920 x 1152"`
- `"...screen: 1920 x 1200"`
- `"0% headless: 52defe05"`
- `"0.044378245697021486"`
- `"1013"`
- `"1028"`
- `"1152"`
- `"1920"`
- `"25% like headless: fafdf9d1"`
- `"300"`
- `"693"`
- `"693"`
- `"@media: 0bb692ca"`
- `"America, Chicago"`
- `"America/Chicago (300)"`
- `"Audio836bc7c7"`
- `"CSS Media Queriescda12a5d"`
- `"Canvas 2d4bdd42a4"`
- `"Central Daylight Time"`
- `"FP ID: 8800a54ad3e1483016ba9735441291146cea679381decedb34d6191aaea67593"`
- `"Fuzzy: 797ab544392586111c1949303de0c281ff57d9f369be00feb011000000000000"`
- `"Headlessc84e0876"`
- `"Intl5c90eef3"`
- `"July at Central Daylight Time"`
- `"Navigatorfa8ecbea"`
- `"Screencb176f35"`
- `"Speechd8216ffd"`
- `"Timezone432a225a"`
- `"Worker99ad3822"`
- `"copy:6cc8f515"`
- `"cores: 12, ram: 8"`
- `"cores: 12, ram: 8, touch: 0, bluetooth"`
- `"data: 9c3054bd"`
- `"data:6cc8f515"`
- `"devices (3):"`
- `"freq: 164539.18825531006"`
- `"lang (1): en-US"`
- `"lang: en-US (en-US)"`
- `"level: 75%"`
- `"matchMedia: 0bb692ca"`
- `"mic, audio, webcam"`
- `"remote (0): unsupported"`
- `"screen query: 1920 x 1200"`
- `"sum: 124.04199268739467"`
- `"time: 502.5976674908088"`
- `"😀☺🤵‍♂️...✴🅰🅿"`

## detector text creepjs / headless
control only (50):
- `"-27028710390000"`
- `"-420"`
- `"....avail: 800 x 600"`
- `"...screen: 800 x 600"`
- `"0.01796726806640625"`
- `"100% headless: 44172120"`
- `"31% like headless: eea7f026"`
- `"485"`
- `"485"`
- `"5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Hea...`
- `"580"`
- `"749"`
- `"764"`
- `"780"`
- `"@media: 15a21ebb"`
- `"Asia, Saigon"`
- `"Asia/Saigon (-420)"`
- `"Audiod0c60a78"`
- `"CSS Media Queriescb597810"`
- `"Canvas 2dd3a7e3d4"`
- `"FP ID: c7202d5be991a16e9dd41b28e0a24b785f56679a31768d2815e6f5090d2f69ca"`
- `"Fuzzy: 433ab5443625861ebce948f74de4cda8ff96a98f8aee38fe1411000000000000"`
- `"Headless7519e9f3"`
- `"Indochina Time"`
- `"Intl4b9c0772"`
- `"July at Indochina Time"`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Navigator7a91b622"`
- `"Screenb0313e03"`
- `"Speech77bd6c70"`
- `"Timezone1d1c75e3"`
- `"Workerca66798d"`
- `"audio"`
- `"copy:f5d91537"`
- `"cores: 16, ram: 32"`
- `"cores: 16, ram: 32, touch: 0, bluetooth"`
- `"data: bb870cc4"`
- `"data:f5d91537"`
- `"devices (1):"`
- `"freq: 164539.10744857788"`
- `"lang (18): d185f3e1"`
- `"lang: en-US, en (en-US)"`
- `"level: 100%"`
- `"matchMedia: 15a21ebb"`
- `"remote (19): 036f6dce"`
- `"screen query: 800 x 600"`
- `"sum: 124.04347776696522"`
- `"time: 502.59992877283"`
- `"😀🤵‍♂️⚧...✌☝❄"`
fork only (52):
- `"-27028663764000"`
- `"....avail: 1920 x 1152"`
- `"...screen: 1920 x 1200"`
- `"0% headless: 52defe05"`
- `"0.044378245697021486"`
- `"1057"`
- `"1057"`
- `"1152"`
- `"1889"`
- `"1904"`
- `"1920"`
- `"25% like headless: fafdf9d1"`
- `"300"`
- `"5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chr...`
- `"@media: 0bb692ca"`
- `"America, Chicago"`
- `"America/Chicago (300)"`
- `"Audio836bc7c7"`
- `"CSS Media Queriescda12a5d"`
- `"Canvas 2d4bdd42a4"`
- `"Central Daylight Time"`
- `"FP ID: 8800a54ad3e1483016ba9735441291146cea679381decedb34d6191aaea67593"`
- `"Fuzzy: 797ab544392586111c1949303de0c281ff57d9f369be00feb011000000000000"`
- `"Headlessc84e0876"`
- `"Intl5c90eef3"`
- `"July at Central Daylight Time"`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Navigatorfa8ecbea"`
- `"Screencb176f35"`
- `"Speechd8216ffd"`
- `"Timezone432a225a"`
- `"Worker99ad3822"`
- `"copy:6cc8f515"`
- `"cores: 12, ram: 8"`
- `"cores: 12, ram: 8, touch: 0, bluetooth"`
- `"data: 9c3054bd"`
- `"data:6cc8f515"`
- `"devices (3):"`
- `"freq: 164539.18825531006"`
- `"lang (1): en-US"`
- `"lang: en-US (en-US)"`
- `"level: 75%"`
- `"matchMedia: 0bb692ca"`
- `"mic, audio, webcam"`
- `"remote (0): unsupported"`
- `"screen query: 1920 x 1200"`
- `"sum: 124.04199268739467"`
- `"time: 502.5976674908088"`
- `"ua reduction"`
- `"ua reduction"`
- `"😀☺🤵‍♂️...✴🅰🅿"`

## detector text pixelscan / headed
control only (17):
- `"1024x768"`
- `"1024x768"`
- `"16"`
- `"1d8a8ca496331df64eaed6c1b94af209"`
- `"3b877f7c7844a53dc686c4624374b3c5"`
- `"Asia/Saigon"`
- `"Automated behavior detected"`
- `"Back"`
- `"Back"`
- `"Back"`
- `"Back"`
- `"Join Pixelscan Community"`
- `"No"`
- `"No masking detected"`
- `"<country> / <district>"`
- `"e88cfd9ca1a4be738f002bdfafe5d828"`
- `"en"`
fork only (12):
- `"12"`
- `"1920x1152"`
- `"1920x1200"`
- `"America/Chicago"`
- `"Best antidetect browsers"`
- `"Masking detected"`
- `"No automated behavior detected"`
- `"Timezone spoofed"`
- `"Yes"`
- `"bcd372891ffe7aae25961a96a779cbe4"`
- `"cb22acb5233d976c2cd34286f0deec71"`
- `"f9f0cc6e29e2f08ca0b2de7146fa07e0"`

## detector text pixelscan / headless
control only (19):
- `"16"`
- `"1d8a8ca496331df64eaed6c1b94af209"`
- `"3b877f7c7844a53dc686c4624374b3c5"`
- `"800x600"`
- `"800x600"`
- `"Asia/Saigon"`
- `"Automated behavior detected"`
- `"Back"`
- `"Back"`
- `"Back"`
- `"Back"`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"No"`
- `"No masking detected"`
- `"<country> / <district>"`
- `"a Сhromium-based browser on Windows"`
- `"e88cfd9ca1a4be738f002bdfafe5d828"`
- `"en"`
fork only (15):
- `"12"`
- `"1920x1152"`
- `"1920x1200"`
- `"America/Chicago"`
- `"Best antidetect browsers"`
- `"Chrome 154.0.0.0 on Windows"`
- `"Masking detected"`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"No automated behavior detected"`
- `"Timezone spoofed"`
- `"Yes"`
- `"bcd372891ffe7aae25961a96a779cbe4"`
- `"cb22acb5233d976c2cd34286f0deec71"`
- `"f9f0cc6e29e2f08ca0b2de7146fa07e0"`

## detector text sannysoft / headed
control only (39):
- `"\"cWidth\": 957,"`
- `"\"cWidth\": 957,"`
- `"\"deviceMemory\": 32,"`
- `"\"en\""`
- `"\"en\""`
- `"\"en-US\","`
- `"\"en-US\","`
- `"\"micros\": 0,"`
- `"\"sAvailHeight\": 768,"`
- `"\"sAvailHeight\": 768,"`
- `"\"sAvailWidth\": 1024,"`
- `"\"sAvailWidth\": 1024,"`
- `"\"sHeight\": 768,"`
- `"\"sHeight\": 768,"`
- `"\"sWidth\": 1024,"`
- `"\"sWidth\": 1024,"`
- `"\"wInnerHeight\": 653,"`
- `"\"wInnerHeight\": 653,"`
- `"\"wInnerWidth\": 988,"`
- `"\"wInnerWidth\": 988,"`
- `"\"wOuterHeight\": 748,"`
- `"\"wOuterHeight\": 748,"`
- `"\"wOuterWidth\": 1004,"`
- `"\"wOuterWidth\": 1004,"`
- `"\"wScreenX\": 10,"`
- `"\"wScreenX\": 10,"`
- `"\"webDriverValue\": true,"`
- `"\"webcams\": 0"`
- `"Hash: 1118196126"`
- `"Hash: 1118196126"`
- `"Hash: 1118196126"`
- `"Hash: 1118196126"`
- `"Hash: 1118196126"`
- `"Level: 1"`
- `"en-US,en"`
- `"navigator.mediaDevices\taudiooutput: id ="`
- `"present (failed)"`
- `"screen.height\t768"`
- `"screen.width\t1024"`
fork only (39):
- `"\"cWidth\": 997,"`
- `"\"cWidth\": 997,"`
- `"\"deviceMemory\": 8,"`
- `"\"en-US\""`
- `"\"en-US\""`
- `"\"micros\": 1,"`
- `"\"sAvailHeight\": 1152,"`
- `"\"sAvailHeight\": 1152,"`
- `"\"sAvailWidth\": 1920,"`
- `"\"sAvailWidth\": 1920,"`
- `"\"sHeight\": 1200,"`
- `"\"sHeight\": 1200,"`
- `"\"sWidth\": 1920,"`
- `"\"sWidth\": 1920,"`
- `"\"wInnerHeight\": 693,"`
- `"\"wInnerHeight\": 693,"`
- `"\"wInnerWidth\": 1028,"`
- `"\"wInnerWidth\": 1028,"`
- `"\"wOuterHeight\": 1152,"`
- `"\"wOuterHeight\": 1152,"`
- `"\"wOuterWidth\": 1920,"`
- `"\"wOuterWidth\": 1920,"`
- `"\"wScreenX\": 0,"`
- `"\"wScreenX\": 0,"`
- `"\"webDriverValue\": false,"`
- `"\"webcams\": 1"`
- `"Hash: -1692250503"`
- `"Hash: -1692250503"`
- `"Hash: -1692250503"`
- `"Hash: -1692250503"`
- `"Hash: -1692250503"`
- `"Level: 0.75"`
- `"audiooutput: id ="`
- `"en-US"`
- `"missing (passed)"`
- `"navigator.mediaDevices\taudioinput: id ="`
- `"screen.height\t1200"`
- `"screen.width\t1920"`
- `"videoinput: id ="`

## detector text sannysoft / headless
control only (48):
- `"\"cHeight\": 1615,"`
- `"\"cHeight\": 1615,"`
- `"\"cWidth\": 733,"`
- `"\"cWidth\": 733,"`
- `"\"deviceMemory\": 32,"`
- `"\"en\""`
- `"\"en\""`
- `"\"en-US\","`
- `"\"en-US\","`
- `"\"micros\": 0,"`
- `"\"sAvailHeight\": 600,"`
- `"\"sAvailHeight\": 600,"`
- `"\"sAvailWidth\": 800,"`
- `"\"sAvailWidth\": 800,"`
- `"\"sHeight\": 600,"`
- `"\"sHeight\": 600,"`
- `"\"sWidth\": 800,"`
- `"\"sWidth\": 800,"`
- `"\"userAgent\": \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3...`
- `"\"userAgent\": \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3...`
- `"\"userAgent\": \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3...`
- `"\"wInnerHeight\": 485,"`
- `"\"wInnerHeight\": 485,"`
- `"\"wInnerWidth\": 764,"`
- `"\"wInnerWidth\": 764,"`
- `"\"wOuterHeight\": 580,"`
- `"\"wOuterHeight\": 580,"`
- `"\"wOuterWidth\": 780,"`
- `"\"wOuterWidth\": 780,"`
- `"\"wScreenX\": 10,"`
- `"\"wScreenX\": 10,"`
- `"\"webDriverValue\": true,"`
- `"\"webcams\": 0"`
- `"CHR_MEMORY\tFAIL"`
- `"HEADCHR_UA\tFAIL"`
- `"Hash: 1118196126"`
- `"Hash: 1118196126"`
- `"Hash: 1118196126"`
- `"Hash: 1118196126"`
- `"Hash: 1118196126"`
- `"Level: 1"`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"en-US,en"`
- `"navigator.mediaDevices\taudiooutput: id ="`
- `"navigator.userAgent\tMozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/5...`
- `"present (failed)"`
- `"screen.height\t600"`
- `"screen.width\t800"`
fork only (48):
- `"\"cHeight\": 1579,"`
- `"\"cHeight\": 1579,"`
- `"\"cWidth\": 1873,"`
- `"\"cWidth\": 1873,"`
- `"\"deviceMemory\": 8,"`
- `"\"en-US\""`
- `"\"en-US\""`
- `"\"micros\": 1,"`
- `"\"sAvailHeight\": 1152,"`
- `"\"sAvailHeight\": 1152,"`
- `"\"sAvailWidth\": 1920,"`
- `"\"sAvailWidth\": 1920,"`
- `"\"sHeight\": 1200,"`
- `"\"sHeight\": 1200,"`
- `"\"sWidth\": 1920,"`
- `"\"sWidth\": 1920,"`
- `"\"userAgent\": \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3...`
- `"\"userAgent\": \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3...`
- `"\"userAgent\": \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3...`
- `"\"wInnerHeight\": 1057,"`
- `"\"wInnerHeight\": 1057,"`
- `"\"wInnerWidth\": 1904,"`
- `"\"wInnerWidth\": 1904,"`
- `"\"wOuterHeight\": 1152,"`
- `"\"wOuterHeight\": 1152,"`
- `"\"wOuterWidth\": 1920,"`
- `"\"wOuterWidth\": 1920,"`
- `"\"wScreenX\": 0,"`
- `"\"wScreenX\": 0,"`
- `"\"webDriverValue\": false,"`
- `"\"webcams\": 1"`
- `"CHR_MEMORY\tok"`
- `"HEADCHR_UA\tok"`
- `"Hash: -1692250503"`
- `"Hash: -1692250503"`
- `"Hash: -1692250503"`
- `"Hash: -1692250503"`
- `"Hash: -1692250503"`
- `"Level: 0.75"`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"audiooutput: id ="`
- `"en-US"`
- `"missing (passed)"`
- `"navigator.mediaDevices\taudioinput: id ="`
- `"navigator.userAgent\tMozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/5...`
- `"screen.height\t1200"`
- `"screen.width\t1920"`
- `"videoinput: id ="`

