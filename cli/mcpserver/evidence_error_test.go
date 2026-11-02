package mcpserver

import (
	"context"
	"net/http"
	"testing"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/stretchr/testify/require"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// notFoundClient fails both the local and the private attempt with a remote 404.
func notFoundClient() *mockClient {
	remoteErr := &cq.RemoteError{StatusCode: http.StatusNotFound, Detail: `{"detail":"Knowledge unit not found."}`}

	return &mockClient{
		confirmFn: func(_ context.Context, ku cq.KnowledgeUnit) (cq.KnowledgeUnit, error) {
			if ku.Tier == cq.Local {
				return cq.KnowledgeUnit{}, cq.ErrNotFound
			}

			return cq.KnowledgeUnit{}, remoteErr
		},
		flagFn: func(
			_ context.Context,
			ku cq.KnowledgeUnit,
			_ cq.FlagReason,
			_ ...cq.FlagOption,
		) (cq.KnowledgeUnit, error) {
			if ku.Tier == cq.Local {
				return cq.KnowledgeUnit{}, cq.ErrNotFound
			}

			return cq.KnowledgeUnit{}, remoteErr
		},
	}
}

func TestHandleFlagOnNotFoundNamesRevoke(t *testing.T) {
	t.Parallel()

	s := New(notFoundClient(), "test")

	result, err := s.HandleFlag(context.Background(), mcp.CallToolRequest{
		Params: mcp.CallToolParams{
			Name:      "flag",
			Arguments: map[string]any{"unit_id": "ku_1", "reason": "incorrect"},
		},
	})
	require.NoError(t, err, "a 404 is an answer, not a transport failure")
	require.True(t, result.IsError)

	text := toolResultText(t, result)
	require.Contains(t, text, "revoke")
	require.Contains(t, text, "ku_1")
}

func TestHandleConfirmOnNotFoundNamesRevoke(t *testing.T) {
	t.Parallel()

	s := New(notFoundClient(), "test")

	result, err := s.HandleConfirm(context.Background(), mcp.CallToolRequest{
		Params: mcp.CallToolParams{
			Name:      "confirm",
			Arguments: map[string]any{"unit_id": "ku_1"},
		},
	})
	require.NoError(t, err)
	require.True(t, result.IsError)

	text := toolResultText(t, result)
	require.Contains(t, text, "revoke")
	require.Contains(t, text, "ku_1")
}

func TestHandleFlagOnOtherErrorsIsUnchanged(t *testing.T) {
	t.Parallel()

	serverErr := &cq.RemoteError{StatusCode: http.StatusInternalServerError, Detail: "boom"}
	s := New(&mockClient{
		flagFn: func(
			_ context.Context,
			_ cq.KnowledgeUnit,
			_ cq.FlagReason,
			_ ...cq.FlagOption,
		) (cq.KnowledgeUnit, error) {
			return cq.KnowledgeUnit{}, serverErr
		},
	}, "test")

	_, err := s.HandleFlag(context.Background(), mcp.CallToolRequest{
		Params: mcp.CallToolParams{
			Name:      "flag",
			Arguments: map[string]any{"unit_id": "ku_1", "reason": "incorrect"},
		},
	})
	require.Error(t, err, "a non-404 failure keeps surfacing as a tool error")
	require.NotContains(t, err.Error(), "revoke")
}

// toolResultText returns the text payload of a tool result.
func toolResultText(t *testing.T, result *mcp.CallToolResult) string {
	t.Helper()

	require.NotEmpty(t, result.Content)
	text, ok := mcp.AsTextContent(result.Content[0])
	require.True(t, ok, "tool result should carry text content")

	return text.Text
}
