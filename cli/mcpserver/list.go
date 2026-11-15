package mcpserver

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/mark3labs/mcp-go/mcp"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// defaultListLimit and maxListLimit bound the number of units the MCP list tool returns.
const (
	defaultListLimit = 20
	maxListLimit     = 100
)

// ListTool returns the MCP tool definition for list.
func ListTool() mcp.Tool {
	return mcp.NewTool("list",
		mcp.WithDescription(
			"List the knowledge units you proposed and the review state each one is in. "+
				"Call to check whether your own proposals were approved, rejected or are still pending, "+
				"or to find a unit you proposed earlier so you can confirm or revoke it. "+
				"This covers your own units only; use query to search the shared commons.",
		),
		mcp.WithString(
			"cursor",
			mcp.Description("Cursor from a previous call's next_cursor, to fetch the following page."),
		),
		mcp.WithArray(
			"domains",
			mcp.Description(
				"Limit to units carrying any of these subject tags (e.g. \"api\", \"payments\").",
			),
			mcp.WithStringItems(),
		),
		mcp.WithArray(
			"frameworks",
			mcp.Description(
				"Limit to units carrying any of these frameworks (e.g. \"fastapi\", \"react\").",
			),
			mcp.WithStringItems(),
		),
		mcp.WithArray(
			"languages",
			mcp.Description(
				"Limit to units carrying any of these languages (e.g. \"python\", \"go\").",
			),
			mcp.WithStringItems(),
		),
		mcp.WithNumber(
			"limit",
			mcp.Description(
				fmt.Sprintf("Maximum units per page (default %d, max %d).", defaultListLimit, maxListLimit),
			),
		),
		mcp.WithString(
			"pattern",
			mcp.Description("Limit to units carrying this cross-cutting concern (e.g. \"shell-quoting\")."),
		),
		mcp.WithString(
			"search",
			mcp.Description("Limit to units whose summary, detail or action matches this text."),
		),
		mcp.WithString(
			"status",
			mcp.Description(
				fmt.Sprintf("Limit to one review state (one of: %s).", cq.AllReviewStatuses().String()),
			),
		),
	)
}

// HandleList returns the caller's own knowledge units with their review state.
func (s *Server) HandleList(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	if !s.client.HasRemote() {
		return mcp.NewToolResultError(
			"review state is held by a remote knowledge store and no remote API is configured",
		), nil
	}

	status, err := listStatusArg(req)
	if err != nil {
		return mcp.NewToolResultError(err.Error()), nil
	}

	limit := req.GetInt("limit", defaultListLimit)
	if limit <= 0 {
		limit = defaultListLimit
	}

	if limit > maxListLimit {
		limit = maxListLimit
	}

	params := cq.ListParams{
		Cursor:     req.GetString("cursor", ""),
		Domains:    req.GetStringSlice("domains", nil),
		Frameworks: req.GetStringSlice("frameworks", nil),
		Languages:  req.GetStringSlice("languages", nil),
		Limit:      limit,
		Pattern:    req.GetString("pattern", ""),
		Search:     req.GetString("search", ""),
		Status:     status,
	}

	result, err := s.client.List(ctx, params)
	if err != nil {
		return nil, fmt.Errorf("listing own units: %w", err)
	}

	data, err := json.Marshal(result)
	if err != nil {
		return nil, fmt.Errorf("encoding results: %w", err)
	}

	return mcp.NewToolResultText(string(data)), nil
}

// listStatusArg reads the optional status argument and validates it against
// the known review states. An absent status leaves the selection unfiltered.
func listStatusArg(req mcp.CallToolRequest) (cq.ReviewStatus, error) {
	raw := strings.ToLower(strings.TrimSpace(req.GetString("status", "")))
	if raw == "" {
		return "", nil
	}

	status := cq.ReviewStatus(raw)
	if !status.Valid() {
		return "", fmt.Errorf("invalid status '%s', must be one of: %s", raw, cq.AllReviewStatuses().String())
	}

	return status, nil
}
