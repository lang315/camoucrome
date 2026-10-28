package rodclient

import "strings"

type usKeyInfo struct {
	key, code, text string
	vk, mod         int
}

const shiftBit = 8

// Unshifted punctuation of a US layout: rune -> code, virtual key.
var usPunct = map[rune]struct {
	code string
	vk   int
}{
	' ': {"Space", 32}, '-': {"Minus", 189}, '=': {"Equal", 187}, '[': {"BracketLeft", 219},
	']': {"BracketRight", 221}, '\\': {"Backslash", 220}, ';': {"Semicolon", 186}, '\'': {"Quote", 222},
	',': {"Comma", 188}, '.': {"Period", 190}, '/': {"Slash", 191}, '`': {"Backquote", 192},
}

// shifted punctuation -> its unshifted rune ("_+{}|:\"<>?~").
const shiftedPunct = `_+{}|:"<>?~`
const unshiftedPunct = `-=[]\;',./` + "`"

// usKey maps a rune on a US layout to its key event fields; false for runes
// off the layout.
func usKey(r rune) (usKeyInfo, bool) {
	s := string(r)
	switch {
	case r == '\n' || r == '\r':
		return usKeyInfo{"Enter", "Enter", "\r", 13, 0}, true
	case r == '\t':
		return usKeyInfo{"Tab", "Tab", "", 9, 0}, true
	case r >= 'a' && r <= 'z':
		return usKeyInfo{s, "Key" + strings.ToUpper(s), s, int(r - 'a' + 'A'), 0}, true
	case r >= 'A' && r <= 'Z':
		return usKeyInfo{s, "Key" + s, s, int(r), shiftBit}, true
	case r >= '0' && r <= '9':
		return usKeyInfo{s, "Digit" + s, s, int(r), 0}, true
	}
	if i := strings.IndexRune(")!@#$%^&*(", r); i >= 0 {
		d := string(rune('0' + i))
		return usKeyInfo{s, "Digit" + d, s, int('0') + i, shiftBit}, true
	}
	if i := strings.IndexRune(shiftedPunct, r); i >= 0 {
		base := []rune(unshiftedPunct)[i]
		return usKeyInfo{s, usPunct[base].code, s, usPunct[base].vk, shiftBit}, true
	}
	if p, ok := usPunct[r]; ok {
		return usKeyInfo{s, p.code, s, p.vk, 0}, true
	}
	return usKeyInfo{}, false
}
