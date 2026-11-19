package core

import (
	"fmt"
	"os"
	"runtime"
	"strings"
)

// cpuVendorOf finds GenuineIntel or AuthenticAMD in /proc/cpuinfo or PROCESSOR_IDENTIFIER text.
func cpuVendorOf(s string) string {
	for _, v := range []string{intelCPU, amdCPU} {
		if strings.Contains(s, v) {
			return v
		}
	}
	return ""
}

// probeCPUVendor reads /proc/cpuinfo (Linux), else PROCESSOR_IDENTIFIER (Windows); "" when neither answers.
func probeCPUVendor() string {
	return cpuVendorFrom("/proc/cpuinfo", os.Getenv("PROCESSOR_IDENTIFIER"))
}

func cpuVendorFrom(path, env string) string {
	if b, err := os.ReadFile(path); err == nil {
		if len(b) > 4096 {
			b = b[:4096]
		}
		return cpuVendorOf(string(b))
	}
	return cpuVendorOf(env)
}

// ProbeHost reads what the OS answers without a browser: the allowed CPUs, the
// work area and (Windows) the UA-CH platform version. The display needs the
// one-time browser probe (DisplayProbeJS) and stays nil. A value it cannot read
// stays zero, with a warning; Resolve skips that step.
func ProbeHost() (Host, []string) {
	var h Host
	var warn []string
	pinMu.Lock()             // not while a Pinned start is mid-pin: it would read the narrowed mask. Do not call ProbeHost from inside start.
	cpus, _ := affinityGet() // an unreadable mask falls back to the runtime count
	pinMu.Unlock()
	if len(cpus) > 0 {
		h.Cores = len(cpus)
	} else {
		h.Cores = runtime.NumCPU()
	}
	h.CPUVendor = probeCPUVendor()
	wa, w := probeWorkArea()
	h.WorkArea = wa
	warn = append(warn, w...)
	pv, w := probePlatformVersion()
	h.PlatformVersion = pv
	warn = append(warn, w...)
	return h, warn
}

// highestKnownContract is kHighestKnownUniversalApiContractVersion in Chromium 157
// components/embedder_support/user_agent_utils.cc, GetUniversalApiContractVersion's
// answer when the registry has no contract.
const highestKnownContract = "19.0.0"

// preRS5Contract is that file's map for Windows 10 up to RS4 (build 17134),
// which has no WellKnownContracts key: TH1=1 TH2=2 RS1=3 RS2=4 RS3=5 RS4=6.
// ok is false above RS4.
func preRS5Contract(build int) (string, bool) {
	switch {
	case build > 17134:
		return "", false
	case build >= 17134:
		return "6.0.0", true
	case build >= 16299:
		return "5.0.0", true
	case build >= 15063:
		return "4.0.0", true
	case build >= 14393:
		return "3.0.0", true
	case build >= 10586:
		return "2.0.0", true
	default:
		return "1.0.0", true
	}
}

// contractVersion splits the registry DWORD
// HKLM\SOFTWARE\Microsoft\WindowsRuntime\WellKnownContracts
// "Windows.Foundation.UniversalApiContract" as HIWORD.LOWORD.0, the way
// GetUniversalApiContractVersion does (the minor can be non-zero).
func contractVersion(dword uint32) string {
	return fmt.Sprintf("%d.%d.0", dword>>16, dword&0xFFFF)
}

// platformVersion is the UA-CH platformVersion for a build and the registry's
// contract DWORD (have is false when the key or value is missing).
func platformVersion(build int, dword uint32, have bool) string {
	if v, ok := preRS5Contract(build); ok {
		return v
	}
	if !have {
		return highestKnownContract
	}
	return contractVersion(dword)
}
