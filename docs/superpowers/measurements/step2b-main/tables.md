# Step 2 tables

Run `20261014-053445`; control 154.0.8037.93, fork 154.0.8037.93; flags {}.

## oracle / headed
22 differing rows: 18 expected, 4 volatile

| row | control | fork | label | reason |
|---|---|---|---|---|
| oracle.audioFp | "384.810240" | "384.806327" | expected | identity- or machine-bound; compared by type |
| oracle.canvas.shape | "c662b8ad" | "b6d16345" | expected | identity- or machine-bound; compared by type |
| oracle.canvas.text | "f128eb83" | "e32d3673" | expected | identity- or machine-bound; compared by type |
| oracle.err.stack | "at http://<ip>:52178/" | "at http://<ip>:52199/" | volatile | names the page's server, whose port changes per launch |
| oracle.intl.date0 | "Thu Jan 01 1970 08:00:00 GMT+0800 (Indochina Time)" | "Wed Dec 31 1969 18:00:00 GMT-0600 (Central Standard Time)" | expected | identity- or machine-bound; compared by type |
| oracle.intl.dtf.timeZone | "Asia/Saigon" | "America/Chicago" | expected | identity- or machine-bound; compared by type |
| oracle.mediaDevices | [["audiooutput", "", 0, 0]] | [["audioinput", "", 0, 0], ["videoinput", "", 0, 0], ["audiooutput", "", 0, 0]] | expected | identity- or machine-bound; compared by type |
| oracle.nav.deviceMemory | 32 | 8 | expected | identity- or machine-bound; compared by type |
| oracle.nav.hardwareConcurrency | 16 | 12 | expected | identity- or machine-bound; compared by type |
| oracle.nav.languages | ["en-US", "en"] | ["en-US"] | expected | identity- or machine-bound; compared by type |
| oracle.nav.webdriver | true | false | expected | SP2: the fork hides automation; stock under the same driver reports true |
| oracle.navConnection.downlink | 1.6 | 1.55 | volatile | a network estimate; 1.75 vs 1.6 between two stock launches |
| oracle.navConnection.rtt | 0 | 100 | volatile | a network estimate; changed between two launches of one stock profile |
| oracle.screen.availHeight | 984 | 1152 | expected | identity- or machine-bound; compared by type |
| oracle.screen.availWidth | 1280 | 1920 | expected | identity- or machine-bound; compared by type |
| oracle.screen.height | 1024 | 1200 | expected | identity- or machine-bound; compared by type |
| oracle.screen.width | 1280 | 1920 | expected | identity- or machine-bound; compared by type |
| oracle.voices | [["Google Deutsch", "de-DE", false, true], ["Google US English", "en-US", fal... | [["Microsoft David - English (United States)", "en-US", true, true], ["Micros... | volatile | speechSynthesis loads asynchronously; stock's list differed between launches of one profile |
| oracle.win.outerMinusInnerH | 95 | 203 | expected | identity- or machine-bound; compared by type |
| oracle.win.outerMinusInnerW | 16 | 636 | expected | identity- or machine-bound; compared by type |
| oracle.win.screenX | 10 | 0 | expected | identity- or machine-bound; compared by type |
| oracle.win.screenY | 10 | 0 | expected | identity- or machine-bound; compared by type |

## oracle / headless
22 differing rows: 18 expected, 4 volatile

| row | control | fork | label | reason |
|---|---|---|---|---|
| oracle.audioFp | "384.810240" | "384.806327" | expected | identity- or machine-bound; compared by type |
| oracle.canvas.shape | "c662b8ad" | "b6d16345" | expected | identity- or machine-bound; compared by type |
| oracle.canvas.text | "f128eb83" | "e32d3673" | expected | identity- or machine-bound; compared by type |
| oracle.err.stack | "at http://<ip>:52204/" | "at http://<ip>:52223/" | volatile | names the page's server, whose port changes per launch |
| oracle.intl.date0 | "Thu Jan 01 1970 08:00:00 GMT+0800 (Indochina Time)" | "Wed Dec 31 1969 18:00:00 GMT-0600 (Central Standard Time)" | expected | identity- or machine-bound; compared by type |
| oracle.intl.dtf.timeZone | "Asia/Saigon" | "America/Chicago" | expected | identity- or machine-bound; compared by type |
| oracle.mediaDevices | [["audiooutput", "", 0, 0]] | [["audioinput", "", 0, 0], ["videoinput", "", 0, 0], ["audiooutput", "", 0, 0]] | expected | identity- or machine-bound; compared by type |
| oracle.nav.appVersion | "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Hea... | "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chr... | expected | the identity's User-Agent; stock headless says HeadlessChrome |
| oracle.nav.deviceMemory | 32 | 8 | expected | identity- or machine-bound; compared by type |
| oracle.nav.hardwareConcurrency | 16 | 12 | expected | identity- or machine-bound; compared by type |
| oracle.nav.languages | ["en-US", "en"] | ["en-US"] | expected | identity- or machine-bound; compared by type |
| oracle.nav.webdriver | true | false | expected | SP2: the fork hides automation; stock under the same driver reports true |
| oracle.navConnection.downlink | 1.5 | 1.45 | volatile | a network estimate; 1.75 vs 1.6 between two stock launches |
| oracle.navConnection.rtt | 0 | 100 | volatile | a network estimate; changed between two launches of one stock profile |
| oracle.screen.availHeight | 600 | 1152 | expected | identity- or machine-bound; compared by type |
| oracle.screen.availWidth | 800 | 1920 | expected | identity- or machine-bound; compared by type |
| oracle.screen.height | 600 | 1200 | expected | identity- or machine-bound; compared by type |
| oracle.screen.width | 800 | 1920 | expected | identity- or machine-bound; compared by type |
| oracle.ua | "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge... | "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge... | expected | the identity's User-Agent; stock headless says HeadlessChrome |
| oracle.voices | [["Google Deutsch", "de-DE", false, true], ["Google US English", "en-US", fal... | [["Microsoft David - English (United States)", "en-US", true, true], ["Micros... | volatile | speechSynthesis loads asynchronously; stock's list differed between launches of one profile |
| oracle.win.screenX | 10 | 0 | expected | identity- or machine-bound; compared by type |
| oracle.win.screenY | 10 | 0 | expected | identity- or machine-bound; compared by type |

## noise / headed
0 differing rows: 

## noise / headless
0 differing rows: 

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
0 differing rows: 

## linkability / headed
1 differing rows: 1 expected

| row | control | fork | label | reason |
|---|---|---|---|---|
| link.shared | ["audio.baseLatency", "audio.channelCount", "audio.maxChannelCount", "audio.o... | ["audio.baseLatency", "audio.channelCount", "audio.maxChannelCount", "audio.o... | expected | a record of what two profiles share, not a fork-vs-control finding |

Leaves the two fork profiles share (219 of 238):

`audio.baseLatency`, `audio.channelCount`, `audio.maxChannelCount`, `audio.outputLatency`, `audio.sampleRate`, `audio.state`, `codecs.application/vnd.apple.mpegurl`, `codecs.audio/flac`, `codecs.audio/mp4; codecs="mp4a.40.2"`, `codecs.audio/mpeg`, `codecs.audio/ogg; codecs="opus"`, `codecs.audio/wav`, `codecs.video/mp4; codecs="ac-3"`, `codecs.video/mp4; codecs="av01.0.05M.08"`, `codecs.video/mp4; codecs="avc1.42E01E"`, `codecs.video/mp4; codecs="ec-3"`, `codecs.video/mp4; codecs="hev1.1.6.L93.B0"`, `codecs.video/webm; codecs="vp8"`, `codecs.video/webm; codecs="vp9"`, `codecs.video/x-matroska; codecs="avc1"`, `done`, `err.toStringLen`, `fonts.calibri`, `fonts.dejavu`, `fonts.segoe`, `gpu.features`, `gpu.info.architecture`, `gpu.info.description`, `gpu.info.device`, `gpu.info.vendor`, `gpu.limits.maxBindGroups`, `gpu.limits.maxBufferSize`, `gpu.limits.maxComputeWorkgroupSizeX`, `gpu.limits.maxStorageBufferBindingSize`, `gpu.limits.maxTextureDimension2D`, `intl.collator`, `intl.dtf.calendar`, `intl.dtf.day`, `intl.dtf.locale`, `intl.dtf.month`, `intl.dtf.numberingSystem`, `intl.dtf.year`, `intl.durationFormat`, `intl.nf.locale`, `intl.nf.maximumFractionDigits`, `intl.nf.minimumFractionDigits`, `intl.nf.minimumIntegerDigits`, `intl.nf.notation`, `intl.nf.numberingSystem`, `intl.nf.roundingIncrement`, `intl.nf.roundingMode`, `intl.nf.roundingPriority`, `intl.nf.signDisplay`, `intl.nf.style`, `intl.nf.trailingZeroDisplay`, `intl.nf.useGrouping`, `intl.segmenter`, `intl.tzCount`, `keyboard.Backquote`, `keyboard.Digit1`, `keyboard.KeyA`, `keyboard.KeyQ`, `keyboard.size`, `media.(-webkit-min-device-pixel-ratio: 1)`, `media.(any-hover: hover)`, `media.(any-pointer: fine)`, `media.(color-gamut: p3)`, `media.(color-gamut: rec2020)`, `media.(color-gamut: srgb)`, `media.(color: 10)`, `media.(color: 8)`, `media.(display-mode: browser)`, `media.(dynamic-range: high)`, `media.(forced-colors: active)`, `media.(hover: hover)`, `media.(inverted-colors: inverted)`, `media.(monochrome)`, `media.(orientation: landscape)`, `media.(overflow-block: scroll)`, `media.(pointer: coarse)`, `media.(pointer: fine)`, `media.(pointer: none)`, `media.(prefers-color-scheme: dark)`, `media.(prefers-contrast: more)`, `media.(prefers-contrast: no-preference)`, `media.(prefers-reduced-data: reduce)`, `media.(prefers-reduced-motion: reduce)`, `media.(prefers-reduced-transparency: reduce)`, `media.(scripting: enabled)`, `media.(update: fast)`, `media.(video-dynamic-range: high)`, `mediaCap`, `nav.appCodeName`, `nav.appName`, `nav.appVersion`, `nav.bluetooth`, `nav.canShare`, `nav.clearAppBadge`, `nav.clipboard`, `nav.connection`, `nav.cookieEnabled`, `nav.credentials`, `nav.deviceMemory`, `nav.devicePosture`, `nav.doNotTrack`, `nav.geolocation`, `nav.getBattery`, `nav.getInstalledRelatedApps`, `nav.gpu`, `nav.hid`, `nav.ink`, `nav.keyboard`, `nav.language`, `nav.languages`, `nav.locks`, `nav.login`, `nav.managed`, `nav.maxTouchPoints`, `nav.mediaCapabilities`, `nav.mediaDevices`, `nav.mediaSession`, `nav.onLine`, `nav.pdfViewerEnabled`, `nav.permissions`, `nav.platform`, `nav.presentation`, `nav.product`, `nav.productSub`, `nav.protectedAudience`, `nav.requestMIDIAccess`, `nav.scheduling`, `nav.sendBeacon`, `nav.serial`, `nav.serviceWorker`, `nav.setAppBadge`, `nav.share`, `nav.storage`, `nav.usb`, `nav.userActivation`, `nav.vendor`, `nav.vendorSub`, `nav.vibrate`, `nav.virtualKeyboard`, `nav.wakeLock`, `nav.webdriver`, `nav.windowControlsOverlay`, `nav.xr`, `navConnection.effectiveType`, `navConnection.saveData`, `navProto`, `perfMem.jsHeapSizeLimit`, `perms.accelerometer`, `perms.background-sync`, `perms.camera`, `perms.clipboard-read`, `perms.clipboard-write`, `perms.geolocation`, `perms.gyroscope`, `perms.local-fonts`, `perms.magnetometer`, `perms.microphone`, `perms.midi`, `perms.notifications`, `perms.payment-handler`, `perms.persistent-storage`, `perms.screen-wake-lock`, `perms.storage-access`, `perms.window-management`, `protoCounts.CSSStyleDeclaration`, `protoCounts.Document`, `protoCounts.Element`, `protoCounts.HTMLElement`, `protoCounts.Window`, `protoCounts.cssProps`, `screen.availLeft`, `screen.availTop`, `screen.colorDepth`, `screen.isExtended`, `screen.pixelDepth`, `screenOrientation.angle`, `screenOrientation.type`, `storage.persisted`, `storage.quotaGiB`, `storage.usage`, `ua`, `uad.brands`, `uad.mobile`, `uad.platform`, `uadHigh.architecture`, `uadHigh.bitness`, `uadHigh.brands`, `uadHigh.formFactors`, `uadHigh.fullVersionList`, `uadHigh.mobile`, `uadHigh.model`, `uadHigh.platform`, `uadHigh.platformVersion`, `uadHigh.uaFullVersion`, `uadHigh.wow64`, `win.DeviceMotionEvent`, `win.Notification`, `win.PaymentRequest`, `win.SharedWorker`, `win.chrome`, `win.external`, `win.getScreenDetails`, `win.launchQueue`, `win.ondeviceorientation`, `win.ontouchstart`, `win.openDatabase`, `win.queryLocalFonts`, `win.screenX`, `win.screenY`, `win.showOpenFilePicker`, `win.showSaveFilePicker`, `win.speechSynthesis`, `win.styleMedia`, `windowKeys`, `windowNames`

## linkability / headless
1 differing rows: 1 expected

| row | control | fork | label | reason |
|---|---|---|---|---|
| link.shared | ["audio.baseLatency", "audio.channelCount", "audio.maxChannelCount", "audio.o... | ["audio.baseLatency", "audio.channelCount", "audio.maxChannelCount", "audio.o... | expected | a record of what two profiles share, not a fork-vs-control finding |

Leaves the two fork profiles share (221 of 238):

`audio.baseLatency`, `audio.channelCount`, `audio.maxChannelCount`, `audio.outputLatency`, `audio.sampleRate`, `audio.state`, `codecs.application/vnd.apple.mpegurl`, `codecs.audio/flac`, `codecs.audio/mp4; codecs="mp4a.40.2"`, `codecs.audio/mpeg`, `codecs.audio/ogg; codecs="opus"`, `codecs.audio/wav`, `codecs.video/mp4; codecs="ac-3"`, `codecs.video/mp4; codecs="av01.0.05M.08"`, `codecs.video/mp4; codecs="avc1.42E01E"`, `codecs.video/mp4; codecs="ec-3"`, `codecs.video/mp4; codecs="hev1.1.6.L93.B0"`, `codecs.video/webm; codecs="vp8"`, `codecs.video/webm; codecs="vp9"`, `codecs.video/x-matroska; codecs="avc1"`, `done`, `err.toStringLen`, `fonts.calibri`, `fonts.dejavu`, `fonts.segoe`, `gpu.features`, `gpu.info.architecture`, `gpu.info.description`, `gpu.info.device`, `gpu.info.vendor`, `gpu.limits.maxBindGroups`, `gpu.limits.maxBufferSize`, `gpu.limits.maxComputeWorkgroupSizeX`, `gpu.limits.maxStorageBufferBindingSize`, `gpu.limits.maxTextureDimension2D`, `intl.collator`, `intl.dtf.calendar`, `intl.dtf.day`, `intl.dtf.locale`, `intl.dtf.month`, `intl.dtf.numberingSystem`, `intl.dtf.year`, `intl.durationFormat`, `intl.nf.locale`, `intl.nf.maximumFractionDigits`, `intl.nf.minimumFractionDigits`, `intl.nf.minimumIntegerDigits`, `intl.nf.notation`, `intl.nf.numberingSystem`, `intl.nf.roundingIncrement`, `intl.nf.roundingMode`, `intl.nf.roundingPriority`, `intl.nf.signDisplay`, `intl.nf.style`, `intl.nf.trailingZeroDisplay`, `intl.nf.useGrouping`, `intl.segmenter`, `intl.tzCount`, `keyboard.Backquote`, `keyboard.Digit1`, `keyboard.KeyA`, `keyboard.KeyQ`, `keyboard.size`, `media.(-webkit-min-device-pixel-ratio: 1)`, `media.(any-hover: hover)`, `media.(any-pointer: fine)`, `media.(color-gamut: p3)`, `media.(color-gamut: rec2020)`, `media.(color-gamut: srgb)`, `media.(color: 10)`, `media.(color: 8)`, `media.(display-mode: browser)`, `media.(dynamic-range: high)`, `media.(forced-colors: active)`, `media.(hover: hover)`, `media.(inverted-colors: inverted)`, `media.(monochrome)`, `media.(orientation: landscape)`, `media.(overflow-block: scroll)`, `media.(pointer: coarse)`, `media.(pointer: fine)`, `media.(pointer: none)`, `media.(prefers-color-scheme: dark)`, `media.(prefers-contrast: more)`, `media.(prefers-contrast: no-preference)`, `media.(prefers-reduced-data: reduce)`, `media.(prefers-reduced-motion: reduce)`, `media.(prefers-reduced-transparency: reduce)`, `media.(scripting: enabled)`, `media.(update: fast)`, `media.(video-dynamic-range: high)`, `mediaCap`, `nav.appCodeName`, `nav.appName`, `nav.appVersion`, `nav.bluetooth`, `nav.canShare`, `nav.clearAppBadge`, `nav.clipboard`, `nav.connection`, `nav.cookieEnabled`, `nav.credentials`, `nav.deviceMemory`, `nav.devicePosture`, `nav.doNotTrack`, `nav.geolocation`, `nav.getBattery`, `nav.getInstalledRelatedApps`, `nav.gpu`, `nav.hid`, `nav.ink`, `nav.keyboard`, `nav.language`, `nav.languages`, `nav.locks`, `nav.login`, `nav.managed`, `nav.maxTouchPoints`, `nav.mediaCapabilities`, `nav.mediaDevices`, `nav.mediaSession`, `nav.onLine`, `nav.pdfViewerEnabled`, `nav.permissions`, `nav.platform`, `nav.presentation`, `nav.product`, `nav.productSub`, `nav.protectedAudience`, `nav.requestMIDIAccess`, `nav.scheduling`, `nav.sendBeacon`, `nav.serial`, `nav.serviceWorker`, `nav.setAppBadge`, `nav.share`, `nav.storage`, `nav.usb`, `nav.userActivation`, `nav.vendor`, `nav.vendorSub`, `nav.vibrate`, `nav.virtualKeyboard`, `nav.wakeLock`, `nav.webdriver`, `nav.windowControlsOverlay`, `nav.xr`, `navConnection.effectiveType`, `navConnection.saveData`, `navProto`, `perfMem.jsHeapSizeLimit`, `perms.accelerometer`, `perms.background-sync`, `perms.camera`, `perms.clipboard-read`, `perms.clipboard-write`, `perms.geolocation`, `perms.gyroscope`, `perms.local-fonts`, `perms.magnetometer`, `perms.microphone`, `perms.midi`, `perms.notifications`, `perms.payment-handler`, `perms.persistent-storage`, `perms.screen-wake-lock`, `perms.storage-access`, `perms.window-management`, `protoCounts.CSSStyleDeclaration`, `protoCounts.Document`, `protoCounts.Element`, `protoCounts.HTMLElement`, `protoCounts.Window`, `protoCounts.cssProps`, `screen.availLeft`, `screen.availTop`, `screen.colorDepth`, `screen.isExtended`, `screen.pixelDepth`, `screenOrientation.angle`, `screenOrientation.type`, `storage.persisted`, `storage.quotaGiB`, `storage.usage`, `ua`, `uad.brands`, `uad.mobile`, `uad.platform`, `uadHigh.architecture`, `uadHigh.bitness`, `uadHigh.brands`, `uadHigh.formFactors`, `uadHigh.fullVersionList`, `uadHigh.mobile`, `uadHigh.model`, `uadHigh.platform`, `uadHigh.platformVersion`, `uadHigh.uaFullVersion`, `uadHigh.wow64`, `win.DeviceMotionEvent`, `win.Notification`, `win.PaymentRequest`, `win.SharedWorker`, `win.chrome`, `win.external`, `win.getScreenDetails`, `win.launchQueue`, `win.ondeviceorientation`, `win.ontouchstart`, `win.openDatabase`, `win.outerMinusInnerH`, `win.outerMinusInnerW`, `win.queryLocalFonts`, `win.screenX`, `win.screenY`, `win.showOpenFilePicker`, `win.showSaveFilePicker`, `win.speechSynthesis`, `win.styleMedia`, `windowKeys`, `windowNames`

## detectors / headed
46 differing rows: 35 expected, 3 unexpected, 8 volatile

| row | control | fork | label | reason |
|---|---|---|---|---|
| det.creepjs.....avail | "1280 x 984" | "1920 x 1152" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs....screen | "1280 x 1024" | "1920 x 1200" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.0% headless | "<absent>" | "52defe05" | expected | SP2 and the identity UA move CreepJS's headless scores |
| det.creepjs.33% headless | "a427e0b8" | "<absent>" | expected | SP2 and the identity UA move CreepJS's headless scores |
| det.creepjs.@media | "8de3ca33" | "0bb692ca" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.FP ID | "a2aa5927b68b95e4ad9c8ddc183ab65147fd8f848f4ca913e43e602c99cb5b46" | "8bb2dfd9fdfca64ab6bc48c19bdfd050a79c1ab3408a099d4c0b857dcf0e64b1" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.Fuzzy | "cb3ab5443525861d1ce949f74de0cda8ffb8098f8aee38fe1011000000000000" | "2b95b544392586111c1949303de0c281ff57d9f369be00feb011000000000000" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.candidate | "799532475 1 udp 2113937151 61abcbde-a3bb-475a-92ec-730aa3147398.local 64987 ... | "1191324717 1 udp 2113937151 bffc38c6-5cac-457f-b791-7c67782c4567.local 49356... | volatile | a WebRTC candidate: per-load id and port |
| det.creepjs.copy | "f5d91537" | "6cc8f515" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.cores | "16, ram: 32" | "12, ram: 8" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.data | "501135c7" | "13a58c32" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.freq | "164539.10744857788" | "164539.18825531006" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.images | "e6e66db2" | "54f724f7" | expected | the identity's canvas:seed |
| det.creepjs.lang | "en-US, en (en-US)" | "en-US (en-US)" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.lang (1) | "<absent>" | "en-US" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.lang (18) | "d185f3e1" | "<absent>" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.level | "100%" | "75%" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.matchMedia | "8de3ca33" | "0bb692ca" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.remote (0) | "<absent>" | "unsupported" | unexpected |  |
| det.creepjs.remote (19) | "036f6dce" | "<absent>" | unexpected |  |
| det.creepjs.rtt | "100, downlink: 1.7" | "100, downlink: 1.5" | volatile | a network estimate |
| det.creepjs.screen query | "1280 x 1024" | "1920 x 1200" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.stack | "17765" | "17799" | volatile | stack depth, differed between two stock loads |
| det.creepjs.sum | "124.04347776696522" | "124.04199268739467" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.time | "502.59992877283" | "502.5976674908088" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.trap | "0.3009163141795771" | "0.5162407991191533" | volatile | a random value per load |
| det.creepjs.type & base ip | "799532475" | "1191324717" | volatile | a WebRTC candidate hash, per load |
| det.dbi_bot.hasWebdriverInFrameTrue | true | false | expected | SP2: the fork hides automation; stock under the same driver reports true |
| det.dbi_bot.hasWebdriverTrue | true | false | expected | SP2: the fork hides automation; stock under the same driver reports true |
| det.dbi_bot.isBot | true | false | expected | SP2 hides webdriver, and the identity UA is not HeadlessChrome |
| det.detect_headless.Connection Rtt | "Connection-rtt: 150" | "Connection-rtt: 100" | volatile | a network estimate |
| det.detect_headless.Languages | "Detected 2 languages and using en-US" | "Detected 1 languages and using en-US" | expected | the identity's navigator.languages |
| det.detect_headless.Outer dimensions | "Outerheight: 964 and outerwidth: 1050" | "Outerheight: 1152 and outerwidth: 1920" | expected | the identity's window size |
| det.detect_headless.Time Elapse | "Time elapsed to close alert: 4 (< 30)" | "Time elapsed to close alert: 8 (< 30)" | volatile | the time to close an alert, a timing |
| det.detect_headless.Webdriver | "Webdriver present" | "Missing webdriver" | expected | SP2: the fork hides automation; stock under the same driver reports true |
| det.fingerprint_pro.Bot | "You are a bad bot 🤖 (type: webdriver)" | "Not detected" | expected | SP2 and the identity UA: stock reads as a webdriver / headless_chrome bot |
| det.fingerprint_pro.High-Activity Device | "Yes 🔥" | "Not detected" | volatile | the visitor's history on the service: stock's id had loaded the page all day |
| det.fingerprint_pro.Proxy Detection | "Not detected" | "Your IP is used by a residential proxy (confidence: low, ML score: 0.602)" | unexpected |  |
| det.fingerprint_pro.Suspect Score | "25" | "21" | expected | the service's sum over its signals, which the rows around it explain |
| det.fingerprint_pro.VPN | "You are using a VPN 🌐 (public VPN IP)" | "You are using a VPN 🌐 (public VPN IP, timezone mismatch)" | expected | 'timezone mismatch': the identity's zone (seed 1) against the host's IP; a client pairs the identity with a matching proxy |
| det.incolumitas.webDriver | "FAIL" | "OK" | expected | SP2: the fork hides automation; stock under the same driver reports true |
| det.incolumitas.webdriverPresent | "FAIL" | "OK" | expected | SP2: the fork hides automation; stock under the same driver reports true |
| det.rebrowser.navigatorWebdriver | "fail" | "pass" | expected | SP2: the fork hides automation; stock under the same driver reports true |
| det.sannysoft.navigator.mediaDevices | "audiooutput: id =" | "audioinput: id =" | expected | the identity's value, or a detector hash over identity values |
| det.sannysoft.screen.height | "1024" | "1200" | expected | the identity's value, or a detector hash over identity values |
| det.sannysoft.screen.width | "1280" | "1920" | expected | the identity's value, or a detector hash over identity values |

## detectors / headless
58 differing rows: 47 expected, 4 unexpected, 7 volatile

| row | control | fork | label | reason |
|---|---|---|---|---|
| det.creepjs.....avail | "800 x 600" | "1920 x 1152" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs....screen | "800 x 600" | "1920 x 1200" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.0% headless | "<absent>" | "52defe05" | expected | SP2 and the identity UA move CreepJS's headless scores |
| det.creepjs.100% headless | "44172120" | "<absent>" | expected | SP2 and the identity UA move CreepJS's headless scores |
| det.creepjs.25% like headless | "<absent>" | "fafdf9d1" | expected | SP2 and the identity UA move CreepJS's headless scores |
| det.creepjs.31% like headless | "eea7f026" | "<absent>" | expected | SP2 and the identity UA move CreepJS's headless scores |
| det.creepjs.@media | "f73d6ae7" | "0bb692ca" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.FP ID | "6a56a9d0abba4747f51c5770c406541d39fede6b0b33d4469a467b50f5acc4b5" | "8bb2dfd9fdfca64ab6bc48c19bdfd050a79c1ab3408a099d4c0b857dcf0e64b1" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.Fuzzy | "cb3ab5443d25861ebce948f74de4cda8ff96a98f8aee38fe1411000000000000" | "2b95b544392586111c1949303de0c281ff57d9f369be00feb011000000000000" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.candidate | "3769749611 1 udp 2113937151 8ad9ee94-2d37-4c06-b31b-a7a2d0dac8b0.local 54470... | "2192866330 1 udp 2113937151 2ba1526d-553f-4292-84c1-347d561afdec.local 59226... | volatile | a WebRTC candidate: per-load id and port |
| det.creepjs.copy | "f5d91537" | "6cc8f515" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.cores | "16, ram: 32" | "12, ram: 8" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.data | "501135c7" | "13a58c32" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.freq | "164539.10744857788" | "164539.18825531006" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.images | "e6e66db2" | "54f724f7" | expected | the identity's canvas:seed |
| det.creepjs.lang | "en-US, en (en-US)" | "en-US (en-US)" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.lang (1) | "<absent>" | "en-US" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.lang (18) | "d185f3e1" | "<absent>" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.level | "100%" | "75%" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.matchMedia | "f73d6ae7" | "0bb692ca" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.remote (0) | "<absent>" | "unsupported" | unexpected |  |
| det.creepjs.remote (19) | "036f6dce" | "<absent>" | unexpected |  |
| det.creepjs.rtt | "100, downlink: 1.65" | "100, downlink: 1.7" | volatile | a network estimate |
| det.creepjs.screen query | "800 x 600" | "1920 x 1200" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.stack | "17767" | "17773" | volatile | stack depth, differed between two stock loads |
| det.creepjs.sum | "124.04347776696522" | "124.04199268739467" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.time | "502.59992877283" | "502.5976674908088" | expected | the identity's value, or a detector hash over identity values |
| det.creepjs.trap | "0.841747991393612" | "0.7757308170556861" | volatile | a random value per load |
| det.creepjs.type & base ip | "3769749611" | "2192866330" | volatile | a WebRTC candidate hash, per load |
| det.dbi_bot.hasBotUserAgent | true | false | expected | stock headless says HeadlessChrome; the identity UA does not |
| det.dbi_bot.hasWebdriverInFrameTrue | true | false | expected | SP2: the fork hides automation; stock under the same driver reports true |
| det.dbi_bot.hasWebdriverTrue | true | false | expected | SP2: the fork hides automation; stock under the same driver reports true |
| det.dbi_bot.isBot | true | false | expected | SP2 hides webdriver, and the identity UA is not HeadlessChrome |
| det.detect_headless.App Version | "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Hea... | "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chr... | expected | the identity's User-Agent; stock headless says HeadlessChrome |
| det.detect_headless.Connection Rtt | "Connection-rtt: 100" | "Connection-rtt: 50" | volatile | a network estimate |
| det.detect_headless.Languages | "Detected 2 languages and using en-US" | "Detected 1 languages and using en-US" | expected | the identity's navigator.languages |
| det.detect_headless.Outer dimensions | "Outerheight: 580 and outerwidth: 780" | "Outerheight: 1152 and outerwidth: 1920" | expected | the identity's window size |
| det.detect_headless.User Agent | "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge... | "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge... | expected | the identity's User-Agent; stock headless says HeadlessChrome |
| det.detect_headless.Webdriver | "Webdriver present" | "Missing webdriver" | expected | SP2: the fork hides automation; stock under the same driver reports true |
| det.fingerprint_pro.Bot | "You are a bad bot 🤖 (type: headless_chrome)" | "Not detected" | expected | SP2 and the identity UA: stock reads as a webdriver / headless_chrome bot |
| det.fingerprint_pro.Browser Tampering | "Not detected" | "Yes 🖥️🔧" | unexpected |  |
| det.fingerprint_pro.High-Activity Device | "Yes 🔥" | "Not detected" | volatile | the visitor's history on the service: stock's id had loaded the page all day |
| det.fingerprint_pro.Proxy Detection | "Not detected" | "Your IP is used by a residential proxy (confidence: low, ML score: 0.602)" | unexpected |  |
| det.fingerprint_pro.Suspect Score | "17" | "21" | expected | the service's sum over its signals, which the rows around it explain |
| det.fingerprint_pro.VPN | "You are using a VPN 🌐 (public VPN IP)" | "You are using a VPN 🌐 (public VPN IP, timezone mismatch)" | expected | 'timezone mismatch': the identity's zone (seed 1) against the host's IP; a client pairs the identity with a matching proxy |
| det.incolumitas.CHR_MEMORY | "FAIL" | "OK" | expected | stock headless fails it (deviceMemory absent); the identity sets it |
| det.incolumitas.HEADCHR_UA | "FAIL" | "OK" | expected | stock headless says HeadlessChrome; the identity UA does not |
| det.incolumitas.userAgent | "FAIL" | "OK" | expected | stock headless says HeadlessChrome; the identity UA does not |
| det.incolumitas.webDriver | "FAIL" | "OK" | expected | SP2: the fork hides automation; stock under the same driver reports true |
| det.incolumitas.webdriverPresent | "FAIL" | "OK" | expected | SP2: the fork hides automation; stock under the same driver reports true |
| det.rebrowser.navigatorWebdriver | "fail" | "pass" | expected | SP2: the fork hides automation; stock under the same driver reports true |
| det.sannysoft.CHR_MEMORY | "FAIL \| " | "ok \| " | expected | stock headless fails it (deviceMemory absent); the identity sets it |
| det.sannysoft.HEADCHR_UA | "FAIL \| " | "ok \| " | expected | stock headless says HeadlessChrome; the identity UA does not |
| det.sannysoft.navigator.mediaDevices | "audiooutput: id =" | "audioinput: id =" | expected | the identity's value, or a detector hash over identity values |
| det.sannysoft.navigator.userAgent | "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge... | "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge... | expected | the identity's value, or a detector hash over identity values |
| det.sannysoft.screen.height | "600" | "1200" | expected | the identity's value, or a detector hash over identity values |
| det.sannysoft.screen.width | "800" | "1920" | expected | the identity's value, or a detector hash over identity values |
| det.whoer.blocked | "cloudflare challenge" | "no" | expected | Cloudflare challenges stock's HeadlessChrome UA; the identity UA is not headless |

## detector text amiunique / headed
control only (9):
- `"And 63 others"`
- `"Arial Narrow"`
- `"FAQ ?"`
- `"Fingerprint"`
- `"History"`
- `"Statistics"`
- `"UTC+07:00"`
- `"en-US,en"`
- `"level : 1"`
fork only (25):
- `"1 audioinput"`
- `"1 videoinput"`
- `"2026 — AmIUnique.org"`
- `"40 avenue Halley, 59650 Villeneuve d’Ascq, France"`
- `"About"`
- `"Address"`
- `"Am I Unique ?"`
- `"And 60 others"`
- `"BLOG"`
- `"Blog"`
- `"CONTACT US"`
- `"Calibri Light"`
- `"Email"`
- `"GLOBAL STATISTICS"`
- `"Join Us"`
- `"MY EXTENSION"`
- `"MY FINGERPRINT"`
- `"QUICK LINKS"`
- `"SURVEY"`
- `"This website aims at studying the diversity of browser fingerprints and prov...`
- `"USEFUL LINKS"`
- `"UTC-05:00"`
- `"browser-fingerprinting@univ-lille.fr"`
- `"en-US"`
- `"level : 0.75"`

## detector text amiunique / headless
control only (11):
- `"And 63 others"`
- `"Arial Narrow"`
- `"FAQ ?"`
- `"Fingerprint"`
- `"History"`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Statistics"`
- `"UTC+07:00"`
- `"en-US,en"`
- `"level : 1"`
fork only (27):
- `"1 audioinput"`
- `"1 videoinput"`
- `"2026 — AmIUnique.org"`
- `"40 avenue Halley, 59650 Villeneuve d’Ascq, France"`
- `"About"`
- `"Address"`
- `"Am I Unique ?"`
- `"And 60 others"`
- `"BLOG"`
- `"Blog"`
- `"CONTACT US"`
- `"Calibri Light"`
- `"Email"`
- `"GLOBAL STATISTICS"`
- `"Join Us"`
- `"MY EXTENSION"`
- `"MY FINGERPRINT"`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"QUICK LINKS"`
- `"SURVEY"`
- `"This website aims at studying the diversity of browser fingerprints and prov...`
- `"USEFUL LINKS"`
- `"UTC-05:00"`
- `"browser-fingerprinting@univ-lille.fr"`
- `"en-US"`
- `"level : 0.75"`

## detector text browserleaks_canvas / headed
control only (26):
- `"Android 10\t2/111\tMicrosoft Edge\t16/111\tGoogle Nexus 5\t1/111"`
- `"Android 15\t1/111\tChromium GOST\t7/111\tSmartphone\t1/111"`
- `"Blink 140\t9/111\tDuckDuckGo Privacy Browser\t7/111"`
- `"Blink 141\t8/111\tViber\t6/111"`
- `"Blink 142\t9/111\tBrowsers by Version\tLinux amd64\t1/111"`
- `"Blink 143\t9/111\tCCleaner\t4/111\tLinux armv81\t3/111"`
- `"Blink 144\t7/111\tChrome 142\t4/111"`
- `"Blink 145\t8/111\tChrome 140\t6/111"`
- `"Blink 146\t10/111\tAvast Secure Browser\t5/111\tLinux aarch64\t3/111"`
- `"Blink 148\t8/111\tChrome 146\t6/111"`
- `"Chrome 139\t4/111"`
- `"Chrome 141\t4/111"`
- `"Engines\tViber\t6/111\tWin32\t104/111"`
- `"File Size\t5597 bytes"`
- `"GNU/Linux\t1/111\tDuckDuckGo Privacy Browser\t7/111\tTablet\t1/111"`
- `"IDAT\t1414\tC7879BE3\tPNG image data"`
- `"IDAT\t4096\tFAF91E1D\tPNG image data"`
- `"IDAT\t6\t574F6833\tPNG image data"`
- `"It's very likely that your web browser is Chrome and your operating system i...`
- `"Number of Colors\t222"`
- `"Operating Systems\tBrowsers\tDevices"`
- `"Signature\t1C6ABD493317125AB9C8F2069A29E126"`
- `"Signature Stats"`
- `"Uniqueness\t99.95% (111 of 258037 user agents have the same signature)"`
- `"Windows\t1/111\tSberBrowser\t7/111\tPlatforms"`
- `"Windows 10\t106/111\tChrome\t51/111\tDesktop\t108/111"`
fork only (7):
- `"File Size\t5674 bytes"`
- `"IDAT\t1491\t079981BB\tPNG image data"`
- `"IDAT\t4096\t930BB3FC\tPNG image data"`
- `"IDAT\t6\t45731CFC\tPNG image data"`
- `"Number of Colors\t219"`
- `"Signature\tA7918A5C53FBB369AE180FBAF353B505"`
- `"Uniqueness\t100% (The signature is unique to our database)"`

## detector text browserleaks_canvas / headless
control only (26):
- `"Android 10\t2/111\tMicrosoft Edge\t16/111\tGoogle Nexus 5\t1/111"`
- `"Android 15\t1/111\tChromium GOST\t7/111\tSmartphone\t1/111"`
- `"Blink 140\t9/111\tDuckDuckGo Privacy Browser\t7/111"`
- `"Blink 141\t8/111\tViber\t6/111"`
- `"Blink 142\t9/111\tBrowsers by Version\tLinux amd64\t1/111"`
- `"Blink 143\t9/111\tCCleaner\t4/111\tLinux armv81\t3/111"`
- `"Blink 144\t7/111\tChrome 142\t4/111"`
- `"Blink 145\t8/111\tChrome 140\t6/111"`
- `"Blink 146\t10/111\tAvast Secure Browser\t5/111\tLinux aarch64\t3/111"`
- `"Blink 148\t8/111\tChrome 146\t6/111"`
- `"Chrome 139\t4/111"`
- `"Chrome 141\t4/111"`
- `"Engines\tViber\t6/111\tWin32\t104/111"`
- `"File Size\t5597 bytes"`
- `"GNU/Linux\t1/111\tDuckDuckGo Privacy Browser\t7/111\tTablet\t1/111"`
- `"IDAT\t1414\tC7879BE3\tPNG image data"`
- `"IDAT\t4096\tFAF91E1D\tPNG image data"`
- `"IDAT\t6\t574F6833\tPNG image data"`
- `"It's very likely that your web browser is Chrome and your operating system i...`
- `"Number of Colors\t222"`
- `"Operating Systems\tBrowsers\tDevices"`
- `"Signature\t1C6ABD493317125AB9C8F2069A29E126"`
- `"Signature Stats"`
- `"Uniqueness\t99.95% (111 of 258037 user agents have the same signature)"`
- `"Windows\t1/111\tSberBrowser\t7/111\tPlatforms"`
- `"Windows 10\t106/111\tChrome\t51/111\tDesktop\t108/111"`
fork only (7):
- `"File Size\t5674 bytes"`
- `"IDAT\t1491\t079981BB\tPNG image data"`
- `"IDAT\t4096\t930BB3FC\tPNG image data"`
- `"IDAT\t6\t45731CFC\tPNG image data"`
- `"Number of Colors\t219"`
- `"Signature\tA7918A5C53FBB369AE180FBAF353B505"`
- `"Uniqueness\t100% (The signature is unique to our database)"`

## detector text browserleaks_client_hints / headed
control only (4):
- `"RTT\t50"`
- `"Sec-CH-Viewport-Height\t869"`
- `"Sec-CH-Viewport-Width\t1034"`
- `"Viewport-Width\t1034"`
fork only (4):
- `"RTT\t200"`
- `"Sec-CH-Viewport-Height\t949"`
- `"Sec-CH-Viewport-Width\t1284"`
- `"Viewport-Width\t1284"`

## detector text browserleaks_client_hints / headless
control only (5):
- `"HTTP User-Agent\tMozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3...`
- `"RTT\t50"`
- `"Sec-CH-Viewport-Height\t485"`
- `"Sec-CH-Viewport-Width\t764"`
- `"Viewport-Width\t764"`
fork only (5):
- `"HTTP User-Agent\tMozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3...`
- `"RTT\t250"`
- `"Sec-CH-Viewport-Height\t1057"`
- `"Sec-CH-Viewport-Width\t1904"`
- `"Viewport-Width\t1904"`

## detector text browserleaks_fonts / headed
control only (2):
- `"1460A0F298CCEAFCBF6B0D45331C5610"`
- `"Report\t111 fonts and 78 unique metrics found"`
fork only (2):
- `"6A8431C978511DA48F16F4134D9403D2"`
- `"Report\t99 fonts and 78 unique metrics found"`

## detector text browserleaks_fonts / headless
control only (2):
- `"1460A0F298CCEAFCBF6B0D45331C5610"`
- `"Report\t111 fonts and 78 unique metrics found"`
fork only (2):
- `"6A8431C978511DA48F16F4134D9403D2"`
- `"Report\t99 fonts and 78 unique metrics found"`

## detector text browserleaks_javascript / headed
control only (28):
- `"1280×1024 5:4 24-bit TrueColor (viewport: 1019×869)"`
- `"Google Bahasa Indonesia"`
- `"Google Deutsch"`
- `"Google Nederlands"`
- `"Google UK English Female"`
- `"Google UK English Male"`
- `"Google US English"`
- `"Google español"`
- `"Google español de Estados Unidos"`
- `"Google français"`
- `"Google italiano"`
- `"Google polski"`
- `"Google português do Brasil"`
- `"Google русский"`
- `"Google हिन्दी"`
- `"Google 國語（臺灣）"`
- `"Google 日本語"`
- `"Google 한국의"`
- `"Google 普通话（中国大陆）"`
- `"Google 粤語（香港）"`
- `"Microsoft David - English (United States)"`
- `"Speech Voices"`
- `"deviceMemory\t32"`
- `"hardwareConcurrency\t16"`
- `"languages\t[\"en-US\",\"en\"]"`
- `"level\t1"`
- `"timeZone\tAsia/Saigon"`
- `"webdriver\ttrue"`
fork only (8):
- `"1920×1200 16:10 24-bit TrueColor (viewport: 1269×949)"`
- `"Speech Voices\tMicrosoft David - English (United States)"`
- `"deviceMemory\t8"`
- `"hardwareConcurrency\t12"`
- `"languages\t[\"en-US\"]"`
- `"level\t0.75"`
- `"timeZone\tAmerica/Chicago"`
- `"webdriver\tfalse"`

## detector text browserleaks_javascript / headless
control only (30):
- `"800×600 (Letterboxing) 24-bit TrueColor (viewport: 749×485)"`
- `"Google Bahasa Indonesia"`
- `"Google Deutsch"`
- `"Google Nederlands"`
- `"Google UK English Female"`
- `"Google UK English Male"`
- `"Google US English"`
- `"Google español"`
- `"Google español de Estados Unidos"`
- `"Google français"`
- `"Google italiano"`
- `"Google polski"`
- `"Google português do Brasil"`
- `"Google русский"`
- `"Google हिन्दी"`
- `"Google 國語（臺灣）"`
- `"Google 日本語"`
- `"Google 한국의"`
- `"Google 普通话（中国大陆）"`
- `"Google 粤語（香港）"`
- `"Microsoft David - English (United States)"`
- `"Speech Voices"`
- `"appVersion\t5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, lik...`
- `"deviceMemory\t32"`
- `"hardwareConcurrency\t16"`
- `"languages\t[\"en-US\",\"en\"]"`
- `"level\t1"`
- `"timeZone\tAsia/Saigon"`
- `"userAgent\tMozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHT...`
- `"webdriver\ttrue"`
fork only (10):
- `"1920×1200 16:10 24-bit TrueColor (viewport: 1889×1057)"`
- `"Speech Voices\tMicrosoft David - English (United States)"`
- `"appVersion\t5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, lik...`
- `"deviceMemory\t8"`
- `"hardwareConcurrency\t12"`
- `"languages\t[\"en-US\"]"`
- `"level\t0.75"`
- `"timeZone\tAmerica/Chicago"`
- `"userAgent\tMozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHT...`
- `"webdriver\tfalse"`

## detector text browserleaks_tls / headed
control only (0):
fork only (0):

## detector text browserleaks_tls / headless
control only (1):
- `"HTTP User-Agent\tMozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3...`
fork only (2):
- `"Cipher Suites"`
- `"HTTP User-Agent\tMozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3...`

## detector text browserleaks_webgl / headed
control only (1):
- `"WebGL Image Hash\t62E11136104BD996D8ADA7B925E51D65"`
fork only (1):
- `"WebGL Image Hash\t69A94B31FEB05D05FF2980D8F1C58972"`

## detector text browserleaks_webgl / headless
control only (2):
- `"HTTP User-Agent\tMozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3...`
- `"WebGL Image Hash\t62E11136104BD996D8ADA7B925E51D65"`
fork only (2):
- `"HTTP User-Agent\tMozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3...`
- `"WebGL Image Hash\t69A94B31FEB05D05FF2980D8F1C58972"`

## detector text browserleaks_webrtc / headed
control only (1):
- `"Media Devices\t    kind: audiooutput"`
fork only (9):
- `"Media Devices\t    kind: audioinput"`
- `"deviceId: n/a"`
- `"deviceId: n/a"`
- `"groupId: n/a"`
- `"groupId: n/a"`
- `"kind: audiooutput"`
- `"kind: videoinput"`
- `"label: n/a"`
- `"label: n/a"`

## detector text browserleaks_webrtc / headless
control only (1):
- `"Media Devices\t    kind: audiooutput"`
fork only (9):
- `"Media Devices\t    kind: audioinput"`
- `"deviceId: n/a"`
- `"deviceId: n/a"`
- `"groupId: n/a"`
- `"groupId: n/a"`
- `"kind: audiooutput"`
- `"kind: videoinput"`
- `"label: n/a"`
- `"label: n/a"`

## detector text browserscan / headed
control only (12):
- `"1280×1024"`
- `"1280×984"`
- `"Anti-detection browser"`
- `"Asia/Saigon"`
- `"Bot Control"`
- `"Fonts listShow all fonts(132)"`
- `"Web browser testing"`
- `"What is a robot?"`
- `"Yes"`
- `"YesDetection"`
- `"Your browser environment appears to be controlled by a robot."`
- `"en-US,en"`
fork only (8):
- `"1920×1152"`
- `"1920×1200"`
- `"America/Chicago"`
- `"Fonts listShow all fonts(95)"`
- `"No"`
- `"NoDetection"`
- `"WebGL exception"`
- `"en-US"`

## detector text browserscan / headless
control only (14):
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
fork only (16):
- `"1920×1152"`
- `"1920×1200"`
- `"America/Chicago"`
- `"Anti-detection browser"`
- `"Chrome"`
- `"Chrome 154.0.8037.93 Detection"`
- `"EN"`
- `"Fonts listShow all fonts(95)"`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"No"`
- `"NoDetection"`
- `"Web browser testing"`
- `"WebGL exception"`
- `"blog"`
- `"en-US"`

## detector text creepjs / headed
control only (39):
- `"....avail: 1280 x 984"`
- `"...screen: 1280 x 1024"`
- `"33% headless: a427e0b8"`
- `"@media: 8de3ca33"`
- `"Asia, Saigon"`
- `"Asia/Saigon (-420)"`
- `"Audiod0c60a78"`
- `"CSS Media Queriese1c4f27c"`
- `"Canvas 2d019e195f"`
- `"FP ID: a2aa5927b68b95e4ad9c8ddc183ab65147fd8f848f4ca913e43e602c99cb5b46"`
- `"Fuzzy: cb3ab5443525861d1ce949f74de0cda8ffb8098f8aee38fe1011000000000000"`
- `"Headless34760712"`
- `"Indochina Time"`
- `"Intl4b9c0772"`
- `"July at Indochina Time"`
- `"Navigatore8cbab8b"`
- `"Screend8485e84"`
- `"Speech77bd6c70"`
- `"Timezone1d1c75e3"`
- `"WebGL423723fb"`
- `"Workera005e692"`
- `"audio"`
- `"copy:f5d91537"`
- `"cores: 16, ram: 32"`
- `"cores: 16, ram: 32, touch: 0, bluetooth"`
- `"data: 501135c7"`
- `"data:f5d91537"`
- `"devices (1):"`
- `"freq: 164539.10744857788"`
- `"images:e6e66db2"`
- `"lang (18): d185f3e1"`
- `"lang: en-US, en (en-US)"`
- `"level: 100%"`
- `"matchMedia: 8de3ca33"`
- `"remote (19): 036f6dce"`
- `"screen query: 1280 x 1024"`
- `"sum: 124.04347776696522"`
- `"time: 502.59992877283"`
- `"😀🤵‍♂️⚧...✌☝❄"`
fork only (39):
- `"....avail: 1920 x 1152"`
- `"...screen: 1920 x 1200"`
- `"0% headless: 52defe05"`
- `"@media: 0bb692ca"`
- `"America, Chicago"`
- `"America/Chicago (300)"`
- `"Audio836bc7c7"`
- `"CSS Media Queriescda12a5d"`
- `"Canvas 2d065d2fe3"`
- `"Central Daylight Time"`
- `"FP ID: 8bb2dfd9fdfca64ab6bc48c19bdfd050a79c1ab3408a099d4c0b857dcf0e64b1"`
- `"Fuzzy: 2b95b544392586111c1949303de0c281ff57d9f369be00feb011000000000000"`
- `"Headlessc84e0876"`
- `"Intl5c90eef3"`
- `"July at Central Daylight Time"`
- `"Navigatorfa8ecbea"`
- `"Screencb176f35"`
- `"Speechd8216ffd"`
- `"Timezone432a225a"`
- `"WebGL57b0f004"`
- `"Worker99ad3822"`
- `"copy:6cc8f515"`
- `"cores: 12, ram: 8"`
- `"cores: 12, ram: 8, touch: 0, bluetooth"`
- `"data: 13a58c32"`
- `"data:6cc8f515"`
- `"devices (3):"`
- `"freq: 164539.18825531006"`
- `"images:54f724f7"`
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
control only (43):
- `"....avail: 800 x 600"`
- `"...screen: 800 x 600"`
- `"100% headless: 44172120"`
- `"31% like headless: eea7f026"`
- `"5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Hea...`
- `"@media: f73d6ae7"`
- `"Asia, Saigon"`
- `"Asia/Saigon (-420)"`
- `"Audiod0c60a78"`
- `"CSS Media Queries1c00518e"`
- `"Canvas 2d019e195f"`
- `"FP ID: 6a56a9d0abba4747f51c5770c406541d39fede6b0b33d4469a467b50f5acc4b5"`
- `"Fuzzy: cb3ab5443d25861ebce948f74de4cda8ff96a98f8aee38fe1411000000000000"`
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
- `"WebGL423723fb"`
- `"Workerca66798d"`
- `"audio"`
- `"copy:f5d91537"`
- `"cores: 16, ram: 32"`
- `"cores: 16, ram: 32, touch: 0, bluetooth"`
- `"data: 501135c7"`
- `"data:f5d91537"`
- `"devices (1):"`
- `"freq: 164539.10744857788"`
- `"images:e6e66db2"`
- `"lang (18): d185f3e1"`
- `"lang: en-US, en (en-US)"`
- `"level: 100%"`
- `"matchMedia: f73d6ae7"`
- `"remote (19): 036f6dce"`
- `"screen query: 800 x 600"`
- `"sum: 124.04347776696522"`
- `"time: 502.59992877283"`
- `"😀🤵‍♂️⚧...✌☝❄"`
fork only (45):
- `"....avail: 1920 x 1152"`
- `"...screen: 1920 x 1200"`
- `"0% headless: 52defe05"`
- `"25% like headless: fafdf9d1"`
- `"5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chr...`
- `"@media: 0bb692ca"`
- `"America, Chicago"`
- `"America/Chicago (300)"`
- `"Audio836bc7c7"`
- `"CSS Media Queriescda12a5d"`
- `"Canvas 2d065d2fe3"`
- `"Central Daylight Time"`
- `"FP ID: 8bb2dfd9fdfca64ab6bc48c19bdfd050a79c1ab3408a099d4c0b857dcf0e64b1"`
- `"Fuzzy: 2b95b544392586111c1949303de0c281ff57d9f369be00feb011000000000000"`
- `"Headlessc84e0876"`
- `"Intl5c90eef3"`
- `"July at Central Daylight Time"`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Navigatorfa8ecbea"`
- `"Screencb176f35"`
- `"Speechd8216ffd"`
- `"Timezone432a225a"`
- `"WebGL57b0f004"`
- `"Worker99ad3822"`
- `"copy:6cc8f515"`
- `"cores: 12, ram: 8"`
- `"cores: 12, ram: 8, touch: 0, bluetooth"`
- `"data: 13a58c32"`
- `"data:6cc8f515"`
- `"devices (3):"`
- `"freq: 164539.18825531006"`
- `"images:54f724f7"`
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

## detector text dbi_bot / headed
control only (5):
- `"\"hasWebdriverInFrameTrue\": true,"`
- `"\"hasWebdriverTrue\": true,"`
- `"\"isBot\": true,"`
- `"You are a bot!"`
- `"❌"`
fork only (5):
- `"\"hasWebdriverInFrameTrue\": false,"`
- `"\"hasWebdriverTrue\": false,"`
- `"\"isBot\": false,"`
- `"You are human!"`
- `"✅"`

## detector text dbi_bot / headless
control only (6):
- `"\"hasBotUserAgent\": true,"`
- `"\"hasWebdriverInFrameTrue\": true,"`
- `"\"hasWebdriverTrue\": true,"`
- `"\"isBot\": true,"`
- `"You are a bot!"`
- `"❌"`
fork only (14):
- `"\"hasBotUserAgent\": false,"`
- `"\"hasWebdriverInFrameTrue\": false,"`
- `"\"hasWebdriverTrue\": false,"`
- `"\"isBot\": false,"`
- `"APIs"`
- `"Blog"`
- `"Data"`
- `"Login"`
- `"My Device"`
- `"Pricing"`
- `"Proxy Detection Database"`
- `"Search proxy IP"`
- `"You are human!"`
- `"✅"`

## detector text detect_headless / headed
control only (3):
- `"Languages\tDetected 2 languages and using en-US"`
- `"Outer dimensions\tOuterheight: 964 and outerwidth: 1050"`
- `"Webdriver\tWebdriver present"`
fork only (3):
- `"Languages\tDetected 1 languages and using en-US"`
- `"Outer dimensions\tOuterheight: 1152 and outerwidth: 1920"`
- `"Webdriver\tMissing webdriver"`

## detector text detect_headless / headless
control only (5):
- `"App Version\t5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, li...`
- `"Languages\tDetected 2 languages and using en-US"`
- `"Outer dimensions\tOuterheight: 580 and outerwidth: 780"`
- `"User Agent\tMozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KH...`
- `"Webdriver\tWebdriver present"`
fork only (5):
- `"App Version\t5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, li...`
- `"Languages\tDetected 1 languages and using en-US"`
- `"Outer dimensions\tOuterheight: 1152 and outerwidth: 1920"`
- `"User Agent\tMozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KH...`
- `"Webdriver\tMissing webdriver"`

## detector text fingerprint_pro / headed
control only (39):
- `"0: 1280"`
- `"1: \"Franklin Gothic\""`
- `"1: 1024"`
- `"2: \"MS UI Gothic\""`
- `"3: \"Marlett\""`
- `"4: \"Segoe UI Light\""`
- `"Chrome 154.0.0"`
- `"Yes 🔥"`
- `"You are a bad bot 🤖 (type: webdriver)"`
- `"You are using a VPN 🌐 (public VPN IP)"`
- `"audio: 124.04347776696522"`
- `"battery_level: 100"`
- `"bot: \"bad\""`
- `"bot_info: {"`
- `"bot_type: \"webdriver\""`
- `"browser_full_version: \"154.0.0\""`
- `"browser_major_version: \"154\""`
- `"browser_name: \"Chrome\""`
- `"category: \"browser_automation\""`
- `"confidence: \"medium\""`
- `"device_memory: 32"`
- `"font_hash: \"50a1ee1ae0a63656844e7e05dd1c6f17\""`
- `"geometry: \"201c44790d32cf278a5e1351d46e84bf\""`
- `"hardware_concurrency: 16"`
- `"high_activity_device: true"`
- `"identity: \"unknown\""`
- `"name: \"WebDriver\""`
- `"po0I0bPAqE1vRsejafQi"`
- `"provider: \"webdriver\""`
- `"proxy: false"`
- `"proxy_confidence: \"high\""`
- `"rare_device_percentile_bucket: \"<p95\""`
- `"suspect_score: 25"`
- `"suspect_score: 25"`
- `"text: \"5ce126082d85b80770bfb99467f39671\""`
- `"timezone: \"Asia/Saigon\""`
- `"timezone_mismatch: false"`
- `"timezone_offset: \"+07:00\""`
- `"vpn_origin_timezone: \"Asia/Saigon\""`
fork only (33):
- `"0: 1920"`
- `"1: \"MS UI Gothic\""`
- `"1: 1200"`
- `"2: \"Marlett\""`
- `"3: \"Segoe UI Light\""`
- `"Chromium-Based Browser Not Available"`
- `"HGR8ev97jdUiW30alnav"`
- `"Not detected"`
- `"You are using a VPN 🌐 (public VPN IP, timezone mismatch)"`
- `"Your IP is used by a residential proxy (confidence: low, ML score: 0.602)"`
- `"audio: 124.04199268739467"`
- `"battery_level: 75"`
- `"bot: \"not_detected\""`
- `"browser_full_version: \"Not Available\""`
- `"browser_major_version: \"Not Available\""`
- `"browser_name: \"Chromium-Based Browser\""`
- `"device_memory: 8"`
- `"font_hash: \"6c3d8f4c6de6e48b788d32ce0880d176\""`
- `"geometry: \"46cf089d2f930fceb91adf7103f459ca\""`
- `"hardware_concurrency: 12"`
- `"high_activity_device: false"`
- `"proxy: true"`
- `"proxy_confidence: \"low\""`
- `"proxy_details: {"`
- `"proxy_type: \"residential\""`
- `"rare_device_percentile_bucket: \"p95-p99\""`
- `"suspect_score: 21"`
- `"suspect_score: 21"`
- `"text: \"6b256dd7040c134d6291e33da7cd1ca2\""`
- `"timezone: \"America/Chicago\""`
- `"timezone_mismatch: true"`
- `"timezone_offset: \"-05:00\""`
- `"vpn_origin_timezone: \"America/Chicago\""`

## detector text fingerprint_pro / headless
control only (43):
- `"0: 800"`
- `"1574XcKrqSk4YUqD0Iqu"`
- `"1: \"Franklin Gothic\""`
- `"1: 600"`
- `"2: \"MS UI Gothic\""`
- `"3: \"Marlett\""`
- `"4: \"Segoe UI Light\""`
- `"HeadlessChrome 154.0.0"`
- `"Yes 🔥"`
- `"You are a bad bot 🤖 (type: headless_chrome)"`
- `"You are using a VPN 🌐 (public VPN IP)"`
- `"anti_detect_browser: false"`
- `"audio: 124.04347776696522"`
- `"battery_level: 100"`
- `"bot: \"bad\""`
- `"bot_info: {"`
- `"bot_type: \"headless_chrome\""`
- `"browser_full_version: \"154.0.0\""`
- `"browser_major_version: \"154\""`
- `"browser_name: \"HeadlessChrome\""`
- `"category: \"browser_automation\""`
- `"confidence: \"medium\""`
- `"device_memory: 32"`
- `"font_hash: \"50a1ee1ae0a63656844e7e05dd1c6f17\""`
- `"geometry: \"201c44790d32cf278a5e1351d46e84bf\""`
- `"hardware_concurrency: 16"`
- `"high_activity_device: true"`
- `"identity: \"unknown\""`
- `"name: \"ChromeHeadless\""`
- `"provider: \"chromium/chromium\""`
- `"proxy: false"`
- `"proxy_confidence: \"high\""`
- `"rare_device_percentile_bucket: \"<p95\""`
- `"suspect_score: 17"`
- `"suspect_score: 17"`
- `"tampering: false"`
- `"tampering_confidence: \"high\""`
- `"text: \"5ce126082d85b80770bfb99467f39671\""`
- `"timezone: \"Asia/Saigon\""`
- `"timezone_mismatch: false"`
- `"timezone_offset: \"+07:00\""`
- `"user_agent: \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (...`
- `"vpn_origin_timezone: \"Asia/Saigon\""`
fork only (42):
- `"0: 1920"`
- `"1: \"MS UI Gothic\""`
- `"1: 1200"`
- `"2: \"Marlett\""`
- `"3: \"Segoe UI Light\""`
- `"Chromium-Based Browser Not Available"`
- `"Contact sales"`
- `"Get started"`
- `"HGR8ev97jdUiW30alnav"`
- `"Home"`
- `"Playground"`
- `"Use cases"`
- `"Yes 🖥️🔧"`
- `"You are using a VPN 🌐 (public VPN IP, timezone mismatch)"`
- `"Your IP is used by a residential proxy (confidence: low, ML score: 0.602)"`
- `"anti_detect_browser: true"`
- `"audio: 124.04199268739467"`
- `"battery_level: 75"`
- `"bot: \"not_detected\""`
- `"browser_full_version: \"Not Available\""`
- `"browser_major_version: \"Not Available\""`
- `"browser_name: \"Chromium-Based Browser\""`
- `"device_memory: 8"`
- `"font_hash: \"6c3d8f4c6de6e48b788d32ce0880d176\""`
- `"geometry: \"46cf089d2f930fceb91adf7103f459ca\""`
- `"hardware_concurrency: 12"`
- `"high_activity_device: false"`
- `"proxy: true"`
- `"proxy_confidence: \"low\""`
- `"proxy_details: {"`
- `"proxy_type: \"residential\""`
- `"rare_device_percentile_bucket: \"p95-p99\""`
- `"suspect_score: 21"`
- `"suspect_score: 21"`
- `"tampering: true"`
- `"tampering_confidence: \"medium\""`
- `"text: \"6b256dd7040c134d6291e33da7cd1ca2\""`
- `"timezone: \"America/Chicago\""`
- `"timezone_mismatch: true"`
- `"timezone_offset: \"-05:00\""`
- `"user_agent: \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (...`
- `"vpn_origin_timezone: \"America/Chicago\""`

## detector text fingerprint_scan / headed
control only (14):
- `"Asia/Saigon"`
- `"Bot score 100/100"`
- `"Browser: HIGH"`
- `"Network / proxy: MEDIUM"`
- `"Summarizer Availability"`
- `"Summarizer Language Availability"`
- `"[\"Google Deutsch (de-DE)\",\"Google US English (en-US)\",\"Google UK Englis...`
- `"[\"en-US\",\"en\"]"`
- `"downloadable"`
- `"downloadable"`
- `"en"`
- `"en"`
- `"supported"`
- `"webdriver"`
fork only (8):
- `"America/Chicago"`
- `"Bot score 20/100"`
- `"Browser: MEDIUM"`
- `"Network / proxy: LOW"`
- `"NotSupportedError"`
- `"TIMEOUT"`
- `"[\"Microsoft David - English (United States) (en-US)\",\"Microsoft Mark - En...`
- `"[\"en-US\"]"`

## detector text fingerprint_scan / headless
control only (18):
- `"Asia/Saigon"`
- `"Bot score 100/100"`
- `"Browser: HIGH"`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Network / proxy: MEDIUM"`
- `"Summarizer Availability"`
- `"Summarizer Language Availability"`
- `"[\"Google Deutsch (de-DE)\",\"Google US English (en-US)\",\"Google UK Englis...`
- `"[\"en-US\",\"en\"]"`
- `"downloadable"`
- `"downloadable"`
- `"en"`
- `"en"`
- `"supported"`
- `"webdriver"`
fork only (12):
- `"America/Chicago"`
- `"Bot score 20/100"`
- `"Browser: MEDIUM"`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Network / proxy: LOW"`
- `"NotSupportedError"`
- `"TIMEOUT"`
- `"[\"Microsoft David - English (United States) (en-US)\",\"Microsoft Mark - En...`
- `"[\"en-US\"]"`

## detector text incolumitas / headed
control only (31):
- `"\"cWidth\": 1019,"`
- `"\"deviceMemory\": 32,"`
- `"\"deviceMemory\": 32,"`
- `"\"deviceMemory\": 32,"`
- `"\"en\""`
- `"\"en\""`
- `"\"en\""`
- `"\"en-US\","`
- `"\"en-US\","`
- `"\"en-US\","`
- `"\"getTimezoneOffset\": -420,"`
- `"\"hardwareConcurrency\": 16,"`
- `"\"hardwareConcurrency\": 16,"`
- `"\"hardwareConcurrency\": 16,"`
- `"\"level\": 1"`
- `"\"micros\": 0,"`
- `"\"sAvailHeight\": 984,"`
- `"\"sAvailWidth\": 1280,"`
- `"\"sHeight\": 1024,"`
- `"\"sWidth\": 1280,"`
- `"\"timezone\": -420,"`
- `"\"timezone2\": \"Asia/Saigon\","`
- `"\"wInnerHeight\": 869,"`
- `"\"wInnerWidth\": 1034,"`
- `"\"wOuterHeight\": 964,"`
- `"\"wOuterWidth\": 1050,"`
- `"\"wScreenX\": 10,"`
- `"\"webDriver\": \"FAIL\","`
- `"\"webDriverValue\": true,"`
- `"\"webcams\": 0"`
- `"\"webdriverPresent\": \"FAIL\","`
fork only (28):
- `"\"cWidth\": 1269,"`
- `"\"deviceMemory\": 8,"`
- `"\"deviceMemory\": 8,"`
- `"\"deviceMemory\": 8,"`
- `"\"en-US\""`
- `"\"en-US\""`
- `"\"en-US\""`
- `"\"getTimezoneOffset\": 360,"`
- `"\"hardwareConcurrency\": 12,"`
- `"\"hardwareConcurrency\": 12,"`
- `"\"hardwareConcurrency\": 12,"`
- `"\"level\": 0.75"`
- `"\"micros\": 1,"`
- `"\"sAvailHeight\": 1152,"`
- `"\"sAvailWidth\": 1920,"`
- `"\"sHeight\": 1200,"`
- `"\"sWidth\": 1920,"`
- `"\"timezone\": 300,"`
- `"\"timezone2\": \"America/Chicago\","`
- `"\"wInnerHeight\": 949,"`
- `"\"wInnerWidth\": 1284,"`
- `"\"wOuterHeight\": 1152,"`
- `"\"wOuterWidth\": 1920,"`
- `"\"wScreenX\": 0,"`
- `"\"webDriver\": \"OK\","`
- `"\"webDriverValue\": false,"`
- `"\"webcams\": 1"`
- `"\"webdriverPresent\": \"OK\","`

## detector text incolumitas / headless
control only (40):
- `"\"CHR_MEMORY\": \"FAIL\","`
- `"\"HEADCHR_UA\": \"FAIL\","`
- `"\"appVersion\": \"5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTM...`
- `"\"appVersion\": \"5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTM...`
- `"\"appVersion\": \"5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTM...`
- `"\"cWidth\": 749,"`
- `"\"deviceMemory\": 32,"`
- `"\"deviceMemory\": 32,"`
- `"\"deviceMemory\": 32,"`
- `"\"en\""`
- `"\"en\""`
- `"\"en\""`
- `"\"en-US\","`
- `"\"en-US\","`
- `"\"en-US\","`
- `"\"getTimezoneOffset\": -420,"`
- `"\"hardwareConcurrency\": 16,"`
- `"\"hardwareConcurrency\": 16,"`
- `"\"hardwareConcurrency\": 16,"`
- `"\"level\": 1"`
- `"\"micros\": 0,"`
- `"\"sAvailHeight\": 600,"`
- `"\"sAvailWidth\": 800,"`
- `"\"sHeight\": 600,"`
- `"\"sWidth\": 800,"`
- `"\"timezone\": -420,"`
- `"\"timezone2\": \"Asia/Saigon\","`
- `"\"userAgent\": \"FAIL\","`
- `"\"userAgent\": \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3...`
- `"\"userAgent\": \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3...`
- `"\"userAgent\": \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3...`
- `"\"wInnerHeight\": 485,"`
- `"\"wInnerWidth\": 764,"`
- `"\"wOuterHeight\": 580,"`
- `"\"wOuterWidth\": 780,"`
- `"\"wScreenX\": 10,"`
- `"\"webDriver\": \"FAIL\","`
- `"\"webDriverValue\": true,"`
- `"\"webcams\": 0"`
- `"\"webdriverPresent\": \"FAIL\","`
fork only (37):
- `"\"CHR_MEMORY\": \"OK\","`
- `"\"HEADCHR_UA\": \"OK\","`
- `"\"appVersion\": \"5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTM...`
- `"\"appVersion\": \"5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTM...`
- `"\"appVersion\": \"5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTM...`
- `"\"cWidth\": 1889,"`
- `"\"deviceMemory\": 8,"`
- `"\"deviceMemory\": 8,"`
- `"\"deviceMemory\": 8,"`
- `"\"en-US\""`
- `"\"en-US\""`
- `"\"en-US\""`
- `"\"getTimezoneOffset\": 360,"`
- `"\"hardwareConcurrency\": 12,"`
- `"\"hardwareConcurrency\": 12,"`
- `"\"hardwareConcurrency\": 12,"`
- `"\"level\": 0.75"`
- `"\"micros\": 1,"`
- `"\"sAvailHeight\": 1152,"`
- `"\"sAvailWidth\": 1920,"`
- `"\"sHeight\": 1200,"`
- `"\"sWidth\": 1920,"`
- `"\"timezone\": 300,"`
- `"\"timezone2\": \"America/Chicago\","`
- `"\"userAgent\": \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3...`
- `"\"userAgent\": \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3...`
- `"\"userAgent\": \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.3...`
- `"\"userAgent\": \"OK\","`
- `"\"wInnerHeight\": 1057,"`
- `"\"wInnerWidth\": 1904,"`
- `"\"wOuterHeight\": 1152,"`
- `"\"wOuterWidth\": 1920,"`
- `"\"wScreenX\": 0,"`
- `"\"webDriver\": \"OK\","`
- `"\"webDriverValue\": false,"`
- `"\"webcams\": 1"`
- `"\"webdriverPresent\": \"OK\","`

## detector text iphey / headed
control only (10):
- `"1280x1024"`
- `"Asia/Saigon"`
- `"Chrome"`
- `"Detected an automated browser environment signal (diver)"`
- `"GMT+7"`
- `"Indochina Time"`
- `"Software"`
- `"Vietnam"`
- `"audiooutput"`
- `"en-US, en"`
fork only (12):
- `"1920x1200"`
- `"America/Chicago"`
- `"Browser"`
- `"CDT"`
- `"Central Daylight Time"`
- `"Click here to see"`
- `"Detected an inconsistent browser fingerprint (roadmap)"`
- `"Detected masked or inconsistent location data (light)"`
- `"Everything is fine"`
- `"Location"`
- `"audioinput, videoinput, audiooutput"`
- `"en-US"`

## detector text iphey / headless
control only (14):
- `"800x600"`
- `"Asia/Saigon"`
- `"Chrome Headless"`
- `"Chrome Headless"`
- `"Chrome Headless"`
- `"Detected an automated browser environment signal (diver)"`
- `"GMT+7"`
- `"Indochina Time"`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Software"`
- `"Vietnam"`
- `"audiooutput"`
- `"en-US, en"`
fork only (16):
- `"1920x1200"`
- `"America/Chicago"`
- `"Browser"`
- `"CDT"`
- `"Central Daylight Time"`
- `"Chrome"`
- `"Chrome"`
- `"Click here to see"`
- `"Detected an inconsistent browser fingerprint (roadmap)"`
- `"Detected masked or inconsistent location data (light)"`
- `"Everything is fine"`
- `"Location"`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"audioinput, videoinput, audiooutput"`
- `"en-US"`

## detector text pixelscan / headed
control only (7):
- `"1280x1024"`
- `"1280x984"`
- `"Asia/Saigon"`
- `"Automated behavior detected"`
- `"No"`
- `"Vietnam / <city>"`
- `"en"`
fork only (7):
- `"1920x1152"`
- `"1920x1200"`
- `"America/Chicago"`
- `"Join Pixelscan Community"`
- `"No automated behavior detected"`
- `"Timezone spoofed"`
- `"Yes"`

## detector text pixelscan / headless
control only (14):
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
- `"Vietnam / <city>"`
- `"a Сhromium-based browser on Windows"`
- `"en"`
fork only (9):
- `"1920x1152"`
- `"1920x1200"`
- `"America/Chicago"`
- `"Chrome 154.0.0.0 on Windows"`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"No automated behavior detected"`
- `"Timezone spoofed"`
- `"Yes"`

## detector text rebrowser / headed
control only (3):
- `"\"height\": 869"`
- `"\"width\": 1034,"`
- `"typeof navigator.webdriver = boolean; navigator.webdriver = true"`
fork only (2):
- `"\"height\": 949"`
- `"\"width\": 1284,"`

## detector text rebrowser / headless
control only (3):
- `"\"height\": 485"`
- `"\"width\": 764,"`
- `"typeof navigator.webdriver = boolean; navigator.webdriver = true"`
fork only (2):
- `"\"height\": 1057"`
- `"\"width\": 1904,"`

## detector text sannysoft / headed
control only (39):
- `"\"cWidth\": 1003,"`
- `"\"cWidth\": 1003,"`
- `"\"deviceMemory\": 32,"`
- `"\"en\""`
- `"\"en\""`
- `"\"en-US\","`
- `"\"en-US\","`
- `"\"micros\": 0,"`
- `"\"sAvailHeight\": 984,"`
- `"\"sAvailHeight\": 984,"`
- `"\"sAvailWidth\": 1280,"`
- `"\"sAvailWidth\": 1280,"`
- `"\"sHeight\": 1024,"`
- `"\"sHeight\": 1024,"`
- `"\"sWidth\": 1280,"`
- `"\"sWidth\": 1280,"`
- `"\"wInnerHeight\": 869,"`
- `"\"wInnerHeight\": 869,"`
- `"\"wInnerWidth\": 1034,"`
- `"\"wInnerWidth\": 1034,"`
- `"\"wOuterHeight\": 964,"`
- `"\"wOuterHeight\": 964,"`
- `"\"wOuterWidth\": 1050,"`
- `"\"wOuterWidth\": 1050,"`
- `"\"wScreenX\": 10,"`
- `"\"wScreenX\": 10,"`
- `"\"webDriverValue\": true,"`
- `"\"webcams\": 0"`
- `"Hash: -134274369"`
- `"Hash: -134274369"`
- `"Hash: -134274369"`
- `"Hash: -134274369"`
- `"Hash: -134274369"`
- `"Level: 1"`
- `"en-US,en"`
- `"navigator.mediaDevices\taudiooutput: id ="`
- `"present (failed)"`
- `"screen.height\t1024"`
- `"screen.width\t1280"`
fork only (39):
- `"\"cWidth\": 1253,"`
- `"\"cWidth\": 1253,"`
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
- `"\"wInnerHeight\": 949,"`
- `"\"wInnerHeight\": 949,"`
- `"\"wInnerWidth\": 1284,"`
- `"\"wInnerWidth\": 1284,"`
- `"\"wOuterHeight\": 1152,"`
- `"\"wOuterHeight\": 1152,"`
- `"\"wOuterWidth\": 1920,"`
- `"\"wOuterWidth\": 1920,"`
- `"\"wScreenX\": 0,"`
- `"\"wScreenX\": 0,"`
- `"\"webDriverValue\": false,"`
- `"\"webcams\": 1"`
- `"Hash: -1245261672"`
- `"Hash: -1245261672"`
- `"Hash: -1245261672"`
- `"Hash: -1245261672"`
- `"Hash: -1245261672"`
- `"Level: 0.75"`
- `"audiooutput: id ="`
- `"en-US"`
- `"missing (passed)"`
- `"navigator.mediaDevices\taudioinput: id ="`
- `"screen.height\t1200"`
- `"screen.width\t1920"`
- `"videoinput: id ="`

## detector text sannysoft / headless
control only (46):
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
- `"Hash: -134274369"`
- `"Hash: -134274369"`
- `"Hash: -134274369"`
- `"Hash: -134274369"`
- `"Hash: -134274369"`
- `"Level: 1"`
- `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Ge...`
- `"en-US,en"`
- `"navigator.mediaDevices\taudiooutput: id ="`
- `"navigator.userAgent\tMozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/5...`
- `"present (failed)"`
- `"screen.height\t600"`
- `"screen.width\t800"`
fork only (46):
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
- `"Hash: -1245261672"`
- `"Hash: -1245261672"`
- `"Hash: -1245261672"`
- `"Hash: -1245261672"`
- `"Hash: -1245261672"`
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

## detector text whoer / headed
control only (7):
- `"Each with a new fingerprint and residential IP."`
- `"N/A  Singapore"`
- `"One browser."`
- `"Separate identities."`
- `"Your disguise: 70% Moderate security and anonymity remarks"`
- `"<isp>"`
- `"<isp>"`
fork only (15):
- `"A browser with unlimited ready-to-use profiles."`
- `"Browser fingerprint"`
- `"Carolina"`
- `"Client"`
- `"Fresh fingerprint and residential IP included."`
- `"Generated"`
- `"Included"`
- `"More than"`
- `"N/A"`
- `"Ready to browse"`
- `"Residential IP"`
- `"Your disguise: 90% Minor remarks regarding your anonymity and security"`
- `"a new IP."`
- `"<isp>"`
- `"<isp>"`

## detector text whoer / headless
control only (5):
- `"Performance and Security by Cloudflare"`
- `"Performing security verification"`
- `"Privacy"`
- `"This website uses a security service to protect against malicious bots. This...`
- `"whoer.net"`
fork only (193):
- `"(VN)"`
- `"<ip>"`
- `"<ip>  Singapore"`
- `"<ip> - <ip>"`
- `"<ip>"`
- `"7 days free · No card required"`
- `"A browser with unlimited ready-to-use profiles."`
- `"ACTIVEX"`
- `"APPS"`
- `"AS Number:"`
- `"AS Organization:"`
- `"About us"`
- `"Anonymizer:"`
- `"Apps Privacy Policy"`
- `"Asia/Ho_Chi_Minh"`
- `"Best VPN services"`
- `"Blacklist:"`
- `"Blog"`
- `"Browser fingerprint"`
- `"Browser fingerprint"`
- `"Browser fingerprint checker"`
- `"Browser:"`
- `"Buy VPN"`
- `"Buy VPN now"`
- `"Buy aged accounts"`
- `"COOKIES"`
- `"Carolina"`
- `"Check IP (country, ISP, ASN, ZIP code)"`
- `"Chrome 154.0 Check fingerprint"`
- `"City:"`
- `"Claim your free trial"`
- `"Client"`
- `"Contacts"`
- `"Copyright © whoer.net 2008-2026"`
- `"Country:"`
- `"Crypto Converter"`
- `"Customer Support"`
- `"DNS"`
- `"DNS LEAK TEST"`
- `"Disabled"`
- `"Disabled"`
- `"Disabled"`
- `"Does a VPN or proxy change what I see as my IP here?"`
- `"EVERCOOKIE TEST"`
- `"Enabled"`
- `"Enabled"`
- `"English"`
- `"Extended version"`
- `"FAQ: IP address and privacy on Whoer"`
- `"FLASH"`
- `"Fresh fingerprint and residential IP included."`
- `"Generated"`
- `"Get proxy"`
- `"Go"`
- `"Go"`
- `"Go"`
- `"<city>"`
- `"<city>"`
- `"<city> / Vietnam"`
- `"Hostname:"`
- `"Hostname:"`
- `"How do I find my IP address and location?"`
- `"How to disable Internet when VPN goes offline"`
- `"How to find IP address on your devices"`
- `"How to install OpenVPN on your router"`
- `"INFORMATION"`
- `"IP Address Details"`
- `"IP range:"`
- `"IP, headers and technical signals. No extra software, no personal data forms."`
- `"ISP:"`
- `"ISP:"`
- `"If you want to check IP on Windows, you can find it in the network settings....`
- `"Included"`
- `"Is it safe to use Whoer to check my IP address?"`
- `"JAVA"`
- `"JAVASCRIPT"`
- `"Just open Whoer.net in your browser. The page loads, and on the first screen"`
- `"LANGUAGE"`
- `"LOCATION"`
- `"Leaks are cases when real IP or DNS requests are visible outside a VPN or pr...`
- `"Local:"`
- `"More"`
- `"More than"`
- `"Multi-Acc"`
- `"My IP"`
- `"My IP"`
- `"My IP"`
- `"My IP: <ip>"`
- `"NOID"`
- `"NOID"`
- `"NOID is an example of such a privacy-focused browser."`
- `"NOID protects your privacy with isolated profiles"`
- `"No"`
- `"No"`
- `"No"`
- `"OS:"`
- `"On Whoer you see it together with rough location, ISP name and ASN."`
- `"On a Mac, click the Apple menu and open System Settings (or System Preferenc...`
- `"Organization:"`
- `"PORT SCANNER"`
- `"Partner With Us"`
- `"Ping"`
- `"Ping"`
- `"Port scanner"`
- `"Privacy Policy"`
- `"Proxy:"`
- `"Ready to browse"`
- `"Recover access code"`
- `"Refund Policy"`
- `"Region:"`
- `"Resi Proxy"`
- `"Resi Proxy"`
- `"Residential IP"`
- `"Reversed:"`
- `"SERVICES"`
- `"SOCIAL NETWORKS"`
- `"Secure internet"`
- `"Services"`
- `"Specialized browsers are designed to manage and isolate browser fingerprints...`
- `"Speed test"`
- `"Speed test"`
- `"System:"`
- `"TIME"`
- `"Telegram"`
- `"Telegram"`
- `"Terms of use"`
- `"The VPN leak test detects VPNs and TOR. We compare your IP country with DNS,...`
- `"The Whoer.net leaks score"`
- `"The Whoer.net leaks score is a helpful feature that shows how secure your co...`
- `"The browser fingerprint checker shows details like your User-Agent, HTTP hea...`
- `"The proxy checker validates HTTP/HTTPS/SOCKS5: it inspects headers, scans co...`
- `"To find IP on Android, open Settings and go to your Wi-Fi section. Tap the W...`
- `"To find iPhone IP, open Settings, then Wi-Fi. Tap the little “i” icon next t...`
- `"Top Services 2026 by Whoer.net"`
- `"Try NOID"`
- `"US"`
- `"USEFUL LINKS"`
- `"Use extended version"`
- `"VPN"`
- `"VPN"`
- `"VPN check & Proxy checker"`
- `"VPN for Android"`
- `"VPN for Chrome"`
- `"VPN for Edge"`
- `"VPN for Firefox"`
- `"VPN for Linux"`
- `"VPN for Mac"`
- `"VPN for Opera"`
- `"VPN for Router"`
- `"VPN for Windows"`
- `"VPN for Yandex"`
- `"VPN for games"`
- `"VPN for iOS"`
- `"VPN-related problems and solutions"`
- `"Vietnam"`
- `"<isp> Group"`
- `"<isp> Group"`
- `"<isp> Group"`
- `"<isp> Group"`
- `"WADE X Multi-Acc Browser"`
- `"WADE X Multi-Acc Browser"`
- `"WEBRTC"`
- `"WHOER.NET"`
- `"Want to know more?"`
- `"We could not find that you are logged in to social networks"`
- `"We only show data your browser and network already send with every request:"`
- `"Websites are tracking you across accounts and IPs"`
- `"Websites identify users not only by IP, but also by a unique browser fingerp...`
- `"What does “see leaks” on this page mean?"`
- `"What is My IP – Free IP Lookup"`
- `"What is my IP address and what does it show?"`
- `"When I open the main page, I can see my public IP address, DNS, country/city...`
- `"Whoer runs simple DNS and WebRTC checks and highlights if something is expos...`
- `"Whoer.net is a user-friendly What is my IP tool to find IP address in one cl...`
- `"Whois"`
- `"Whois"`
- `"Whois"`
- `"Win10.0"`
- `"With Whoer.net, you can instantly check for IP and DNS leaks and see if your...`
- `"YOUR FINGERPRINT IS EXPOSED"`
- `"Yes. If your VPN or proxy is working, you should see its IP and country inst...`
- `"You have a public IP address (what websites see) and a local IP address (wha...`
- `"Your IP address is a number that helps your devices connect. If you want to ...`
- `"Your IP address is a number your provider gives your device on the internet."`
- `"Your disguise: 70% Moderate security and anonymity remarks"`
- `"Your local IP is the one used inside your home or office network. You need i...`
- `"ZIP:"`
- `"Zone:"`
- `"a new IP."`
- `"<isp>"`
- `"<isp>"`
- `"of your real network IP. If not, the tests may show leaks or mismatches."`
- `"you see your IP address, country or city, provider and basic connection info."`

## verdicts

| row | control headed | fork headed | control headless | fork headless |
|---|---|---|---|---|
| det.amiunique.blocked | "no" | "no" | "no" | "no" |
| det.browserleaks_canvas.blocked | "no" | "no" | "no" | "no" |
| det.browserleaks_client_hints.blocked | "no" | "no" | "no" | "no" |
| det.browserleaks_fonts.blocked | "no" | "no" | "no" | "no" |
| det.browserleaks_javascript.blocked | "no" | "no" | "no" | "no" |
| det.browserleaks_tls.blocked | "no" | "no" | "no" | "no" |
| det.browserleaks_webgl.blocked | "no" | "no" | "no" | "no" |
| det.browserleaks_webrtc.blocked | "no" | "no" | "no" | "no" |
| det.browserscan.blocked | "no" | "no" | "no" | "no" |
| det.creepjs.blocked | "no" | "no" | "no" | "no" |
| det.dbi_bot.blocked | "no" | "no" | "no" | "no" |
| det.dbi_bot.hasBotUserAgent | false | false | true | false |
| det.dbi_bot.hasHeadlessChromeDefaultScreenResolution | false | false | false | false |
| det.dbi_bot.hasHighHardwareConcurrency | false | false | false | false |
| det.dbi_bot.hasInconsistentChromeObject | false | false | false | false |
| det.dbi_bot.hasInconsistentClientHints | false | false | false | false |
| det.dbi_bot.hasInconsistentGPUFeatures | false | false | false | false |
| det.dbi_bot.hasInconsistentTimingResolution | false | false | false | false |
| det.dbi_bot.hasInconsistentWebGLShaderLang | false | false | false | false |
| det.dbi_bot.hasInconsistentWorkerValues | false | false | false | false |
| det.dbi_bot.hasSuspiciousWeakSignals | false | false | false | false |
| det.dbi_bot.hasWebdriverInFrameTrue | true | false | true | false |
| det.dbi_bot.hasWebdriverTrue | true | false | true | false |
| det.dbi_bot.isAutomatedWithCDP | false | false | false | false |
| det.dbi_bot.isAutomatedWithCDPInWebWorker | false | false | false | false |
| det.dbi_bot.isBot | true | false | true | false |
| det.dbi_bot.isHeadlessChrome | false | false | false | false |
| det.dbi_bot.isIframeOverridden | false | false | false | false |
| det.dbi_bot.isNightmare | false | false | false | false |
| det.dbi_bot.isPhantom | false | false | false | false |
| det.dbi_bot.isPlaywright | false | false | false | false |
| det.dbi_bot.isSeleniumChromeDefault | false | false | false | false |
| det.dbi_bot.isSequentum | false | false | false | false |
| det.dbi_bot.isWebGLInconsistent | false | false | false | false |
| det.detect_headless.blocked | "no" | "no" | "no" | "no" |
| det.fingerprint_pro.Bot | "You are a bad bot 🤖 (type: webdriver)" | "Not detected" | "You are a bad bot 🤖 (type: headless_chrome)" | "Not detected" |
| det.fingerprint_pro.Browser Tampering | "Yes 🖥️🔧" | "Yes 🖥️🔧" | "Not detected" | "Yes 🖥️🔧" |
| det.fingerprint_pro.Developer Tools | "Not detected" | "Not detected" | "Not detected" | "Not detected" |
| det.fingerprint_pro.High-Activity Device | "Yes 🔥" | "Not detected" | "Yes 🔥" | "Not detected" |
| det.fingerprint_pro.IP Blocklist | "Not detected" | "Not detected" | "Not detected" | "Not detected" |
| det.fingerprint_pro.Incognito Mode | "Not detected" | "Not detected" | "Not detected" | "Not detected" |
| det.fingerprint_pro.Privacy Settings | "Not detected" | "Not detected" | "Not detected" | "Not detected" |
| det.fingerprint_pro.Proxy Detection | "Not detected" | "Your IP is used by a residential proxy (confidence: low, ML score: 0.602)" | "Not detected" | "Your IP is used by a residential proxy (confidence: low, ML score: 0.602)" |
| det.fingerprint_pro.Rare Device | "Not detected" | "Not detected" | "Not detected" | "Not detected" |
| det.fingerprint_pro.Suspect Score | "25" | "21" | "17" | "21" |
| det.fingerprint_pro.VPN | "You are using a VPN 🌐 (public VPN IP)" | "You are using a VPN 🌐 (public VPN IP, timezone mismatch)" | "You are using a VPN 🌐 (public VPN IP)" | "You are using a VPN 🌐 (public VPN IP, timezone mismatch)" |
| det.fingerprint_pro.Virtual Machine | "Not detected" | "Not detected" | "Not detected" | "Not detected" |
| det.fingerprint_pro.blocked | "no" | "no" | "no" | "no" |
| det.fingerprint_scan.blocked | "no" | "no" | "no" | "no" |
| det.incolumitas.CHR_BATTERY | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.CHR_DEBUG_TOOLS | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.CHR_MEMORY | "OK" | "OK" | "FAIL" | "OK" |
| det.incolumitas.HEADCHR_CHROME_OBJ | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.HEADCHR_IFRAME | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.HEADCHR_PERMISSIONS | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.HEADCHR_PLUGINS | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.HEADCHR_UA | "OK" | "OK" | "FAIL" | "OK" |
| det.incolumitas.MQ_SCREEN | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.PHANTOM_ETSL | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.PHANTOM_LANGUAGE | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.PHANTOM_OVERFLOW | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.PHANTOM_PROPERTIES | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.PHANTOM_UA | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.PHANTOM_WEBSOCKET | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.PHANTOM_WINDOW_HEIGHT | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.SELENIUM_DRIVER | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.SEQUENTUM | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.TRANSPARENT_PIXEL | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.VIDEO_CODECS | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.WEBDRIVER | "FAIL" | "FAIL" | "FAIL" | "FAIL" |
| det.incolumitas.blocked | "no" | "no" | "no" | "no" |
| det.incolumitas.connectionRTT | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.inconsistentServiceWorkerNavigatorPropery | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.inconsistentWebWorkerNavigatorPropery | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.languages | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.overflowTest | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.overrideTest | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.pluginArray | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.pluginsLength | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.puppeteerEvaluationScript | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.puppeteerExtraStealthUsed | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.refMatch | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.userAgent | "OK" | "OK" | "FAIL" | "OK" |
| det.incolumitas.webDriver | "FAIL" | "OK" | "FAIL" | "OK" |
| det.incolumitas.webDriverAdvanced | "OK" | "OK" | "OK" | "OK" |
| det.incolumitas.webdriverPresent | "FAIL" | "OK" | "FAIL" | "OK" |
| det.iphey.blocked | "no" | "no" | "no" | "no" |
| det.pixelscan.blocked | "no" | "no" | "no" | "no" |
| det.rebrowser.blocked | "no" | "no" | "no" | "no" |
| det.rebrowser.bypassCsp | "pass" | "pass" | "pass" | "pass" |
| det.rebrowser.dummyFn | "not triggered" | "not triggered" | "not triggered" | "not triggered" |
| det.rebrowser.exposeFunctionLeak | "not triggered" | "not triggered" | "not triggered" | "not triggered" |
| det.rebrowser.mainWorldExecution | "not triggered" | "not triggered" | "not triggered" | "not triggered" |
| det.rebrowser.navigatorWebdriver | "fail" | "pass" | "fail" | "pass" |
| det.rebrowser.pwInitScripts | "pass" | "pass" | "pass" | "pass" |
| det.rebrowser.runtimeEnableLeak | "pass" | "pass" | "pass" | "pass" |
| det.rebrowser.sourceUrlLeak | "not triggered" | "not triggered" | "not triggered" | "not triggered" |
| det.rebrowser.useragent | "pass" | "pass" | "pass" | "pass" |
| det.rebrowser.viewport | "pass" | "pass" | "pass" | "pass" |
| det.sannysoft.blocked | "no" | "no" | "no" | "no" |
| det.whoer.blocked | "no" | "no" | "cloudflare challenge" | "no" |

