package ttl_test

import (
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/mozilla-ai/cq/sdk/go/ttl"
)

// TestParse covers the public Parse contract: lower-case is canonical,
// upper-case input is normalised, whitespace is trimmed, and any value
// outside the grammar or above Max is rejected with a typed error.
func TestParse(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name    string
		input   string
		want    string
		wantDur time.Duration
		wantErr error
	}{
		{name: "lower-case days", input: "30d", want: "30d", wantDur: 30 * 24 * time.Hour},
		{name: "lower-case hours", input: "12h", want: "12h", wantDur: 12 * time.Hour},
		{name: "lower-case minutes", input: "45m", want: "45m", wantDur: 45 * time.Minute},
		{name: "lower-case seconds", input: "60s", want: "60s", wantDur: 60 * time.Second},
		{name: "upper-case days canonicalised", input: "3D", want: "3d", wantDur: 3 * 24 * time.Hour},
		{name: "upper-case hours canonicalised", input: "2H", want: "2h", wantDur: 2 * time.Hour},
		{
			name:    "mixed-case rejected by grammar is impossible after normalisation",
			input:   "3D",
			want:    "3d",
			wantDur: 3 * 24 * time.Hour,
		},
		{name: "leading and trailing whitespace trimmed", input: "  90d  ", want: "90d", wantDur: 90 * 24 * time.Hour},
		{name: "leading zero accepted", input: "007d", want: "007d", wantDur: 7 * 24 * time.Hour},
		{name: "max boundary 365d accepted", input: "365d", want: "365d", wantDur: ttl.Max},
		{name: "max boundary 8760h accepted", input: "8760h", want: "8760h", wantDur: ttl.Max},
		{name: "max boundary 525600m accepted", input: "525600m", want: "525600m", wantDur: ttl.Max},
		{name: "max boundary 31536000s accepted", input: "31536000s", want: "31536000s", wantDur: ttl.Max},

		{name: "empty rejected", input: "", wantErr: ttl.ErrEmpty},
		{name: "whitespace-only rejected", input: "   ", wantErr: ttl.ErrEmpty},
		{name: "weeks rejected", input: "1w", wantErr: ttl.ErrGrammar},
		{name: "missing unit rejected", input: "30", wantErr: ttl.ErrGrammar},
		{name: "unit only rejected", input: "d", wantErr: ttl.ErrGrammar},
		{name: "wrong order rejected", input: "d30", wantErr: ttl.ErrGrammar},
		{name: "decimal rejected", input: "3.5d", wantErr: ttl.ErrGrammar},
		{name: "negative rejected", input: "-1d", wantErr: ttl.ErrGrammar},
		{name: "compound rejected", input: "1d2h", wantErr: ttl.ErrGrammar},
		{name: "months rejected", input: "3mo", wantErr: ttl.ErrGrammar},
		{name: "years rejected", input: "5y", wantErr: ttl.ErrGrammar},
		{name: "internal whitespace rejected", input: "1 d", wantErr: ttl.ErrGrammar},

		{name: "366d rejected as exceeding cap", input: "366d", wantErr: ttl.ErrTooLarge},
		{name: "8761h rejected as exceeding cap", input: "8761h", wantErr: ttl.ErrTooLarge},
		{name: "525601m rejected as exceeding cap", input: "525601m", wantErr: ttl.ErrTooLarge},
		{name: "31536001s rejected as exceeding cap", input: "31536001s", wantErr: ttl.ErrTooLarge},
		{name: "huge value out of int64 range rejected", input: "99999999999999999999d", wantErr: ttl.ErrTooLarge},

		{name: "zero days rejected", input: "0d", wantErr: ttl.ErrTooSmall},
		{name: "zero seconds rejected", input: "0s", wantErr: ttl.ErrTooSmall},
		{name: "zero with leading zeros rejected", input: "000h", wantErr: ttl.ErrTooSmall},

		{
			name:    "canonical length cap rejects padded leading zeros",
			input:   "00000000000000001d",
			wantErr: ttl.ErrTooLarge,
		},
		{name: "canonical length cap rejects 17-char digit run", input: "11111111111111111s", wantErr: ttl.ErrTooLarge},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			gotCanonical, gotDur, err := ttl.Parse(tc.input)

			if tc.wantErr != nil {
				require.Error(t, err)
				require.ErrorIs(t, err, tc.wantErr)
				require.Empty(t, gotCanonical)
				require.Zero(t, gotDur)

				return
			}

			require.NoError(t, err)
			require.Equal(t, tc.want, gotCanonical)
			require.Equal(t, tc.wantDur, gotDur)
		})
	}
}

// TestParse_QuotedInputAppearsInError pins that the wrapped error
// message includes the user's original (un-normalised) input so a UI
// surfacing the error can faithfully echo what the user typed.
func TestParse_QuotedInputAppearsInError(t *testing.T) {
	t.Parallel()

	_, _, err := ttl.Parse("1W")
	require.Error(t, err)
	require.ErrorIs(t, err, ttl.ErrGrammar)
	require.Contains(t, err.Error(), `"1W"`)
}

// TestParse_ErrorsAreSentinels confirms the four exported errors are
// distinct values so callers can dispatch on them with errors.Is.
func TestParse_ErrorsAreSentinels(t *testing.T) {
	t.Parallel()

	for _, pair := range [][2]error{
		{ttl.ErrEmpty, ttl.ErrGrammar},
		{ttl.ErrEmpty, ttl.ErrTooLarge},
		{ttl.ErrEmpty, ttl.ErrTooSmall},
		{ttl.ErrGrammar, ttl.ErrTooLarge},
		{ttl.ErrGrammar, ttl.ErrTooSmall},
		{ttl.ErrTooLarge, ttl.ErrTooSmall},
	} {
		require.False(t, errors.Is(pair[0], pair[1]))
	}
}

// TestMax_Is365Days locks the platform-supplied upper bound so a casual
// edit to the constant has to update the test deliberately.
func TestMax_Is365Days(t *testing.T) {
	t.Parallel()

	require.Equal(t, 365*24*time.Hour, ttl.Max)
}

// TestParse_LengthCapDefendsAgainstUnboundedInput pins that the parser
// rejects very long inputs up-front (before regex/normalisation runs)
// so a malicious caller cannot make Parse do CPU work proportional to
// a multi-megabyte digit run. The error is wrapped as ErrTooLarge
// because the underlying intent (a bigger-than-Max value) is the same.
func TestParse_LengthCapDefendsAgainstUnboundedInput(t *testing.T) {
	t.Parallel()

	huge := strings.Repeat("9", 1<<20) + "d"
	canonical, dur, err := ttl.Parse(huge)
	require.Error(t, err)
	require.ErrorIs(t, err, ttl.ErrTooLarge)
	require.Empty(t, canonical)
	require.Zero(t, dur)
	// The error message must not echo the entire attacker-controlled
	// input back; truncation is part of the contract so logs stay sane.
	require.Less(t, len(err.Error()), 256)
}
