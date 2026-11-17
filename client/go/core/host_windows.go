//go:build windows

package core

import (
	"fmt"
	"strconv"
	"syscall"
	"unsafe"
)

var (
	user32           = syscall.NewLazyDLL("user32.dll")
	procSPI          = user32.NewProc("SystemParametersInfoW")
	procGetDpiForSys = user32.NewProc("GetDpiForSystem")
)

// probeWorkArea is SPI_GETWORKAREA scaled to physical px by the system DPI.
// The process is not made DPI-aware (that would change the caller's own
// windows), so the rectangle comes back in logical px, and logical x dpi / 96
// is physical. Only meaningful in the user's own session (session 1).
func probeWorkArea() ([2]int, []string) {
	var r struct{ left, top, right, bottom int32 }
	if ok, _, _ := procSPI.Call(0x30, 0, uintptr(unsafe.Pointer(&r)), 0); ok == 0 {
		return [2]int{}, []string{"work area: SystemParametersInfoW failed"}
	}
	dpi := 96
	if procGetDpiForSys.Find() == nil {
		if d, _, _ := procGetDpiForSys.Call(); d != 0 {
			dpi = int(d)
		}
	}
	return [2]int{int(r.right-r.left) * dpi / 96, int(r.bottom-r.top) * dpi / 96}, nil
}

// probePlatformVersion reads CurrentBuildNumber from the registry (HKLM, SOFTWARE\Microsoft\Windows NT\CurrentVersion).
func probePlatformVersion() (string, []string) {
	var h syscall.Handle
	key, _ := syscall.UTF16PtrFromString(`SOFTWARE\Microsoft\Windows NT\CurrentVersion`)
	if err := syscall.RegOpenKeyEx(syscall.HKEY_LOCAL_MACHINE, key, 0, syscall.KEY_READ, &h); err != nil {
		return "", []string{fmt.Sprintf("platform version: registry open failed: %v", err)}
	}
	defer syscall.RegCloseKey(h)
	name, _ := syscall.UTF16PtrFromString("CurrentBuildNumber")
	var buf [32]uint16
	n := uint32(len(buf) * 2)
	if err := syscall.RegQueryValueEx(h, name, nil, nil, (*byte)(unsafe.Pointer(&buf[0])), &n); err != nil {
		return "", []string{fmt.Sprintf("platform version: CurrentBuildNumber unreadable: %v", err)}
	}
	build, err := strconv.Atoi(syscall.UTF16ToString(buf[:]))
	if err != nil {
		return "", []string{"platform version: CurrentBuildNumber is not a number"}
	}
	return platformVersionForBuild(build), nil
}
