package mcpserver

import (
	"context"
	"encoding/json"
	"errors"
	"strconv"
	"testing"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/stretchr/testify/require"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

func TestHandleListClampsLimit(t *testing.T) {
	t.Parallel()

	for _, tc := range []struct {
		name string
		args map[string]any
		want int
	}{
		{name: "above the ceiling", args: map[string]any{"limit": 500}, want: maxListLimit},
		{name: "absent", args: map[string]any{}, want: defaultListLimit},
		{name: "negative", args: map[string]any{"limit": -3}, want: defaultListLimit},
		{name: "within range", args: map[string]any{"limit": 7}, want: 7},
		{name: "zero", args: map[string]any{"limit": 0}, want: defaultListLimit},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			var got int
			s := New(&mockClient{
				hasRemote: true,
				listFn: func(_ context.Context, params cq.ListParams) (cq.ListResult, error) {
					got = params.Limit

					return cq.ListResult{}, nil
				},
			}, "test")

			result, err := s.HandleList(context.Background(), mcp.CallToolRequest{
				Params: mcp.CallToolParams{Name: "list", Arguments: tc.args},
			})
			require.NoError(t, err)
			require.False(t, result.IsError)
			require.Equal(t, tc.want, got)
		})
	}
}

func TestHandleListPassesEveryFilter(t *testing.T) {
	t.Parallel()

	var got cq.ListParams
	s := New(&mockClient{
		hasRemote: true,
		listFn: func(_ context.Context, params cq.ListParams) (cq.ListResult, error) {
			got = params

			return cq.ListResult{}, nil
		},
	}, "test")

	result, err := s.HandleList(context.Background(), mcp.CallToolRequest{
		Params: mcp.CallToolParams{Name: "list", Arguments: map[string]any{
			"cursor":     "cursor_abc",
			"domains":    []any{"api", "payments"},
			"frameworks": []any{"fastapi"},
			"languages":  []any{"go"},
			"limit":      7,
			"pattern":    "shell-quoting",
			"search":     "nektos/act",
			"status":     "pending",
		}},
	})
	require.NoError(t, err)
	require.False(t, result.IsError)

	require.Equal(t, cq.ListParams{
		Cursor:     "cursor_abc",
		Domains:    []string{"api", "payments"},
		Frameworks: []string{"fastapi"},
		Languages:  []string{"go"},
		Limit:      7,
		Pattern:    "shell-quoting",
		Search:     "nektos/act",
		Status:     cq.Pending,
	}, got)
}

func TestHandleListRejectsUnknownStatus(t *testing.T) {
	t.Parallel()

	s := New(&mockClient{hasRemote: true}, "test")

	result, err := s.HandleList(context.Background(), mcp.CallToolRequest{
		Params: mcp.CallToolParams{Name: "list", Arguments: map[string]any{"status": "approvd"}},
	})
	require.NoError(t, err)
	require.True(t, result.IsError)

	text := result.Content[0].(mcp.TextContent).Text
	require.Contains(t, text, "approvd")
	require.Contains(t, text, "pending")
}

func TestHandleListReportsAClientFailure(t *testing.T) {
	t.Parallel()

	s := New(&mockClient{
		hasRemote: true,
		listFn: func(_ context.Context, _ cq.ListParams) (cq.ListResult, error) {
			return cq.ListResult{}, errors.New("remote refused the listing")
		},
	}, "test")

	_, err := s.HandleList(context.Background(), mcp.CallToolRequest{
		Params: mcp.CallToolParams{Name: "list", Arguments: map[string]any{}},
	})
	require.ErrorContains(t, err, "remote refused the listing")
}

func TestHandleListReturnsUnitsStatusAndCursor(t *testing.T) {
	t.Parallel()

	s := New(&mockClient{
		hasRemote: true,
		listFn: func(_ context.Context, _ cq.ListParams) (cq.ListResult, error) {
			return cq.ListResult{
				Facets:     cq.Facets{Domains: map[string]int{"api": 2}},
				NextCursor: "cursor_next",
				Units: []cq.OwnUnit{{
					KnowledgeUnit: cq.KnowledgeUnit{ID: "ku_00000000000000000000000000000001"},
					Status:        cq.Approved,
				}},
			}, nil
		},
	}, "test")

	result, err := s.HandleList(context.Background(), mcp.CallToolRequest{
		Params: mcp.CallToolParams{Name: "list", Arguments: map[string]any{}},
	})
	require.NoError(t, err)
	require.False(t, result.IsError)

	text := result.Content[0].(mcp.TextContent).Text
	var payload cq.ListResult
	require.NoError(t, json.Unmarshal([]byte(text), &payload))

	require.Len(t, payload.Units, 1)
	require.Equal(t, cq.Approved, payload.Units[0].Status)

	// Without the cursor an agent cannot reach the second page, and without
	// the facets it cannot tell which tags are worth narrowing to.
	require.Equal(t, "cursor_next", payload.NextCursor)
	require.Equal(t, 2, payload.Facets.Domains["api"])
}

func TestHandleListWithoutRemoteExplainsWhy(t *testing.T) {
	t.Parallel()

	// listFn is nil, so reaching the client at all fails the test.
	s := New(&mockClient{hasRemote: false}, "test")

	result, err := s.HandleList(context.Background(), mcp.CallToolRequest{
		Params: mcp.CallToolParams{Name: "list", Arguments: map[string]any{}},
	})
	require.NoError(t, err)
	require.True(t, result.IsError)

	text := result.Content[0].(mcp.TextContent).Text
	require.Contains(t, text, "remote")
}

func TestListToolStatesTheLimitCeiling(t *testing.T) {
	t.Parallel()

	require.Equal(t, "list", ListTool().Name)

	prop, ok := ListTool().InputSchema.Properties["limit"].(map[string]any)
	require.True(t, ok, "limit property should be an object")
	description, ok := prop["description"].(string)
	require.True(t, ok, "limit property should carry a description")
	require.Contains(t, description, strconv.Itoa(defaultListLimit))
	require.Contains(t, description, strconv.Itoa(maxListLimit))
}
