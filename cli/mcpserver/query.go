package mcpserver

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/mark3labs/mcp-go/mcp"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// defaultMCPQueryLimit and maxMCPQueryLimit bound the number of results the MCP query tool returns.
const (
	defaultQueryLimit = 5
	maxQueryLimit     = 50
)

// QueryTool returns the MCP tool definition for query.
func QueryTool() mcp.Tool {
	return mcp.NewTool("query",
		mcp.WithDescription(
			"Search for relevant knowledge units by domain tags.",
		),
		mcp.WithArray("domain",
			mcp.Required(),
			mcp.Description("Domain tags to search."),
			mcp.WithStringItems(),
		),
		mcp.WithString("language",
			mcp.Description("Filter by programming language."),
		),
		mcp.WithString("framework",
			mcp.Description("Filter by framework."),
		),
		mcp.WithNumber("limit",
			mcp.Description("Maximum results to return (default 5, max 50)."),
		),
	)
}

// HandleQuery searches knowledge units by domain.
func (s *Server) HandleQuery(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	domains, err := req.RequireStringSlice("domain")
	if err != nil {
		return mcp.NewToolResultError("domain is required (string array)"), nil
	}
	if len(domains) == 0 {
		return mcp.NewToolResultError("domain must contain at least one tag"), nil
	}

	language := req.GetString("language", "")
	framework := req.GetString("framework", "")
	limit := req.GetInt("limit", defaultQueryLimit)
	if limit <= 0 {
		limit = defaultQueryLimit
	}
	if limit > maxQueryLimit {
		limit = maxQueryLimit
	}

	params := cq.QueryParams{
		Domains: domains,
		Limit:   limit,
	}
	if language != "" {
		params.Languages = []string{language}
	}
	if framework != "" {
		params.Frameworks = []string{framework}
	}

	result, err := s.client.Query(ctx, params)
	if err != nil {
		return nil, fmt.Errorf("querying: %w", err)
	}

	data, err := json.Marshal(result.Units)
	if err != nil {
		return nil, fmt.Errorf("encoding results: %w", err)
	}

	return mcp.NewToolResultText(string(data)), nil
}
