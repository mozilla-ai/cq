package mcpserver

import (
	"errors"
	"fmt"
	"net/http"

	"github.com/mark3labs/mcp-go/mcp"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// unreachableUnitResult explains a not-found answer from the evidence path and
// names the verb that applies instead, or returns nil when err is something
// else.
//
// Confirmations and flags attach evidence to a unit, which only a unit in
// circulation can carry. A unit awaiting review is therefore reported as
// absent, and an agent that just proposed it cannot tell that apart from a bad
// ID without being told.
func unreachableUnitResult(unitID string, err error) *mcp.CallToolResult {
	var remoteErr *cq.RemoteError
	if !errors.As(err, &remoteErr) || remoteErr.StatusCode != http.StatusNotFound {
		return nil
	}

	return mcp.NewToolResultError(fmt.Sprintf(
		"knowledge unit %s is not available for confirmations or flags. "+
			"A unit awaiting review carries no evidence to dispute. "+
			"If you proposed this unit yourself and it is wrong, use revoke to withdraw it.",
		unitID,
	))
}

// unrevokableUnitResult explains a not-found answer from the withdrawal path,
// or returns nil when err is something else.
//
// A node that implements no author-scoped withdrawal endpoint answers exactly
// as one that holds no such unit, so the message has to name both causes
// rather than assert either.
func unrevokableUnitResult(unitID string, err error) *mcp.CallToolResult {
	var remoteErr *cq.RemoteError
	if !errors.As(err, &remoteErr) || remoteErr.StatusCode != http.StatusNotFound {
		return nil
	}

	return mcp.NewToolResultError(fmt.Sprintf(
		"knowledge unit %s could not be withdrawn. Either you did not propose it, "+
			"or the configured knowledge store does not support withdrawing a unit.",
		unitID,
	))
}
