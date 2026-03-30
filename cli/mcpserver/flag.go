package mcpserver

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/mark3labs/mcp-go/mcp"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

var flagReasonValues = map[string]cq.FlagReason{
	"stale":     cq.Stale,
	"incorrect": cq.Incorrect,
	"duplicate": cq.Duplicate,
}

// FlagTool returns the MCP tool definition for flag.
func FlagTool() mcp.Tool {
	return mcp.NewTool("flag",
		mcp.WithDescription("Flag a knowledge unit as problematic, reducing its confidence score."),
		mcp.WithString("unit_id",
			mcp.Required(),
			mcp.Description("ID of the knowledge unit to flag."),
		),
		mcp.WithString("reason",
			mcp.Required(),
			mcp.Description("Flag reason."),
			mcp.Enum("stale", "incorrect", "duplicate"),
		),
		mcp.WithString("detail",
			mcp.Description("Optional detail for this flag."),
		),
		mcp.WithString("duplicate_of",
			mcp.Description("Original unit ID when reason is duplicate."),
		),
	)
}

// HandleFlag marks a knowledge unit as problematic and reduces its confidence.
func (s *Server) HandleFlag(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	unitID, err := req.RequireString("unit_id")
	if err != nil {
		return mcp.NewToolResultError("unit_id is required"), nil
	}
	reason, err := req.RequireString("reason")
	if err != nil {
		return mcp.NewToolResultError("reason is required"), nil
	}

	flagReason, ok := flagReasonValues[strings.ToLower(reason)]
	if !ok {
		return mcp.NewToolResultError(
			fmt.Sprintf("invalid reason %s: must be stale, incorrect, or duplicate", reason),
		), nil
	}

	opts := make([]cq.FlagOption, 0, 2)
	detail := req.GetString("detail", "")
	if detail != "" {
		opts = append(opts, cq.WithDetail(detail))
	}
	duplicateOf := req.GetString("duplicate_of", "")
	if duplicateOf != "" {
		opts = append(opts, cq.WithDuplicateOf(duplicateOf))
	}

	result, err := s.client.Flag(ctx, cq.KnowledgeUnit{ID: unitID, Tier: cq.Local}, flagReason, opts...)
	if errors.Is(err, cq.ErrNotFound) {
		result, err = s.client.Flag(ctx, cq.KnowledgeUnit{ID: unitID, Tier: cq.Private}, flagReason, opts...)
	}
	if err != nil {
		return nil, fmt.Errorf("flagging: %w", err)
	}

	data, err := json.Marshal(result)
	if err != nil {
		return nil, fmt.Errorf("encoding result: %w", err)
	}

	return mcp.NewToolResultText(string(data)), nil
}
