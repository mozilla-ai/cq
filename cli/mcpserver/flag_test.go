package mcpserver

import (
	"context"
	"encoding/json"
	"strconv"
	"testing"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/stretchr/testify/require"

	cqschema "github.com/mozilla-ai/cq/schema"
	cq "github.com/mozilla-ai/cq/sdk/go"
)

func TestHandleFlag(t *testing.T) {
	t.Parallel()

	t.Run("passes reason and options", func(t *testing.T) {
		t.Parallel()

		var gotReason cq.FlagReason
		var gotOptCount int

		s := New(&mockClient{
			flagFn: func(_ context.Context, _ cq.KnowledgeUnit, reason cq.FlagReason, opts ...cq.FlagOption) (cq.KnowledgeUnit, error) {
				gotReason = reason
				gotOptCount = len(opts)

				return cq.KnowledgeUnit{ID: "ku_1"}, nil
			},
		}, "test")

		result, err := s.HandleFlag(context.Background(), mcp.CallToolRequest{
			Params: mcp.CallToolParams{
				Name: "flag",
				Arguments: map[string]any{
					"unit_id":      "ku_1",
					"reason":       "duplicate",
					"detail":       "same as existing",
					"duplicate_of": "ku_2",
				},
			},
		})
		require.NoError(t, err)
		require.False(t, result.IsError)
		require.Equal(t, cq.Duplicate, gotReason)
		require.Equal(t, 2, gotOptCount)

		text := result.Content[0].(mcp.TextContent).Text
		var ku cq.KnowledgeUnit
		require.NoError(t, json.Unmarshal([]byte(text), &ku))
		require.Equal(t, "ku_1", ku.ID)
	})

	t.Run("errors on invalid reason", func(t *testing.T) {
		t.Parallel()

		s := New(&mockClient{}, "test")
		result, err := s.HandleFlag(context.Background(), mcp.CallToolRequest{
			Params: mcp.CallToolParams{Name: "flag", Arguments: map[string]any{"unit_id": "ku_1", "reason": "bad"}},
		})
		require.NoError(t, err)
		require.True(t, result.IsError)
	})
}

func TestFlagToolDescribesDetailLimit(t *testing.T) {
	t.Parallel()

	prop, ok := FlagTool().InputSchema.Properties["detail"].(map[string]any)
	require.True(t, ok, "detail property should be an object")
	description, ok := prop["description"].(string)
	require.True(t, ok, "detail property should carry a description")
	require.Contains(t, description, strconv.Itoa(cqschema.FlagDetailMaxLength()))
}
