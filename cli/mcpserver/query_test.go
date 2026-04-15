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
					"domains":    []any{"api", "go"},
					"languages":  []any{"go"},
					"frameworks": []any{"cobra"},
					"limit":      7,
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

	t.Run("errors when domains missing", func(t *testing.T) {
		t.Parallel()

		s := New(&mockClient{}, "test")
		result, err := s.HandleQuery(context.Background(), mcp.CallToolRequest{
			Params: mcp.CallToolParams{Name: "query", Arguments: map[string]any{}},
		})
		require.NoError(t, err)
		require.True(t, result.IsError)
	})

	t.Run("ignores unknown sibling keys", func(t *testing.T) {
		t.Parallel()

		s := New(&mockClient{
			queryFn: func(_ context.Context, _ cq.QueryParams) (cq.QueryResult, error) {
				return cq.QueryResult{}, nil
			},
		}, "test")

		result, err := s.HandleQuery(context.Background(), mcp.CallToolRequest{
			Params: mcp.CallToolParams{
				Name: "query",
				Arguments: map[string]any{
					"domains":  []any{"memory-layer", "ai-agents"},
					"context":  map[string]any{"pattern": "competitor-research"},
					"keywords": []any{"honcho", "plastic-labs"},
					"limit":    5,
				},
			},
		})
		require.NoError(t, err)
		require.False(t, result.IsError, "unknown sibling keys must not trigger a validation error")
	})

	t.Run("domains argument error modes produce distinct messages", func(t *testing.T) {
		t.Parallel()

		tests := []struct {
			name    string
			args    map[string]any
			wantMsg string
		}{
			{
				name:    "key absent",
				args:    map[string]any{"limit": 3},
				wantMsg: `invalid 'domains' argument: 'required argument "domains" not found'`,
			},
			{
				name:    "domains is a plain string",
				args:    map[string]any{"domains": "memory-layer"},
				wantMsg: `invalid 'domains' argument: 'argument "domains" is not a string slice'`,
			},
			{
				name:    "domains is a number",
				args:    map[string]any{"domains": 42},
				wantMsg: `invalid 'domains' argument: 'argument "domains" is not a string slice'`,
			},
			{
				name:    "domains is null",
				args:    map[string]any{"domains": nil},
				wantMsg: `invalid 'domains' argument: 'argument "domains" is not a string slice'`,
			},
			{
				name:    "domains is a map",
				args:    map[string]any{"domains": map[string]any{"a": "b"}},
				wantMsg: `invalid 'domains' argument: 'argument "domains" is not a string slice'`,
			},
			{
				name:    "domains contains non-string item",
				args:    map[string]any{"domains": []any{"memory-layer", 42}},
				wantMsg: `invalid 'domains' argument: 'item 1 in argument "domains" is not a string'`,
			},
		}

		for _, tc := range tests {
			t.Run(tc.name, func(t *testing.T) {
				t.Parallel()

				s := New(&mockClient{}, "test")
				result, err := s.HandleQuery(context.Background(), mcp.CallToolRequest{
					Params: mcp.CallToolParams{Name: "query", Arguments: tc.args},
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
		result, err := s.HandleQuery(context.Background(), mcp.CallToolRequest{
			Params: mcp.CallToolParams{
				Name:      "query",
				Arguments: map[string]any{"domains": []any{}},
			},
		})
		require.NoError(t, err)
		require.True(t, result.IsError)
		require.Equal(t, "domains must contain at least one tag", result.Content[0].(mcp.TextContent).Text)
	})
}
