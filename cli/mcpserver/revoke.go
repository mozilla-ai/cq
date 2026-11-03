package mcpserver

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/mark3labs/mcp-go/mcp"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// RevokeTool returns the MCP tool definition for revoke.
func RevokeTool() mcp.Tool {
	return mcp.NewTool("revoke",
		mcp.WithDescription(
			"Withdraw a knowledge unit you proposed yourself, after discovering it was wrong. "+
				"Use revoke for your own units and flag for units proposed by someone else: "+
				"a unit still awaiting review carries no evidence to dispute, so flag does not apply to it. "+
				"A unit held only locally is deleted rather than withdrawn, which cannot be undone.",
		),
		mcp.WithString("unit_id",
			mcp.Required(),
			mcp.Description("ID of the knowledge unit to revoke (returned by propose or query)."),
		),
	)
}

// revokeOutcome reports what withdrawing a unit actually did.
//
// Withdrawing a remote unit changes its review status and leaves it readable.
// Withdrawing a local unit deletes it, so naming the two apart keeps an agent
// from citing or re-confirming a record that no longer exists.
type revokeOutcome struct {
	// UnitID is the unit that was withdrawn.
	UnitID string `json:"unit_id"`

	// Action is either "deleted_local" or "revoked_remote".
	Action string `json:"action"`
}

// HandleRevoke withdraws a knowledge unit on behalf of its author.
func (s *Server) HandleRevoke(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	unitID, err := req.RequireString("unit_id")
	if err != nil {
		return mcp.NewToolResultError("unit_id is required"), nil
	}

	if err := cq.ValidateID(unitID); err != nil {
		return mcp.NewToolResultError(err.Error()), nil
	}

	action := "deleted_local"
	result, err := s.client.Revoke(ctx, cq.KnowledgeUnit{ID: unitID, Tier: cq.Local})
	if errors.Is(err, cq.ErrNotFound) {
		action = "revoked_remote"
		result, err = s.client.Revoke(ctx, cq.KnowledgeUnit{ID: unitID, Tier: cq.Private})
	}
	if err != nil {
		if unrevokable := unrevokableUnitResult(unitID, err); unrevokable != nil {
			return unrevokable, nil
		}

		return nil, fmt.Errorf("revoking: %w", err)
	}

	data, err := json.Marshal(revokeOutcome{UnitID: result.ID, Action: action})
	if err != nil {
		return nil, fmt.Errorf("encoding result: %w", err)
	}

	return mcp.NewToolResultText(string(data)), nil
}
