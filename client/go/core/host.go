package core

import "runtime"

// ProbeHost reads what the OS answers without a browser: the allowed CPUs, the
// work area and (Windows) the UA-CH platform version. The display needs the
// one-time browser probe (DisplayProbeJS) and stays nil. A value it cannot read
// stays zero, with a warning; Resolve skips that step.
func ProbeHost() (Host, []string) {
	var h Host
	var warn []string
	if cpus, err := affinityGet(); err == nil && len(cpus) > 0 {
		h.Cores = len(cpus)
	} else {
		h.Cores = runtime.NumCPU()
	}
	wa, w := probeWorkArea()
	h.WorkArea = wa
	warn = append(warn, w...)
	pv, w := probePlatformVersion()
	h.PlatformVersion = pv
	warn = append(warn, w...)
	return h, warn
}

// platformVersionForBuild maps a Windows build number to the UA-CH
// platformVersion Chrome reports. Chromium derives it in
// components/embedder_support/user_agent_utils.cc: Windows 10 reports 10.0.0,
// Windows 11 reports the UniversalApiContract major (13 for 21H2, 14 for 22H2,
// 15 for 23H2, 19 for 24H2 and later).
// UNVERIFIED against stock Chrome: the table is from memory; the orchestrator
// compares it with getHighEntropyValues on the host (plan, Self-review notes).
func platformVersionForBuild(build int) string {
	switch {
	case build < 22000:
		return "10.0.0"
	case build < 22621:
		return "13.0.0"
	case build < 22631:
		return "14.0.0"
	case build < 26100:
		return "15.0.0"
	default:
		return "19.0.0"
	}
}
