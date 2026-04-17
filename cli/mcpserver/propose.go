package mcpserver

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/mark3labs/mcp-go/mcp"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// ProposeTool returns the MCP tool definition for propose.
func ProposeTool() mcp.Tool {
	return mcp.NewTool("propose",
		mcp.WithDescription("Propose a new knowledge unit."),
		mcp.WithString("summary",
			mcp.Required(),
			mcp.Description("Brief summary of the insight."),
		),
		mcp.WithString("detail",
			mcp.Required(),
			mcp.Description("Detailed explanation of what was discovered."),
		),
		mcp.WithString("action",
			mcp.Required(),
			mcp.Description("Recommended action for agents encountering this situation."),
		),
		mcp.WithArray("domains",
			mcp.Required(),
			mcp.Description("Domain tags for this knowledge."),
			mcp.WithStringItems(),
		),
		mcp.WithArray("languages",
			mcp.Description("Programming language context."),
			mcp.WithStringItems(),
		),
		mcp.WithArray("frameworks",
			mcp.Description("Framework context."),
			mcp.WithStringItems(),
		),
		mcp.WithString("pattern", mcp.Description("Pattern name.")),
	)
}

// HandlePropose creates a knowledge unit.
func (s *Server) HandlePropose(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	summary, err := req.RequireString("summary")
	if err != nil {
		return mcp.NewToolResultError("summary is required"), nil
	}
	detail, err := req.RequireString("detail")
	if err != nil {
		return mcp.NewToolResultError("detail is required"), nil
	}
	action, err := req.RequireString("action")
	if err != nil {
		return mcp.NewToolResultError("action is required"), nil
	}
	domains, err := req.RequireStringSlice("domains")
	if err != nil {
		return mcp.NewToolResultError(fmt.Sprintf("invalid 'domains' argument: '%s'", err)), nil
	}
	if len(domains) == 0 {
		return mcp.NewToolResultError("domains must contain at least one tag"), nil
	}

	params := cq.ProposeParams{
		Summary:    summary,
		Detail:     detail,
		Action:     action,
		Domains:    domains,
		Languages:  req.GetStringSlice("languages", nil),
		Frameworks: req.GetStringSlice("frameworks", nil),
		Pattern:    req.GetString("pattern", ""),
	}

	result, err := s.client.Propose(ctx, params)
	// Remote unreachable/rejected: unit was stored locally. Surface the unit
	// alongside a warning so the caller can summarise the partial success.
	var fb *cq.FallbackError
	if errors.As(err, &fb) {
		data, mErr := json.Marshal(fb.LocalUnit)
		if mErr != nil {
			return nil, fmt.Errorf("encoding result: %w", mErr)
		}

		return mcp.NewToolResultText(fmt.Sprintf("warning: %s\n%s", fb, data)), nil
	}
	if err != nil {
		return nil, fmt.Errorf("proposing: %w", err)
	}

	data, err := json.Marshal(result)
	if err != nil {
		return nil, fmt.Errorf("encoding result: %w", err)
	}

	return mcp.NewToolResultText(string(data)), nil
}
