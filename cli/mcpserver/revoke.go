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

// HandleRevoke withdraws a knowledge unit on behalf of its author.
func (s *Server) HandleRevoke(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	unitID, err := req.RequireString("unit_id")
	if err != nil {
		return mcp.NewToolResultError("unit_id is required"), nil
	}

	result, err := s.client.Revoke(ctx, cq.KnowledgeUnit{ID: unitID, Tier: cq.Local})
	if errors.Is(err, cq.ErrNotFound) {
		result, err = s.client.Revoke(ctx, cq.KnowledgeUnit{ID: unitID, Tier: cq.Private})
	}
	if err != nil {
		return nil, fmt.Errorf("revoking: %w", err)
	}

	data, err := json.Marshal(result)
	if err != nil {
		return nil, fmt.Errorf("encoding result: %w", err)
	}

	return mcp.NewToolResultText(string(data)), nil
}
