package cq

import (
	"errors"
	"fmt"
)

// RemoteError is returned when the remote API explicitly rejects a request.
type RemoteError struct {
	StatusCode int
	Detail     string
}

// ErrNotFound indicates a knowledge unit was not found.
var ErrNotFound = errors.New("knowledge unit not found")

// Error returns a human-readable description of the remote API rejection.
func (e *RemoteError) Error() string {
	return fmt.Sprintf("remote API rejected request (%d): %s", e.StatusCode, e.Detail)
}
