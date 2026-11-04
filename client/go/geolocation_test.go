package camoucrome

import (
	"errors"
	"reflect"
	"testing"
)

func TestLaunchGrantsGeolocationOnlyWithBothCoordinates(t *testing.T) {
	perms := func(o Options) []string {
		f := &fakeLauncher{err: errors.New("stop here")}
		launch(f, o)
		return f.opts.Permissions
	}
	both := map[string]any{"geolocation:latitude": 1.5, "geolocation:longitude": 2.5}
	if got := perms(Options{Config: both}); !reflect.DeepEqual(got, []string{"geolocation"}) {
		t.Errorf("both coordinates: %v", got)
	}
	if got := perms(Options{Config: both, Permissions: []string{"notifications"}}); !reflect.DeepEqual(got, []string{"notifications", "geolocation"}) {
		t.Errorf("merged: %v", got)
	}
	if got := perms(Options{Config: both, Permissions: []string{"geolocation", "notifications"}}); !reflect.DeepEqual(got, []string{"geolocation", "notifications"}) {
		t.Errorf("duplicate: %v", got)
	}
	if got := perms(Options{Config: `{"geolocation:latitude":1.5,"geolocation:longitude":2.5}`}); !reflect.DeepEqual(got, []string{"geolocation"}) {
		t.Errorf("JSON string config: %v", got)
	}
	for _, c := range []map[string]any{{"geolocation:latitude": 1.5}, {"geolocation:longitude": 2.5}, {"a": 1}} {
		if got := perms(Options{Config: c}); got != nil {
			t.Errorf("%v granted %v", c, got)
		}
	}
	if got := perms(Options{Config: map[string]any{"a": 1}, Permissions: []string{"notifications"}}); !reflect.DeepEqual(got, []string{"notifications"}) {
		t.Errorf("callers list: %v", got)
	}
}

func TestLaunchWarnsOfAProxyWithoutGeoIP(t *testing.T) {
	const want = "a proxy without geoip: timezone, locale and geolocation are not checked against the exit IP"
	warned := func(o Options) []string {
		var got []string
		o.Warn = func(m string) { got = append(got, m) }
		launch(&fakeLauncher{err: errors.New("stop here")}, o)
		return got
	}
	p := &Proxy{Server: "http://p.example:8080"}
	if got := warned(Options{Proxy: p}); !reflect.DeepEqual(got, []string{want}) {
		t.Errorf("proxy without geoip warned %v", got)
	}
	if got := warned(Options{}); got != nil {
		t.Errorf("no proxy warned %v", got)
	}
	stubs(t, "192.0.2.5", nil, `{"warning":null}`, nil)
	if got := warned(Options{Proxy: p, GeoIP: "/db.mmdb", ExitIP: "192.0.2.5", Config: map[string]any{"timezone:id": "America/New_York"}}); got != nil {
		t.Errorf("geoip set warned %v", got)
	}
}
