package postgres_test

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	cq "github.com/mozilla-ai/cq/sdk/go"

	"github.com/mozilla-ai/cq/sdk/go/stores/postgres"
)

func TestNew(t *testing.T) {
	t.Parallel()

	tcs := []struct {
		name       string
		connString string
		wantErr    string
	}{
		{
			name:       "empty connection string",
			connString: "",
			wantErr:    "connection string must not be empty",
		},
		{
			name:       "malformed URL",
			connString: "://not-a-url",
			wantErr:    "invalid connection string",
		},
		{
			name:       "unreachable host",
			connString: "postgres://localhost:1/nonexistent",
			wantErr:    "connecting to server",
		},
	}
	for _, tc := range tcs {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			_, err := postgres.New(context.Background(), tc.connString)
			require.Error(t, err)
			require.Contains(t, err.Error(), tc.wantErr)
		})
	}
}

func TestNewRespectsCancelledContext(t *testing.T) {
	t.Parallel()

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_, err := postgres.New(ctx, "postgres://localhost:1/nonexistent")
	require.Error(t, err)
	require.ErrorIs(t, err, context.Canceled)
}

func TestMarshalUnmarshalRoundTrip(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC().Truncate(time.Second)
	tcs := []struct {
		name string
		ku   cq.KnowledgeUnit
	}{
		{
			name: "minimal unit",
			ku: cq.KnowledgeUnit{
				ID:      "ku_00000000000000000000000000000001",
				Version: 1,
				Domains: []string{"api"},
				Insight: cq.Insight{
					Summary: "summary",
					Detail:  "detail",
					Action:  "action",
				},
				Evidence: cq.Evidence{
					Confidence:    0.5,
					Confirmations: 1,
					FirstObserved: &now,
					LastConfirmed: &now,
				},
				Tier:  cq.Local,
				Flags: []cq.Flag{},
			},
		},
		{
			name: "unit with extensions",
			ku: cq.KnowledgeUnit{
				ID:      "ku_00000000000000000000000000000002",
				Version: 1,
				Domains: []string{"api", "security"},
				Insight: cq.Insight{
					Summary: "CVE-2025-1234 in libfoo",
					Detail:  "Buffer overflow in parsing",
					Action:  "Upgrade to >= 2.0.1",
				},
				Context: cq.Context{
					Languages:  []string{"go"},
					Frameworks: []string{"grpc"},
					Pattern:    "dependency-vulnerability",
				},
				Evidence: cq.Evidence{
					Confidence:    0.9,
					Confirmations: 5,
					FirstObserved: &now,
					LastConfirmed: &now,
				},
				Tier:       cq.Local,
				Extensions: map[string]any{"vuln:cvss": 7.5},
				Flags:      []cq.Flag{},
			},
		},
		{
			name: "unit with empty optional fields",
			ku: cq.KnowledgeUnit{
				ID:      "ku_00000000000000000000000000000003",
				Version: 1,
				Domains: []string{"testing"},
				Insight: cq.Insight{
					Summary: "s",
					Detail:  "d",
					Action:  "a",
				},
				Evidence: cq.Evidence{
					Confidence:    0.0,
					Confirmations: 0,
				},
				Tier:  cq.Local,
				Flags: []cq.Flag{},
			},
		},
	}
	for _, tc := range tcs {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			data, err := json.Marshal(tc.ku)
			require.NoError(t, err)

			var got cq.KnowledgeUnit
			require.NoError(t, json.Unmarshal(data, &got))

			require.Equal(t, tc.ku.ID, got.ID)
			require.Equal(t, tc.ku.Version, got.Version)
			require.Equal(t, tc.ku.Domains, got.Domains)
			require.Equal(t, tc.ku.Insight.Summary, got.Insight.Summary)
			require.Equal(t, tc.ku.Insight.Detail, got.Insight.Detail)
			require.Equal(t, tc.ku.Insight.Action, got.Insight.Action)
			require.InDelta(t, tc.ku.Evidence.Confidence, got.Evidence.Confidence, 0.001)
			require.Equal(t, tc.ku.Tier, got.Tier)
		})
	}
}

func TestUnmarshalInvalidJSON(t *testing.T) {
	t.Parallel()

	tcs := []struct {
		name string
		data string
	}{
		{
			name: "empty string",
			data: "",
		},
		{
			name: "bare string",
			data: `"hello"`,
		},
		{
			name: "truncated object",
			data: `{"id": "ku_0000000000000000000000000000`,
		},
		{
			name: "wrong type",
			data: `[1, 2, 3]`,
		},
	}
	for _, tc := range tcs {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			var ku cq.KnowledgeUnit
			require.Error(t, json.Unmarshal([]byte(tc.data), &ku))
		})
	}
}
