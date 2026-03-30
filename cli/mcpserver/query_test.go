package mcpserver

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/stretchr/testify/require"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

func TestHandleQuery(t *testing.T) {
	t.Parallel()

	t.Run("passes query params and returns units", func(t *testing.T) {
		t.Parallel()

		var got cq.QueryParams
		s := New(&mockClient{
			queryFn: func(_ context.Context, params cq.QueryParams) (cq.QueryResult, error) {
				got = params

				return cq.QueryResult{Units: []cq.KnowledgeUnit{{ID: "ku_0123456789abcdef0123456789abcdef"}}}, nil
			},
		}, "test")

		result, err := s.HandleQuery(context.Background(), mcp.CallToolRequest{
			Params: mcp.CallToolParams{
				Name: "query",
				Arguments: map[string]any{
					"domain":    []any{"api", "go"},
					"language":  "go",
					"framework": "cobra",
					"limit":     7,
				},
			},
		})
		require.NoError(t, err)
		require.False(t, result.IsError)

		require.Equal(t, []string{"api", "go"}, got.Domains)
		require.Equal(t, []string{"go"}, got.Languages)
		require.Equal(t, []string{"cobra"}, got.Frameworks)
		require.Equal(t, 7, got.Limit)

		text := result.Content[0].(mcp.TextContent).Text
		var units []cq.KnowledgeUnit
		require.NoError(t, json.Unmarshal([]byte(text), &units))
		require.Len(t, units, 1)
	})

	t.Run("errors when domain missing", func(t *testing.T) {
		t.Parallel()

		s := New(&mockClient{}, "test")
		result, err := s.HandleQuery(context.Background(), mcp.CallToolRequest{
			Params: mcp.CallToolParams{Name: "query", Arguments: map[string]any{}},
		})
		require.NoError(t, err)
		require.True(t, result.IsError)
	})
}
