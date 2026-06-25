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
			"Search for known gotchas, workarounds, and version-specific quirks before acting. "+
				"Call when starting a task in unfamiliar territory, encountering an error, or setting up CI/CD or infrastructure. "+
				"Returns knowledge units with confidence scores and recommended actions. "+
				"Skip for routine edits to code you are already working in this session.",
		),
		mcp.WithArray(
			"domains",
			mcp.Required(),
			mcp.Description(
				"Subject-area tags capturing what the query is about (e.g. \"api\", \"payments\", \"connection-pooling\"). Use 2-3 specific tags.",
			),
			mcp.WithStringItems(),
		),
		mcp.WithArray(
			"languages",
			mcp.Description(
				"Programming languages the query applies to (e.g. \"python\", \"go\"). Do not repeat in domains.",
			),
			mcp.WithStringItems(),
		),
		mcp.WithArray(
			"frameworks",
			mcp.Description(
				"Libraries or frameworks involved (e.g. \"webpack\", \"react\", \"fastapi\"). Do not repeat in domains.",
			),
			mcp.WithStringItems(),
		),
		mcp.WithString(
			"pattern",
			mcp.Description(
				"Cross-cutting concern useful as a search axis independent of specific technology (e.g. \"shell-quoting\", \"ci-pipeline\").",
			),
		),
		mcp.WithNumber("limit",
			mcp.Description("Maximum results to return (default 5, max 50). Increase for broad exploratory queries."),
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
		Pattern:    req.GetString("pattern", ""),
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
