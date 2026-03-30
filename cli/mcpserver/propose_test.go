package mcpserver

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/stretchr/testify/require"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

func TestHandlePropose(t *testing.T) {
	t.Parallel()

	t.Run("passes propose params and returns created unit", func(t *testing.T) {
		t.Parallel()

		var got cq.ProposeParams
		s := New(&mockClient{
			proposeFn: func(_ context.Context, params cq.ProposeParams) (cq.KnowledgeUnit, error) {
				got = params
				return cq.KnowledgeUnit{ID: "ku_0123456789abcdef0123456789abcdef"}, nil
			},
		}, "test")

		result, err := s.HandlePropose(context.Background(), mcp.CallToolRequest{
			Params: mcp.CallToolParams{
				Name: "propose",
				Arguments: map[string]any{
					"summary":   "summary",
					"detail":    "detail",
					"action":    "action",
					"domain":    []any{"api"},
					"language":  "go",
					"framework": "cobra",
					"pattern":   "cli",
				},
			},
		})
		require.NoError(t, err)
		require.False(t, result.IsError)
		require.Equal(t, "summary", got.Summary)
		require.Equal(t, []string{"api"}, got.Domains)

		text := result.Content[0].(mcp.TextContent).Text
		var ku cq.KnowledgeUnit
		require.NoError(t, json.Unmarshal([]byte(text), &ku))
		require.Equal(t, "ku_0123456789abcdef0123456789abcdef", ku.ID)
	})

	t.Run("errors when required fields are missing", func(t *testing.T) {
		t.Parallel()

		s := New(&mockClient{}, "test")
		result, err := s.HandlePropose(context.Background(), mcp.CallToolRequest{
			Params: mcp.CallToolParams{Name: "propose", Arguments: map[string]any{}},
		})
		require.NoError(t, err)
		require.True(t, result.IsError)
	})
}
