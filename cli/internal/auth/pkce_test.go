package auth

import (
	"crypto/sha256"
	"encoding/base64"
	"regexp"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

// base64URLAlphabet is the RFC 4648 §5 alphabet allowed in a PKCE verifier
// and challenge: ALPHA / DIGIT / "-" / "." / "_" / "~". RFC 7636 §4.1
// permits the unreserved set; the challenge specifically uses base64url
// without padding.
var base64URLAlphabet = regexp.MustCompile(`^[A-Za-z0-9\-._~]+$`)

func TestNewPKCE_VerifierLengthIsBetween43And128(t *testing.T) {
	for range 100 {
		p, err := newPKCE()
		require.NoError(t, err)
		require.GreaterOrEqual(t, len(p.verifier), 43)
		require.LessOrEqual(t, len(p.verifier), 128)
	}
}

func TestNewPKCE_VerifierUsesAllowedAlphabet(t *testing.T) {
	for range 100 {
		p, err := newPKCE()
		require.NoError(t, err)
		require.Regexp(t, base64URLAlphabet, p.verifier)
	}
}

func TestNewPKCE_ChallengeIsSHA256OfVerifierBase64URLNoPadding(t *testing.T) {
	p, err := newPKCE()
	require.NoError(t, err)

	sum := sha256.Sum256([]byte(p.verifier))
	want := base64.RawURLEncoding.EncodeToString(sum[:])

	require.Equal(t, want, p.challenge)
	require.Len(t, p.challenge, 43)
	require.False(t, strings.Contains(p.challenge, "="))
}

func TestNewPKCE_TwoCallsProduceDifferentVerifiers(t *testing.T) {
	a, err := newPKCE()
	require.NoError(t, err)

	b, err := newPKCE()
	require.NoError(t, err)

	require.NotEqual(t, a.verifier, b.verifier)
	require.NotEqual(t, a.challenge, b.challenge)
}
