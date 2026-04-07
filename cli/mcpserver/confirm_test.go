package mcpserver

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/stretchr/testify/require"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

func TestHandleConfirm(t *testing.T) {
	t.Parallel()

	t.Run("falls back to remote tier on local not found", func(t *testing.T) {
		t.Parallel()

		calls := 0
		s := New(&mockClient{
			confirmFn: func(_ context.Context, ku cq.KnowledgeUnit) (cq.KnowledgeUnit, error) {
				calls++
				if calls == 1 {
					require.Equal(t, cq.Local, ku.Tier)
					return cq.KnowledgeUnit{}, cq.ErrNotFound
				}

				require.Equal(t, cq.Private, ku.Tier)
				return cq.KnowledgeUnit{ID: ku.ID}, nil
			},
		}, "test")

		result, err := s.HandleConfirm(context.Background(), mcp.CallToolRequest{
			Params: mcp.CallToolParams{Name: "confirm", Arguments: map[string]any{"unit_id": "ku_1"}},
		})
		require.NoError(t, err)
		require.False(t, result.IsError)
		require.Equal(t, 2, calls)

		text := result.Content[0].(mcp.TextContent).Text
		var ku cq.KnowledgeUnit
		require.NoError(t, json.Unmarshal([]byte(text), &ku))
		require.Equal(t, "ku_1", ku.ID)
	})

	t.Run("errors when unit id is missing", func(t *testing.T) {
		t.Parallel()

		s := New(&mockClient{}, "test")
		result, err := s.HandleConfirm(context.Background(), mcp.CallToolRequest{
			Params: mcp.CallToolParams{Name: "confirm", Arguments: map[string]any{}},
		})
		require.NoError(t, err)
		require.True(t, result.IsError)
	})
}
