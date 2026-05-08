package auth

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
)

// pkceVerifierBytes is the number of random bytes drawn for a PKCE verifier.
// 32 bytes encode to 43 base64url characters (no padding), the minimum
// length permitted by RFC 7636 §4.1, and well below the 128-character cap.
const pkceVerifierBytes = 32

// pkce holds an RFC 7636 verifier/challenge pair: the verifier is a random
// high-entropy string the client retains; the challenge is its SHA-256
// hash, sent to the authorization server.
type pkce struct {
	// verifier is the secret kept by the client; sent only to the token
	// exchange endpoint and never to the authorization endpoint.
	verifier string

	// challenge is base64url-encoded SHA-256 of the verifier (no padding),
	// sent on the authorization request as "code_challenge".
	challenge string
}

// newPKCE returns a fresh PKCE pair, drawing entropy from crypto/rand.
func newPKCE() (pkce, error) {
	raw := make([]byte, pkceVerifierBytes)
	if _, err := rand.Read(raw); err != nil {
		return pkce{}, fmt.Errorf("generating pkce verifier: %w", err)
	}

	verifier := base64.RawURLEncoding.EncodeToString(raw)
	sum := sha256.Sum256([]byte(verifier))
	challenge := base64.RawURLEncoding.EncodeToString(sum[:])

	return pkce{verifier: verifier, challenge: challenge}, nil
}
