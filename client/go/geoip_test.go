package camoucrome

import (
	"errors"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func stubs(t *testing.T, ip string, ipErr error, out string, outErr error) *[][]string {
	var calls [][]string
	oldE, oldX := echoIP, execPython
	echoIP = func(*Proxy) (string, error) { return ip, ipErr }
	execPython = func(python string, args ...string) ([]byte, error) {
		calls = append(calls, append([]string{python}, args...))
		return []byte(out), outErr
	}
	t.Cleanup(func() { echoIP, execPython = oldE, oldX })
	return &calls
}

func TestCheckGeoIPSurfacesTheModulesWarning(t *testing.T) {
	calls := stubs(t, "192.0.2.5", nil, `{"country":"US","timezone":"America/New_York","locale":"en-US","warning":"timezone:id Asia/Tokyo (UTC+09:00) contradicts the exit IP's America/New_York (UTC-04:00)"}`, nil)
	got := CheckGeoIP(Options{Config: map[string]any{"timezone:id": "Asia/Tokyo"}, GeoIP: "/db.mmdb", Python: "py"})
	if len(got) != 1 || !strings.Contains(got[0], "contradicts") {
		t.Fatalf("warnings = %v", got)
	}
	want := []string{"py", "-m", "camoucrome.geoip", "--ip=192.0.2.5", "--db=/db.mmdb", "--check-zone=Asia/Tokyo"}
	if len(*calls) != 1 || strings.Join((*calls)[0], " ") != strings.Join(want, " ") {
		t.Fatalf("exec = %v, want %v", *calls, want)
	}
}

func TestCheckGeoIPIsQuietWhenTheModuleHasNoWarning(t *testing.T) {
	stubs(t, "192.0.2.5", nil, `{"country":"US","timezone":"America/New_York","locale":"en-US","warning":null}`, nil)
	if got := CheckGeoIP(Options{Config: `{"timezone:id":"America/New_York"}`, GeoIP: "/db.mmdb"}); got != nil {
		t.Fatalf("warnings = %v", got)
	}
}

func TestCheckGeoIPWarnsInsteadOfFailingWhenItCannotTell(t *testing.T) {
	cfg := map[string]any{"timezone:id": "Asia/Tokyo"}
	stubs(t, "", errors.New("no echo service answered"), "", nil)
	if got := CheckGeoIP(Options{Config: cfg, GeoIP: "/db.mmdb"}); len(got) != 1 || !strings.Contains(got[0], "could not be checked") || !strings.Contains(got[0], "no echo service") {
		t.Fatalf("echo failure: %v", got)
	}
	stubs(t, "192.0.2.5", nil, `{"error":"192.0.2.5 is not in the database"}`, nil)
	if got := CheckGeoIP(Options{Config: cfg, GeoIP: "/db.mmdb"}); len(got) != 1 || !strings.Contains(got[0], "not in the database") {
		t.Fatalf("not found: %v", got)
	}
	stubs(t, "192.0.2.5", nil, "Traceback ...", nil)
	if got := CheckGeoIP(Options{Config: cfg, GeoIP: "/db.mmdb"}); len(got) != 1 || !strings.Contains(got[0], "no JSON") {
		t.Fatalf("garbage: %v", got)
	}
	stubs(t, "192.0.2.5", nil, "", errors.New("exec: python3 not found"))
	if got := CheckGeoIP(Options{Config: cfg, GeoIP: "/db.mmdb"}); len(got) != 1 || !strings.Contains(got[0], "not found") {
		t.Fatalf("exec failure: %v", got)
	}
}

func TestCheckGeoIPHasNothingToCheckWithoutAZone(t *testing.T) {
	calls := stubs(t, "192.0.2.5", nil, `{}`, nil)
	if got := CheckGeoIP(Options{Config: map[string]any{"a": 1}, GeoIP: "/db.mmdb"}); got != nil || len(*calls) != 0 {
		t.Fatalf("got %v, exec %v", got, *calls)
	}
}

func TestExitIPGivenSkipsTheEchoRequest(t *testing.T) {
	calls := stubs(t, "", errors.New("must not be asked"), `{"warning":null}`, nil)
	CheckGeoIP(Options{Config: map[string]any{"timezone:id": "Asia/Tokyo"}, GeoIP: "/db.mmdb", ExitIP: "192.0.2.9"})
	if len(*calls) != 1 || (*calls)[0][3] != "--ip=192.0.2.9" {
		t.Fatalf("exec = %v", *calls)
	}
}

func TestLaunchWarnsBeforeItTouchesTheDriver(t *testing.T) {
	stubs(t, "192.0.2.5", nil, `{"warning":"contradicts"}`, nil)
	var got []string
	func() {
		defer func() { recover() }() // Launch(nil) panics on the driver, after the check
		Launch(nil, Options{Config: map[string]any{"timezone:id": "Asia/Tokyo"}, GeoIP: "/db.mmdb", Warn: func(m string) { got = append(got, m) }})
	}()
	if len(got) != 1 || got[0] != "contradicts" {
		t.Fatalf("warned %v", got)
	}
}

func TestExitIPAsksThroughTheProxyWithCredentials(t *testing.T) {
	var sawAuth, sawHost string
	proxy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		sawAuth, sawHost = r.Header.Get("Proxy-Authorization"), r.Host
		w.Write([]byte("203.0.113.9\n"))
	}))
	defer proxy.Close()
	old := echoURLs
	echoURLs = []string{"http://echo.test/"}
	defer func() { echoURLs = old }()
	got, err := ExitIP(&Proxy{Server: proxy.URL, Username: "u", Password: "p@ss"})
	if err != nil || got != "203.0.113.9" || sawAuth == "" || sawHost != "echo.test" {
		t.Fatalf("got %q err %v auth %q host %q", got, err, sawAuth, sawHost)
	}
}

func TestExitIPGivesUpAfterEveryService(t *testing.T) {
	proxy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("<html>blocked</html>")) }))
	defer proxy.Close()
	old := echoURLs
	echoURLs = []string{"http://a.test/", "http://b.test/"}
	defer func() { echoURLs = old }()
	if _, err := ExitIP(&Proxy{Server: proxy.URL}); err == nil || !strings.Contains(err.Error(), "no echo service answered") {
		t.Fatalf("err = %v", err)
	}
}

func TestGenArgsKeepTheOldOrderAndAddTheExitIPFlagsLast(t *testing.T) {
	old := genArgs(GenArgs{OS: "windows", Timezone: "Europe/Paris", Locale: "fr-FR", GPU: "g1", Seed: 7})
	if got := strings.Join(old, " "); got != "-m camoucrome.gen --timezone Europe/Paris --gpu g1 --os windows --locale fr-FR --seed 7" {
		t.Fatalf("args = %q", got)
	}
	got := strings.Join(genArgs(GenArgs{OS: "windows", Seed: -1, ExitIP: "192.0.2.5", GeoIPDB: "/db.mmdb"}), " ")
	if got != "-m camoucrome.gen --os windows --exit-ip=192.0.2.5 --geoip-db=/db.mmdb" {
		t.Fatalf("args = %q", got)
	}
}

func TestGenArgsCarryTheHostFlagsLast(t *testing.T) {
	got := strings.Join(genArgs(GenArgs{OS: "windows", Seed: 3, ExitIP: "192.0.2.5", HostRenderer: "ANGLE (Intel, X)", HostFonts: true}), " ")
	if got != "-m camoucrome.gen --os windows --seed 3 --exit-ip=192.0.2.5 --host-renderer=ANGLE (Intel, X) --host-fonts" {
		t.Fatalf("args = %q", got)
	}
}

func TestGenArgsCarryHostPlatformVersion(t *testing.T) {
	got := strings.Join(genArgs(GenArgs{OS: "windows", Seed: -1, HostPlatformVersion: "15.0.0"}), " ")
	if got != "-m camoucrome.gen --os windows --host-platform-version=15.0.0" {
		t.Fatalf("args = %q", got)
	}
}

func TestGenArgsCarryHostDisplay(t *testing.T) {
	got := strings.Join(genArgs(GenArgs{OS: "windows", Seed: -1, HostDisplay: `{"gamut":"p3"}`}), " ")
	if got != `-m camoucrome.gen --os windows --host-display={"gamut":"p3"}` {
		t.Fatalf("args = %q", got)
	}
}

func TestParseGeneratedToleratesWarnings(t *testing.T) {
	raw := []byte(`{"config":{"a":1},"launch":{"window":[1,2],"dpr":1},"warnings":["host GPU unknown"]}`)
	if _, err := ParseGenerated(raw); err != nil {
		t.Fatal(err)
	}
	if w := generatedWarnings(raw); len(w) != 1 || w[0] != "host GPU unknown" {
		t.Fatalf("warnings = %q", w)
	}
}

func TestExitIPShortFormServerMeansHTTP(t *testing.T) {
	proxy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("203.0.113.9\n")) }))
	defer proxy.Close()
	old := echoURLs
	echoURLs = []string{"http://echo.test/"}
	defer func() { echoURLs = old }()
	got, err := ExitIP(&Proxy{Server: strings.TrimPrefix(proxy.URL, "http://")})
	if err != nil || got != "203.0.113.9" {
		t.Fatalf("got %q err %v", got, err)
	}
}

func TestExitIPMakesNoConnectionThroughANonHTTPProxy(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer ln.Close()
	conns := 0
	go func() {
		for {
			c, err := ln.Accept()
			if err != nil {
				return
			}
			conns++
			c.Close()
		}
	}()
	for _, scheme := range []string{"https", "socks5"} {
		_, err := ExitIP(&Proxy{Server: scheme + "://" + ln.Addr().String(), Username: "uuu", Password: "ppp"})
		want := "through a " + scheme + " proxy (only http)"
		if err == nil || !strings.Contains(err.Error(), want) || strings.Contains(err.Error(), "uuu") || strings.Contains(err.Error(), "ppp") || strings.Contains(err.Error(), "127.0.0.1") {
			t.Fatalf("%s: err = %v", scheme, err)
		}
	}
	if conns != 0 {
		t.Fatalf("%d connections made", conns)
	}
}

func TestCheckGeoIPNoJSONHintNamesThePackages(t *testing.T) {
	stubs(t, "192.0.2.5", nil, "Traceback ...", nil)
	got := CheckGeoIP(Options{Config: map[string]any{"timezone:id": "Asia/Tokyo"}, GeoIP: "/db.mmdb", Python: "py"})
	if len(got) != 1 || !strings.Contains(got[0], "maxminddb and timezonefinder installed for py") {
		t.Fatalf("got %v", got)
	}
}

func TestGenArgsCarryTheProbeExecutable(t *testing.T) {
	got := strings.Join(genArgs(GenArgs{OS: "windows", Seed: -1, ProbeExecutable: `C:\chrome.exe`}), " ")
	if got != `-m camoucrome.gen --os windows --probe-executable=C:\chrome.exe` {
		t.Fatalf("args = %q", got)
	}
}
