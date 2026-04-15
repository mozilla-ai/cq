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
		mcp.WithArray("domains",
			mcp.Required(),
			mcp.Description("Domain tags to search."),
			mcp.WithStringItems(),
		),
		mcp.WithArray("languages",
			mcp.Description("Filter by programming languages."),
			mcp.WithStringItems(),
		),
		mcp.WithArray("frameworks",
			mcp.Description("Filter by frameworks."),
			mcp.WithStringItems(),
		),
		mcp.WithNumber("limit",
			mcp.Description("Maximum results to return (default 5, max 50)."),
		),
	)
}

// HandleQuery searches knowledge units by domain.
func (s *Server) HandleQuery(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	domains, err := req.RequireStringSlice("domains")
	if err != nil {
		return mcp.NewToolResultError(fmt.Sprintf("invalid 'domains' argument: '%s'", err)), nil
	}
	if len(domains) == 0 {
		return mcp.NewToolResultError("domains must contain at least one tag"), nil
	}

	limit := req.GetInt("limit", defaultQueryLimit)
	if limit <= 0 {
		limit = defaultQueryLimit
	}
	if limit > maxQueryLimit {
		limit = maxQueryLimit
	}

	params := cq.QueryParams{
		Domains:    domains,
		Languages:  req.GetStringSlice("languages", nil),
		Frameworks: req.GetStringSlice("frameworks", nil),
		Limit:      limit,
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
