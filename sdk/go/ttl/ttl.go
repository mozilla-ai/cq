// Package ttl parses the duration grammar shared by the cq platform's
// API-key TTL field. The grammar is a strict subset of Go's
// time.ParseDuration: a single positive ASCII integer followed by
// exactly one unit suffix from {s, m, h, d}. Zero is rejected because
// a zero-TTL key is meaningless. Parsing is case-insensitive on input
// but always returns the canonical lower-case form so the value the
// platform validates and persists is unambiguous regardless of which
// client emitted it.
package ttl

import (
	"errors"
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// Max is the upper bound the platform accepts for an API-key TTL.
// Values whose total duration exceeds Max are rejected; the constant is
// exported so callers can quote it in --help text or error messages
// without the string literal drifting between client and server.
const Max = 365 * 24 * time.Hour

// canonicalMax is the canonical lower-case rendering of Max, embedded
// in user-facing error messages so the wording matches the on-wire
// grammar.
const canonicalMax = "365d"

// maxInputLen caps the raw input length so a caller cannot make the
// parser scan or allocate over a multi-megabyte string. The longest
// legitimate input is "31536000s" (9 chars) plus surrounding
// whitespace; the bound here is generous enough to tolerate that
// without forcing callers to pre-strip and tight enough that an
// attacker cannot weaponise length. Inputs longer than this are
// rejected before any case-folding, regexp, or numeric parse runs.
const maxInputLen = 64

// maxCanonicalLen caps the canonical (post-trim, post-lower) input
// length so a caller cannot pad a small value with leading zeros to
// inflate the digit run past the platform's contract. The longest
// legitimate canonical value is "31536000s" (9 chars). The bound
// here matches sdk/python/cq.ttl so the two parsers agree on which
// values they reject as too long; without this cap an input like
// "00000000000000001d" would be accepted by Go and rejected by
// Python.
const maxCanonicalLen = 16

// ErrEmpty is returned by Parse when the input is empty or whitespace.
var ErrEmpty = errors.New("ttl is required")

// ErrGrammar is returned by Parse when the input does not match
// <integer><s|m|h|d>. Callers can compare with errors.Is to distinguish
// grammar errors from non-positive or over-cap values.
var ErrGrammar = errors.New("not a valid duration: expected <integer><s|m|h|d>, e.g. 30d, 12h")

// ErrTooLarge is returned by Parse when the input parses to a duration
// that exceeds Max.
var ErrTooLarge = errors.New("exceeds the maximum of " + canonicalMax)

// ErrTooSmall is returned by Parse when the input parses to zero. The
// platform rejects zero-TTL keys because they are meaningless (expired
// on issue), so the SDK rejects them up-front rather than letting the
// platform return a 422.
var ErrTooSmall = errors.New("must be greater than zero")

// pattern matches the canonical (lower-case) grammar after the input
// has been trimmed and lower-cased. Inputs are normalised before
// matching so "3D", " 3d", and "3d" are all accepted equivalently.
var pattern = regexp.MustCompile(`^[0-9]+[smhd]$`)

// Parse normalises s and returns the canonical lower-case form along
// with the parsed duration. It wraps one of:
//   - ErrEmpty when s is blank,
//   - ErrGrammar when s does not match <integer><s|m|h|d>,
//   - ErrTooSmall when s parses to zero,
//   - ErrTooLarge when s parses to a duration above Max or its
//     canonical length exceeds maxCanonicalLen.
//
// Callers should send the returned canonical string on the wire so the
// platform's stored value is independent of the input casing.
func Parse(s string) (string, time.Duration, error) {
	if len(s) > maxInputLen {
		// Truncate before quoting so the error message can never echo
		// an attacker-controlled megabyte-long input back into logs.
		return "", 0, fmt.Errorf("%q: %w", s[:maxInputLen], ErrTooLarge)
	}

	canonical := strings.ToLower(strings.TrimSpace(s))

	if canonical == "" {
		return "", 0, ErrEmpty
	}

	if len(canonical) > maxCanonicalLen {
		// The raw input is already <= maxInputLen so quoting s is
		// safe and matches the user's actual keystrokes.
		return "", 0, fmt.Errorf("%q: %w", s, ErrTooLarge)
	}

	if !pattern.MatchString(canonical) {
		return "", 0, fmt.Errorf("%q: %w", s, ErrGrammar)
	}

	// pattern guarantees at least one digit followed by exactly one
	// unit byte, so the slice operations below are safe. ParseInt only
	// fails when the digit run overflows int64; treat that as exceeding
	// Max because it trivially does.
	digits := canonical[:len(canonical)-1]
	unit := canonical[len(canonical)-1]

	value, err := strconv.ParseInt(digits, 10, 64)
	if err != nil {
		return "", 0, fmt.Errorf("%q: %w", s, ErrTooLarge)
	}

	if value == 0 {
		return "", 0, fmt.Errorf("%q: %w", s, ErrTooSmall)
	}

	unitDuration := unitDurationFor(unit)
	if value > int64(Max/unitDuration) {
		return "", 0, fmt.Errorf("%q: %w", s, ErrTooLarge)
	}

	return canonical, time.Duration(value) * unitDuration, nil
}

// unitDurationFor returns the duration of a single unit. The unit byte
// is guaranteed to be one of {s, m, h, d} by the caller's regexp; any
// other value would be a programmer error.
func unitDurationFor(unit byte) time.Duration {
	switch unit {
	case 's':
		return time.Second
	case 'm':
		return time.Minute
	case 'h':
		return time.Hour
	case 'd':
		return 24 * time.Hour
	}

	panic(fmt.Sprintf("ttl: unreachable unit %q", unit))
}
