package camoucrome

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"strings"
	"time"
)

// Item 13, launch side. The lookup lives once, in Python (camoucrome.geoip: a DB-IP Lite or GeoLite2-layout .mmdb,
// the zone from the coordinates); Go execs it, as it does camoucrome.gen. IP Geolocation by DB-IP.

// echoURLs are asked one after another, through the proxy when there is one; the service sees only the exit address.
var echoURLs = []string{"https://api.ipify.org", "https://checkip.amazonaws.com", "https://icanhazip.com", "https://ifconfig.co/ip"}

// Seams for the tests.
var (
	echoIP     = ExitIP
	execPython = func(python string, args ...string) ([]byte, error) {
		out, err := exec.Command(python, args...).Output()
		if _, isExit := err.(*exec.ExitError); isExit {
			return out, nil // exit 2 still prints {"error": ...} on stdout
		}
		return out, err
	}
)

// ExitIP is the address the world sees: an echo service asked through the proxy (nil = direct).
func ExitIP(p *Proxy) (string, error) {
	transport := &http.Transport{}
	if p != nil {
		server := p.Server
		if !strings.Contains(server, "://") {
			server = "http://" + server // Playwright's short form
		}
		u, err := url.Parse(server)
		if err != nil {
			return "", errors.New("the proxy server is not a URL")
		}
		if u.Scheme != "http" { // https would send the credentials before TLS here, socks is not spoken; the clients agree
			return "", fmt.Errorf("the exit IP cannot be asked through a %s proxy (only http)", u.Scheme)
		}
		if p.Username != "" {
			u.User = url.UserPassword(p.Username, p.Password)
		}
		transport.Proxy = http.ProxyURL(u)
	}
	client := &http.Client{Transport: transport, Timeout: 5 * time.Second}
	var errs []string
	for _, e := range echoURLs {
		resp, err := client.Get(e)
		if err != nil {
			errs = append(errs, e+": "+err.Error())
			continue
		}
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 200))
		resp.Body.Close()
		if ip := strings.TrimSpace(string(body)); net.ParseIP(ip) != nil {
			return ip, nil
		}
		errs = append(errs, e+": not an address")
	}
	return "", fmt.Errorf("no echo service answered (%s)", strings.Join(errs, "; "))
}

// CheckGeoIP is the warnings about the config's timezone:id against the exit address; it never fails the launch and
// never changes the config. Nothing to check (no timezone:id) gives none.
func CheckGeoIP(o Options) []string {
	cfg, err := effectiveKeys(o.Config, o.Preset)
	if err != nil {
		return nil // the launch reports a bad config itself
	}
	zone, _ := cfg["timezone:id"].(string)
	if zone == "" {
		return nil
	}
	cannot := func(why string) []string {
		return []string{fmt.Sprintf("timezone:id %s could not be checked against the exit IP: %s", zone, why)}
	}
	ip := o.ExitIP
	if ip == "" {
		var err error
		if ip, err = echoIP(o.Proxy); err != nil {
			return cannot(err.Error())
		}
	}
	python := o.Python
	if python == "" {
		python = "python3"
	}
	out, err := execPython(python, "-m", "camoucrome.geoip", "--ip="+ip, "--db="+o.GeoIP, "--check-zone="+zone)
	if err != nil {
		return cannot(err.Error())
	}
	var r struct {
		Error   string  `json:"error"`
		Warning *string `json:"warning"`
	}
	if json.Unmarshal(out, &r) != nil {
		return cannot("camoucrome.geoip printed no JSON (are maxminddb and timezonefinder installed for " + python + "?)")
	}
	if r.Error != "" {
		return cannot(r.Error)
	}
	if r.Warning != nil {
		return []string{*r.Warning}
	}
	return nil
}

func (o Options) warn(msgs []string) {
	for _, m := range msgs {
		if o.Warn != nil {
			o.Warn(m)
		} else {
			fmt.Fprintln(os.Stderr, "camoucrome: "+m)
		}
	}
}
