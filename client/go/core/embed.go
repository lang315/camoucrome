package core

import (
	"bytes"
	"compress/gzip"
	"embed"
	"encoding/json"
	"fmt"
	"io"
	"sync"

	_ "time/tzdata" // zoneinfo for time.LoadLocation: Windows has none of its own
)

//go:embed data/pool-windows.json.gz data/voices.json data/fonts.json data/country_locale.json data/locale_zones.json data/igpu-floors.json data/version.json
var dataFS embed.FS

// poolFormat is the Identity.Version this code reads and writes.
const poolFormat = 1

type poolFile struct {
	Version int               `json:"version"`
	OS      string            `json:"os"`
	Entries []json.RawMessage `json:"entries"`
}

var (
	poolOnce sync.Once
	poolData poolFile
	poolErr  error

	tablesOnce sync.Once
	tables     struct {
		fonts     fontsData
		voices    map[string]json.RawMessage // OS -> rows (Windows only)
		voiceTags []string                   // Windows row tags in file order: "first row of the same language" depends on it
		remote    []any
		country   map[string]string
		zones     map[string][]string // locale -> zones, first is the default
		floors    map[string]int      // "Intel:0x00009A49" -> fewest threads of the CPU family that iGPU ships with
		err       error
	}
)

func pool() (*poolFile, error) {
	poolOnce.Do(func() {
		f, err := dataFS.Open("data/pool-windows.json.gz")
		if err != nil {
			poolErr = err
			return
		}
		defer f.Close()
		zr, err := gzip.NewReader(f)
		if err != nil {
			poolErr = err
			return
		}
		b, err := io.ReadAll(zr)
		if err != nil {
			poolErr = err
			return
		}
		if poolErr = json.Unmarshal(b, &poolData); poolErr == nil && (poolData.Version != poolFormat || len(poolData.Entries) == 0) {
			poolErr = fmt.Errorf("embedded pool has format %d and %d entries", poolData.Version, len(poolData.Entries))
		}
	})
	return &poolData, poolErr
}

func readJSON(name string, v any) error {
	b, err := dataFS.ReadFile("data/" + name)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, v)
}

// objectKeys is the keys of a JSON object in file order.
func objectKeys(raw []byte) ([]string, error) {
	d := json.NewDecoder(bytes.NewReader(raw))
	if t, err := d.Token(); err != nil || t != json.Delim('{') {
		return nil, fmt.Errorf("not a JSON object")
	}
	var keys []string
	for d.More() {
		t, err := d.Token()
		if err != nil {
			return nil, err
		}
		keys = append(keys, t.(string))
		var skip json.RawMessage
		if err := d.Decode(&skip); err != nil {
			return nil, err
		}
	}
	return keys, nil
}

func loadTables() error {
	tablesOnce.Do(func() {
		t := &tables
		var vf struct {
			Windows json.RawMessage `json:"Windows"`
			Remote  []any           `json:"remote"`
		}
		b, err := dataFS.ReadFile("data/voices.json")
		if err != nil {
			t.err = err
			return
		}
		if t.err = json.Unmarshal(b, &vf); t.err != nil {
			return
		}
		t.remote = vf.Remote
		if t.err = json.Unmarshal(vf.Windows, &t.voices); t.err != nil {
			return
		}
		if t.voiceTags, t.err = objectKeys(vf.Windows); t.err != nil {
			return
		}
		if t.err = readJSON("fonts.json", &t.fonts); t.err != nil {
			return
		}
		if t.err = readJSON("country_locale.json", &t.country); t.err != nil {
			return
		}
		if t.err = readJSON("locale_zones.json", &t.zones); t.err != nil {
			return
		}
		t.err = readJSON("igpu-floors.json", &t.floors)
	})
	return tables.err
}

func jsonUnmarshal(b []byte, v any) error { return json.Unmarshal(b, v) }
