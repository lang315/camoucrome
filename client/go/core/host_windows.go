//go:build windows

package core

import (
	"runtime"
	"strconv"
	"syscall"
	"unsafe"
)

var (
	user32           = syscall.NewLazyDLL("user32.dll")
	procSPI          = user32.NewProc("SystemParametersInfoW")
	procSetThreadDpi = user32.NewProc("SetThreadDpiAwarenessContext")
)

// dpiSystemAware is DPI_AWARENESS_CONTEXT_SYSTEM_AWARE, the handle value -2.
const dpiSystemAware = ^uintptr(1)

// probeWorkArea is SPI_GETWORKAREA in PHYSICAL px. A DPI-unaware process is
// handed a virtualised (scaled down) rectangle, so the calling thread is
// switched to system DPI awareness for the one call and switched back after;
// that changes nothing for the caller's own windows. The thread is locked to
// its OS thread for the duration. Needs Windows 10 1607+ (SetThreadDpiAwarenessContext);
// without it the work area stays unknown. Only meaningful in the user's own
// session (session 1).
func probeWorkArea() ([2]int, []string) {
	if procSetThreadDpi.Find() != nil {
		return [2]int{}, []string{"work area: SetThreadDpiAwarenessContext is missing (Windows before 10 1607)"}
	}
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	old, _, _ := procSetThreadDpi.Call(dpiSystemAware)
	if old == 0 {
		return [2]int{}, []string{"work area: SetThreadDpiAwarenessContext failed"}
	}
	defer procSetThreadDpi.Call(old)
	var r struct{ left, top, right, bottom int32 }
	if ok, _, _ := procSPI.Call(0x30, 0, uintptr(unsafe.Pointer(&r)), 0); ok == 0 {
		return [2]int{}, []string{"work area: SystemParametersInfoW failed"}
	}
	return [2]int{int(r.right - r.left), int(r.bottom - r.top)}, nil
}

// probePlatformVersion mirrors Chromium 157 components/embedder_support/user_agent_utils.cc
// GetUniversalApiContractVersion: HKLM\SOFTWARE\Microsoft\WindowsRuntime\WellKnownContracts
// (KEY_QUERY_VALUE | KEY_WOW64_64KEY), DWORD "Windows.Foundation.UniversalApiContract" = HIWORD.LOWORD.0;
// a missing key or value gives 19.0.0; builds up to RS4 use the pre-RS5 map. The build number is
// CurrentBuildNumber from HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion.
func probePlatformVersion() (string, []string) {
	buildStr, ok := regString(`SOFTWARE\Microsoft\Windows NT\CurrentVersion`, "CurrentBuildNumber")
	build, err := strconv.Atoi(buildStr)
	if !ok || err != nil {
		return "", []string{"platform version: CurrentBuildNumber unreadable"}
	}
	dword, have := regDword(`SOFTWARE\Microsoft\WindowsRuntime\WellKnownContracts`, "Windows.Foundation.UniversalApiContract")
	return platformVersion(build, dword, have), nil
}

func openKey(path string) (syscall.Handle, bool) {
	var h syscall.Handle
	key, _ := syscall.UTF16PtrFromString(path)
	return h, syscall.RegOpenKeyEx(syscall.HKEY_LOCAL_MACHINE, key, 0, syscall.KEY_QUERY_VALUE|syscall.KEY_WOW64_64KEY, &h) == nil
}

func regString(path, name string) (string, bool) {
	h, ok := openKey(path)
	if !ok {
		return "", false
	}
	defer syscall.RegCloseKey(h)
	n16, _ := syscall.UTF16PtrFromString(name)
	var buf [32]uint16
	n := uint32(len(buf) * 2)
	if syscall.RegQueryValueEx(h, n16, nil, nil, (*byte)(unsafe.Pointer(&buf[0])), &n) != nil {
		return "", false
	}
	return syscall.UTF16ToString(buf[:]), true
}

func regDword(path, name string) (uint32, bool) {
	h, ok := openKey(path)
	if !ok {
		return 0, false
	}
	defer syscall.RegCloseKey(h)
	n16, _ := syscall.UTF16PtrFromString(name)
	var typ, v, n uint32 = 0, 0, 4
	if syscall.RegQueryValueEx(h, n16, nil, &typ, (*byte)(unsafe.Pointer(&v)), &n) != nil || typ != syscall.REG_DWORD {
		return 0, false
	}
	return v, true
}
