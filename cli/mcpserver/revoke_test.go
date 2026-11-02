package mcpserver

import (
	"context"
	"testing"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/stretchr/testify/require"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

func TestHandleRevoke(t *testing.T) {
	t.Parallel()

	t.Run("passes the unit id through", func(t *testing.T) {
		t.Parallel()

		var gotID string
		s := New(&mockClient{
			revokeFn: func(_ context.Context, ku cq.KnowledgeUnit) (cq.KnowledgeUnit, error) {
				gotID = ku.ID

				return cq.KnowledgeUnit{ID: ku.ID}, nil
			},
		}, "test")

		result, err := s.HandleRevoke(context.Background(), mcp.CallToolRequest{
			Params: mcp.CallToolParams{
				Name:      "revoke",
				Arguments: map[string]any{"unit_id": "ku_00000000000000000000000000000001"},
			},
		})
		require.NoError(t, err)
		require.False(t, result.IsError)
		require.Equal(t, "ku_00000000000000000000000000000001", gotID)

		// A local revoke deletes the unit, so the result names the action rather
		// than handing back a record that no longer exists.
		require.Contains(t, toolResultText(t, result), `"action":"deleted_local"`)
	})

	t.Run("errors when unit_id is missing", func(t *testing.T) {
		t.Parallel()

		s := New(&mockClient{}, "test")

		result, err := s.HandleRevoke(context.Background(), mcp.CallToolRequest{
			Params: mcp.CallToolParams{Name: "revoke", Arguments: map[string]any{}},
		})
		require.NoError(t, err)
		require.True(t, result.IsError)
	})

	t.Run("retries the private tier when the local store has no such unit", func(t *testing.T) {
		t.Parallel()

		var tiers []cq.Tier
		s := New(&mockClient{
			revokeFn: func(_ context.Context, ku cq.KnowledgeUnit) (cq.KnowledgeUnit, error) {
				tiers = append(tiers, ku.Tier)
				if ku.Tier == cq.Local {
					return cq.KnowledgeUnit{}, cq.ErrNotFound
				}

				return cq.KnowledgeUnit{ID: ku.ID}, nil
			},
		}, "test")

		result, err := s.HandleRevoke(context.Background(), mcp.CallToolRequest{
			Params: mcp.CallToolParams{
				Name:      "revoke",
				Arguments: map[string]any{"unit_id": "ku_00000000000000000000000000000001"},
			},
		})
		require.NoError(t, err)
		require.False(t, result.IsError)
		require.Equal(t, []cq.Tier{cq.Local, cq.Private}, tiers)
		require.Contains(t, toolResultText(t, result), `"action":"revoked_remote"`)
	})
}

func TestRevokeToolDescriptionDistinguishesFlag(t *testing.T) {
	t.Parallel()

	description := RevokeTool().Description

	// The whole point of the verb is that an agent picks it over flag for its
	// own units, so the description has to draw that line itself.
	require.Contains(t, description, "flag")
	require.Contains(t, description, "your own")
}

func TestHandleRevokeRejectsMalformedUnitID(t *testing.T) {
	t.Parallel()

	s := New(&mockClient{}, "test")

	result, err := s.HandleRevoke(context.Background(), mcp.CallToolRequest{
		Params: mcp.CallToolParams{
			Name:      "revoke",
			Arguments: map[string]any{"unit_id": "not-a-ku-id"},
		},
	})
	require.NoError(t, err, "bad input is a tool error, not a protocol failure")
	require.True(t, result.IsError)
}
