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
					"domains":    []any{"api"},
					"languages":  []any{"go"},
					"frameworks": []any{"cobra"},
					"pattern":    "cli",
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

	t.Run("domains argument error modes produce distinct messages", func(t *testing.T) {
		t.Parallel()

		baseArgs := func(domains any, present bool) map[string]any {
			args := map[string]any{
				"summary": "s",
				"detail":  "d",
				"action":  "a",
			}
			if present {
				args["domains"] = domains
			}

			return args
		}

		tests := []struct {
			name    string
			args    map[string]any
			wantMsg string
		}{
			{
				name:    "key absent",
				args:    baseArgs(nil, false),
				wantMsg: `invalid 'domains' argument: 'required argument "domains" not found'`,
			},
			{
				name:    "domains is a plain string",
				args:    baseArgs("api", true),
				wantMsg: `invalid 'domains' argument: 'argument "domains" is not a string slice'`,
			},
			{
				name:    "domains contains non-string item",
				args:    baseArgs([]any{"api", 42}, true),
				wantMsg: `invalid 'domains' argument: 'item 1 in argument "domains" is not a string'`,
			},
		}

		for _, tc := range tests {
			t.Run(tc.name, func(t *testing.T) {
				t.Parallel()

				s := New(&mockClient{}, "test")
				result, err := s.HandlePropose(context.Background(), mcp.CallToolRequest{
					Params: mcp.CallToolParams{Name: "propose", Arguments: tc.args},
				})
				require.NoError(t, err)
				require.True(t, result.IsError)
				require.Equal(t, tc.wantMsg, result.Content[0].(mcp.TextContent).Text)
			})
		}
	})

	t.Run("empty domains slice yields distinct message", func(t *testing.T) {
		t.Parallel()

		s := New(&mockClient{}, "test")
		result, err := s.HandlePropose(context.Background(), mcp.CallToolRequest{
			Params: mcp.CallToolParams{
				Name: "propose",
				Arguments: map[string]any{
					"summary": "s",
					"detail":  "d",
					"action":  "a",
					"domains": []any{},
				},
			},
		})
		require.NoError(t, err)
		require.True(t, result.IsError)
		require.Equal(t, "domains must contain at least one tag", result.Content[0].(mcp.TextContent).Text)
	})
}
