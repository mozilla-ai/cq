package mcpserver_test

import (
	"context"
	"encoding/json"
	"path/filepath"
	"testing"

	"github.com/mark3labs/mcp-go/client"
	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/mcptest"
	"github.com/mark3labs/mcp-go/server"
	"github.com/stretchr/testify/require"

	"github.com/mozilla-ai/cq/cli/mcpserver"
	cq "github.com/mozilla-ai/cq/sdk/go"
)

func newMCPTestClient(t *testing.T, srv *mcpserver.Server) *client.Client {
	t.Helper()

	tools := []server.ServerTool{
		{Tool: mcpserver.QueryTool(), Handler: srv.HandleQuery},
		{Tool: mcpserver.ProposeTool(), Handler: srv.HandlePropose},
		{Tool: mcpserver.ConfirmTool(), Handler: srv.HandleConfirm},
		{Tool: mcpserver.FlagTool(), Handler: srv.HandleFlag},
		{Tool: mcpserver.StatusTool(), Handler: srv.HandleStatus},
	}

	testSrv, err := mcptest.NewServer(t, tools...)
	require.NoError(t, err)
	t.Cleanup(testSrv.Close)

	return testSrv.Client()
}

func newSDKClient(t *testing.T) *cq.Client {
	t.Helper()

	t.Setenv("CQ_ADDR", "")
	t.Setenv("CQ_API_KEY", "")
	t.Setenv("CQ_LOCAL_DB_PATH", "")

	path := filepath.Join(t.TempDir(), "local.db")
	c, err := cq.NewClient(cq.WithLocalDBPath(path))
	require.NoError(t, err)
	t.Cleanup(func() { _ = c.Close() })

	return c
}

func TestE2EProposeQueryConfirmFlagStatus(t *testing.T) {

	realClient := newSDKClient(t)
	srv := mcpserver.New(realClient, "test")
	c := newMCPTestClient(t, srv)
	ctx := context.Background()

	proposeResult, err := c.CallTool(ctx, mcp.CallToolRequest{
		Params: mcp.CallToolParams{
			Name: "propose",
			Arguments: map[string]any{
				"summary": "E2E insight",
				"detail":  "Proposed over MCP.",
				"action":  "Use this in tests.",
				"domains": []any{"testing"},
			},
		},
	})
	require.NoError(t, err)
	require.False(t, proposeResult.IsError)

	var proposed cq.KnowledgeUnit
	proposeText := proposeResult.Content[0].(mcp.TextContent).Text
	require.NoError(t, json.Unmarshal([]byte(proposeText), &proposed))
	require.NotEmpty(t, proposed.ID)

	queryResult, err := c.CallTool(ctx, mcp.CallToolRequest{
		Params: mcp.CallToolParams{Name: "query", Arguments: map[string]any{"domains": []any{"testing"}}},
	})
	require.NoError(t, err)
	require.False(t, queryResult.IsError)
	queryText := queryResult.Content[0].(mcp.TextContent).Text
	require.Contains(t, queryText, proposed.ID)

	confirmResult, err := c.CallTool(ctx, mcp.CallToolRequest{
		Params: mcp.CallToolParams{Name: "confirm", Arguments: map[string]any{"unit_id": proposed.ID}},
	})
	require.NoError(t, err)
	require.False(t, confirmResult.IsError)

	flagResult, err := c.CallTool(ctx, mcp.CallToolRequest{
		Params: mcp.CallToolParams{Name: "flag", Arguments: map[string]any{"unit_id": proposed.ID, "reason": "stale"}},
	})
	require.NoError(t, err)
	require.False(t, flagResult.IsError)

	statusResult, err := c.CallTool(ctx, mcp.CallToolRequest{
		Params: mcp.CallToolParams{Name: "status", Arguments: map[string]any{}},
	})
	require.NoError(t, err)
	require.False(t, statusResult.IsError)

	var stats cq.StoreStats
	statusText := statusResult.Content[0].(mcp.TextContent).Text
	require.NoError(t, json.Unmarshal([]byte(statusText), &stats))
	require.Equal(t, 1, stats.TotalCount)
}

// TestE2EPatternBoost verifies that the MCP query tool threads the pattern filter through to
// scoring so a pattern-matching unit ranks above an otherwise-equivalent plain unit. The plain
// unit is inserted first so insertion-order tiebreaking would rank it first if the pattern boost
// were silently dropped anywhere in the propose -> store -> query path.
func TestE2EPatternBoost(t *testing.T) {
	realClient := newSDKClient(t)
	srv := mcpserver.New(realClient, "test")
	c := newMCPTestClient(t, srv)
	ctx := context.Background()

	plainResp, err := c.CallTool(ctx, mcp.CallToolRequest{
		Params: mcp.CallToolParams{
			Name: "propose",
			Arguments: map[string]any{
				"summary": "plain",
				"detail":  "no pattern",
				"action":  "noop",
				"domains": []any{"api"},
			},
		},
	})
	require.NoError(t, err)
	require.False(t, plainResp.IsError)

	var plain cq.KnowledgeUnit
	plainText := plainResp.Content[0].(mcp.TextContent).Text
	require.NoError(t, json.Unmarshal([]byte(plainText), &plain))

	matchResp, err := c.CallTool(ctx, mcp.CallToolRequest{
		Params: mcp.CallToolParams{
			Name: "propose",
			Arguments: map[string]any{
				"summary": "match",
				"detail":  "with pattern",
				"action":  "noop",
				"domains": []any{"api"},
				"pattern": "api-client",
			},
		},
	})
	require.NoError(t, err)
	require.False(t, matchResp.IsError)

	var match cq.KnowledgeUnit
	matchText := matchResp.Content[0].(mcp.TextContent).Text
	require.NoError(t, json.Unmarshal([]byte(matchText), &match))

	queryResp, err := c.CallTool(ctx, mcp.CallToolRequest{
		Params: mcp.CallToolParams{
			Name: "query",
			Arguments: map[string]any{
				"domains": []any{"api"},
				"pattern": "api-client",
			},
		},
	})
	require.NoError(t, err)
	require.False(t, queryResp.IsError)

	var units []cq.KnowledgeUnit
	queryText := queryResp.Content[0].(mcp.TextContent).Text
	require.NoError(t, json.Unmarshal([]byte(queryText), &units))
	require.Len(t, units, 2)
	require.Equal(t, match.ID, units[0].ID, "the pattern-matching unit must rank above the plain unit")
	require.Equal(t, plain.ID, units[1].ID)
}
