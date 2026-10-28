package camoucrome

import (
	"fmt"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"testing"

	"github.com/mxschmitt/playwright-go"
)

// A real browser through a real local proxy. Skipped unless CAMOU_TEST_CHROME names a Chrome executable and
// CAMOU_TEST_GO_DRIVER the patchright-core driver directory (with PLAYWRIGHT_NODEJS_PATH set).
// Launch with a Proxy once did nothing: the field did not exist, and the --proxy-server flag is one of
// Playwright's default args, which the launcher drops. The fixture counts what reaches it.

type countingProxy struct {
	mu   sync.Mutex
	seen []string // "METHOD auth" or "METHOD noauth"
	url  string
}

func (p *countingProxy) saw(method string, authed bool) bool {
	p.mu.Lock()
	defer p.mu.Unlock()
	want := fmt.Sprintf("%s %v", method, authed)
	for _, s := range p.seen {
		if s == want {
			return true
		}
	}
	return false
}

func startProxy(t *testing.T) *countingProxy {
	p := &countingProxy{}
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	srv := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		authed := r.Header.Get("Proxy-Authorization") != ""
		if strings.Contains(r.URL.String()+r.Host, "example.test") {
			p.mu.Lock()
			p.seen = append(p.seen, fmt.Sprintf("%s %v", r.Method, authed))
			p.mu.Unlock()
		}
		if !authed {
			w.Header().Set("Proxy-Authenticate", `Basic realm="t"`)
			w.WriteHeader(http.StatusProxyAuthRequired)
			return
		}
		if r.Method == http.MethodConnect {
			w.WriteHeader(http.StatusBadGateway)
			return
		}
		w.Header().Set("Content-Type", "text/html")
		fmt.Fprint(w, "<title>via-proxy</title>ok")
	})}
	go srv.Serve(ln)
	t.Cleanup(func() { srv.Close() })
	p.url = "http://" + ln.Addr().String()
	return p
}

func visit(t *testing.T, url string, proxy *Proxy) string {
	exe, driver := os.Getenv("CAMOU_TEST_CHROME"), os.Getenv("CAMOU_TEST_GO_DRIVER")
	if exe == "" || driver == "" {
		t.Skip("set CAMOU_TEST_CHROME and CAMOU_TEST_GO_DRIVER")
	}
	pw, err := playwright.Run(&playwright.RunOptions{DriverDirectory: driver, SkipInstallBrowsers: true})
	if err != nil {
		t.Fatal(err)
	}
	defer pw.Stop()
	headless := true
	ctx, err := Launch(pw, Options{ExecutablePath: exe, Headless: &headless, Proxy: proxy})
	if err != nil {
		t.Fatal(err)
	}
	defer ctx.Close()
	page, err := ctx.NewPage()
	if err != nil {
		t.Fatal(err)
	}
	if _, err := page.Goto(url, playwright.PageGotoOptions{Timeout: playwright.Float(15000)}); err != nil {
		return "ERR " + strings.SplitN(err.Error(), "\n", 2)[0]
	}
	title, _ := page.Title()
	return title
}

func TestLiveProxyOptionReachesTheProxyAndAuthenticates(t *testing.T) {
	p := startProxy(t)
	if got := visit(t, "http://example.test/", &Proxy{Server: p.url, Username: "u", Password: "p"}); got != "via-proxy" {
		t.Fatalf("title = %q", got)
	}
	if !p.saw("GET", false) || !p.saw("GET", true) { // the 407, then the authenticated retry
		t.Fatalf("proxy saw %v", p.seen)
	}
}

func TestLiveHTTPSGoesThroughConnect(t *testing.T) {
	p := startProxy(t)
	visit(t, "https://example.test/", &Proxy{Server: p.url, Username: "u", Password: "p"})
	if !p.saw("CONNECT", true) {
		t.Fatalf("proxy saw %v", p.seen)
	}
}

func TestLiveWithoutTheOptionNothingReachesTheProxy(t *testing.T) {
	p := startProxy(t)
	if got := visit(t, "http://example.test/", nil); !strings.HasPrefix(got, "ERR") {
		t.Fatalf("title = %q", got)
	}
	if len(p.seen) != 0 {
		t.Fatalf("proxy saw %v", p.seen)
	}
}
