package cq

import (
	"errors"
	"fmt"
)

// ErrNotFound indicates a knowledge unit was not found.
var ErrNotFound = errors.New("knowledge unit not found")

// FallbackError indicates that a propose could not reach the remote and the
// unit was stored locally instead. It will drain on the next successful
// connection. Err carries the underlying error (RemoteError for auth
// rejection, errUnreachable-wrapped error for transport/5xx).
type FallbackError struct {
	LocalUnit KnowledgeUnit
	Err       error
}

// RemoteError is returned when the remote API explicitly rejects a request.
type RemoteError struct {
	StatusCode int
	Detail     string
}

// Error returns a description indicating local storage after remote failure.
func (e *FallbackError) Error() string {
	return fmt.Sprintf("stored locally after remote failure: %s", e.Err)
}

// Unwrap returns the underlying error so errors.As/errors.Is chain through.
func (e *FallbackError) Unwrap() error {
	return e.Err
}

// Error returns a human-readable description of the remote API rejection.
func (e *RemoteError) Error() string {
	return fmt.Sprintf("remote API rejected request (%d): %s", e.StatusCode, e.Detail)
}
