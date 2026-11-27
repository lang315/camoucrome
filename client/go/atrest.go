package camoucrome

// What a launch leaves behind: owner-only profile dirs, the sweep of a killed
// client's temp dirs, and the browser stderr redacted out of an error. The
// Python (camoucrome/atrest.py) and Node (atrest.js) clients do the same;
// core/atrest.go carries the sweep for the driverless path.

import (
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"strconv"
	"strings"
	"time"

	"github.com/mxschmitt/playwright-go"
)

const (
	staleAfter = time.Hour // since the dir last changed
	redacted   = "<redacted>"
)

var (
	// camoucrome-<pid>-<rand> (a temp profile) and camoucrome-crash-<pid>-<rand>, <pid> the launching client's.
	// The scripts' own camoucrome-<word>- dirs and the pid-less names of older clients never match.
	ownedName = regexp.MustCompile(`^camoucrome-(?:crash-)?([0-9]+)-[^/\\]+$`)
	rawEnv    = regexp.MustCompile(`^CAMOU_(CONFIG|PRESET)(_[0-9]+)?$`)
	shouldBe  = regexp.MustCompile(`(It should be ).+?(\. Not repaired)`)
	quoted    = regexp.MustCompile(`(invariant )?'[^'\n]*'`)
	// A quoted segment shaped like a key name (every settings/keys.json name is) is kept on a camoucfg: line
	// unless it is a configured value, and so is an invariant id: both are public constants the operator needs.
	keyShaped = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_]*(?:[.:][A-Za-z0-9_]+)+$`)
)

// MkdirTemp makes a temp dir named for this process (kind "" for a profile,
// "crash-" for crash dumps), so Sweep can tell a killed client's leftovers
// from a live one's. os.MkdirTemp makes it 0700.
func MkdirTemp(kind string) (string, error) {
	return os.MkdirTemp("", fmt.Sprintf("camoucrome-%s%d-", kind, os.Getpid()))
}

// Sweep removes the temp profiles and crash dirs a killed client left (a
// profile holds Preferences with the identity's languages; a crash dir,
// minidumps with CAMOU_CONFIG). Only this client family's names; never keep
// (the caller's profile) or a dir that holds it. Liveness: the client's pid is in the name, so one
// kill(0) / OpenProcess per candidate, no file to open, and a pid that names
// any live process keeps the dir; a profile is kept too while its
// SingletonLock / lockfile says a browser outlived the client. Failures are
// ignored.
func Sweep(keep string) {
	root := os.TempDir()
	var spared []os.FileInfo
	if keep != "" {
		var ok bool
		if spared, ok = protectedDirs(keep); !ok {
			return // never delete on doubt
		}
	}
	ents, err := os.ReadDir(root)
	if err != nil {
		return
	}
	for _, e := range ents {
		m := ownedName.FindStringSubmatch(e.Name())
		d := filepath.Join(root, e.Name())
		if m == nil {
			continue
		}
		fi, err := os.Lstat(d)
		if err != nil || !fi.IsDir() || time.Since(fi.ModTime()) < staleAfter || !ownedByMe(fi) ||
			slices.ContainsFunc(spared, func(k os.FileInfo) bool { return os.SameFile(k, fi) }) {
			continue
		}
		if pid, err := strconv.Atoi(m[1]); err != nil || alive(pid) || browserRunning(d) {
			continue
		}
		os.RemoveAll(d) // one pass: a locked dir must not stall the launch
	}
}

func joinedEnv(env map[string]string, name string) string {
	if v, ok := env[name]; ok {
		return v
	}
	var b strings.Builder
	for n := 1; ; n++ {
		v, ok := env[fmt.Sprintf("%s_%d", name, n)]
		if !ok {
			return b.String()
		}
		b.WriteString(v)
	}
}

func leaves(v any, out map[string]bool) {
	switch x := v.(type) {
	case map[string]any:
		for _, y := range x {
			leaves(y, out)
		}
	case []any:
		for _, y := range x {
			leaves(y, out)
		}
	case string:
		out[x] = true
	case json.Number:
		out[x.String()] = true
	case bool:
		out[strconv.FormatBool(x)] = true
	}
}

func isWord(b byte) bool {
	return b == '_' || '0' <= b && b <= '9' || 'a' <= b && b <= 'z' || 'A' <= b && b <= 'Z'
}

// replaceToken replaces every occurrence of w that stands as a whole token (RE2 has no lookbehind).
func replaceToken(line, w string) string {
	var b strings.Builder
	from := 0
	for i := 0; ; {
		j := strings.Index(line[i:], w)
		if j == -1 {
			break
		}
		j += i
		end := j + len(w)
		if (j == 0 || !isWord(line[j-1])) && (end == len(line) || !isWord(line[end])) {
			b.WriteString(line[from:j])
			b.WriteString(redacted)
			from, i = end, end
		} else {
			i = j + 1
		}
	}
	b.WriteString(line[from:])
	return b.String()
}

// Redact returns text (the browser's stderr, or an error that carries it)
// with the identity taken out, line structure kept: every CAMOU_CONFIG* /
// CAMOU_PRESET* string of env; every config and preset value of 3+ bytes
// where it stands as a whole token; and on a camoucfg: log line, every quoted
// segment that is neither a key name nor an invariant id, plus a validator's
// unquoted "It should be <value>." (a derived value no config leaf holds).
func Redact(text string, env map[string]string) string {
	var raws []string
	for k, v := range env {
		if v != "" && rawEnv.MatchString(k) {
			raws = append(raws, v)
		}
	}
	keys, vals := map[string]bool{}, map[string]bool{}
	for _, name := range []string{"CAMOU_CONFIG", "CAMOU_PRESET"} {
		dec := json.NewDecoder(strings.NewReader(joinedEnv(env, name)))
		dec.UseNumber()
		var doc any
		if dec.Decode(&doc) != nil {
			continue
		}
		if m, ok := doc.(map[string]any); ok {
			for k := range m {
				keys[k] = true
			}
		}
		leaves(doc, vals)
	}
	var words []string
	for v := range vals {
		if len(v) >= 3 && !keys[v] {
			words = append(words, v)
		}
	}
	longestFirst := func(a, b string) int { return len(b) - len(a) }
	slices.SortFunc(raws, longestFirst)
	slices.SortFunc(words, longestFirst)
	lines := strings.Split(text, "\n")
	for i, line := range lines {
		for _, r := range raws {
			line = strings.ReplaceAll(line, r, redacted)
		}
		if strings.Contains(line, "camoucfg:") {
			line = shouldBe.ReplaceAllString(line, "${1}"+redacted+"${2}")
			line = quoted.ReplaceAllStringFunc(line, func(q string) string {
				v := q[strings.IndexByte(q, '\'')+1 : len(q)-1]
				if strings.HasPrefix(q, "invariant ") || keys[v] || keyShaped.MatchString(v) && !vals[v] {
					return q
				}
				return "'" + redacted + "'"
			})
		}
		for _, w := range words {
			line = replaceToken(line, w)
		}
		lines[i] = line
	}
	return strings.Join(lines, "\n")
}

// redactedError carries a launch error's redacted text. errors.Is and
// errors.As see through it to the original chain (context.DeadlineExceeded,
// the driver's *playwright.Error, redacted in place), but it has no Unwrap:
// a wrapper in between (fmt.Errorf's) holds the text unredacted, and
// errors.Unwrap would hand it out.
type redactedError struct {
	msg  string
	orig error
}

func (e *redactedError) Error() string        { return e.msg }
func (e *redactedError) Is(target error) bool { return errors.Is(e.orig, target) }
func (e *redactedError) As(target any) bool   { return errors.As(e.orig, target) }

// redactErr returns err with the browser stderr's identity taken out of its
// text; err itself when there is nothing to take out.
func redactErr(err error, env map[string]string) error {
	if err == nil {
		return nil
	}
	var pw *playwright.Error
	if errors.As(err, &pw) {
		pw.Message, pw.Stack = Redact(pw.Message, env), Redact(pw.Stack, env)
	}
	msg := Redact(err.Error(), env)
	if msg == err.Error() {
		return err
	}
	return &redactedError{msg, err}
}

// protectedDirs returns keep, resolved, and every dir above it, so Sweep
// spares a candidate that is the caller's dir or holds it however either is
// spelled (a symlink, /var vs /private/var, an 8.3 name, case): os.SameFile
// compares identities, not paths. keep may not exist yet; its deepest
// existing ancestor stands in. ok is false on any doubt.
func protectedDirs(keep string) (dirs []os.FileInfo, ok bool) {
	p, err := filepath.Abs(keep)
	if err != nil {
		return nil, false
	}
	for {
		_, err := os.Stat(p)
		if err == nil {
			break
		}
		if !errors.Is(err, fs.ErrNotExist) || filepath.Dir(p) == p {
			return nil, false
		}
		p = filepath.Dir(p)
	}
	if p, err = filepath.EvalSymlinks(p); err != nil {
		return nil, false
	}
	for {
		fi, err := os.Stat(p)
		if err != nil {
			return nil, false
		}
		dirs = append(dirs, fi)
		if filepath.Dir(p) == p {
			return dirs, true
		}
		p = filepath.Dir(p)
	}
}
