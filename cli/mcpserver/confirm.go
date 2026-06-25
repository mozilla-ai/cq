package mcpserver

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/mark3labs/mcp-go/mcp"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// ConfirmTool returns the MCP tool definition for confirm.
func ConfirmTool() mcp.Tool {
	return mcp.NewTool("confirm",
		mcp.WithDescription(
			"Strengthen a knowledge unit that proved correct during your task. "+
				"Call after you followed queried guidance and it resolved or avoided the described issue, "+
				"or after you independently verified the described behavior still exists.",
		),
		mcp.WithString("unit_id",
			mcp.Required(),
			mcp.Description("ID of the knowledge unit to confirm (returned by query)."),
		),
	)
}

// HandleConfirm boosts the confidence of a knowledge unit.
func (s *Server) HandleConfirm(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	unitID, err := req.RequireString("unit_id")
	if err != nil {
		return mcp.NewToolResultError("unit_id is required"), nil
	}

	result, err := s.client.Confirm(ctx, cq.KnowledgeUnit{ID: unitID, Tier: cq.Local})
	if errors.Is(err, cq.ErrNotFound) {
		result, err = s.client.Confirm(ctx, cq.KnowledgeUnit{ID: unitID, Tier: cq.Private})
	}
	if err != nil {
		return nil, fmt.Errorf("confirming: %w", err)
	}

	data, err := json.Marshal(result)
	if err != nil {
		return nil, fmt.Errorf("encoding result: %w", err)
	}

	return mcp.NewToolResultText(string(data)), nil
}
