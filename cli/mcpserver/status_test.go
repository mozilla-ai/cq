package mcpserver

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/stretchr/testify/require"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

func TestHandleStatus(t *testing.T) {
	t.Parallel()

	s := New(&mockClient{
		statusFn: func(_ context.Context) (cq.StoreStats, error) {
			return cq.StoreStats{TotalCount: 3}, nil
		},
	}, "test")

	result, err := s.HandleStatus(context.Background(), mcp.CallToolRequest{
		Params: mcp.CallToolParams{Name: "status", Arguments: map[string]any{}},
	})
	require.NoError(t, err)
	require.False(t, result.IsError)

	text := result.Content[0].(mcp.TextContent).Text
	var stats cq.StoreStats
	require.NoError(t, json.Unmarshal([]byte(text), &stats))
	require.Equal(t, 3, stats.TotalCount)
}
