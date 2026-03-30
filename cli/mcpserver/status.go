package mcpserver

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/mark3labs/mcp-go/mcp"
)

// StatusTool returns the MCP tool definition for status.
func StatusTool() mcp.Tool {
	return mcp.NewTool("status",
		mcp.WithDescription(
			"Show local knowledge store statistics: unit count, domains, recent additions, confidence distribution.",
		),
	)
}

// HandleStatus returns aggregated store statistics.
func (s *Server) HandleStatus(ctx context.Context, _ mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	stats, err := s.client.Status(ctx)
	if err != nil {
		return nil, fmt.Errorf("reading store stats: %w", err)
	}

	data, err := json.Marshal(stats)
	if err != nil {
		return nil, fmt.Errorf("encoding stats: %w", err)
	}

	return mcp.NewToolResultText(string(data)), nil
}
