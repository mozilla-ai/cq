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

	path := filepath.Join(t.TempDir(), "local.db")
	c, err := cq.NewClient(cq.WithAddr(""), cq.WithAPIKey(""), cq.WithLocalDBPath(path))
	require.NoError(t, err)
	t.Cleanup(func() { _ = c.Close() })

	return c
}

func TestE2EProposeQueryConfirmFlagStatus(t *testing.T) {
	t.Parallel()

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
				"domain":  []any{"testing"},
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
		Params: mcp.CallToolParams{Name: "query", Arguments: map[string]any{"domain": []any{"testing"}}},
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
