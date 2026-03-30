package cq

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestTierIsRemote(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name     string
		tier     Tier
		expected bool
	}{
		{name: "local", tier: Local, expected: false},
		{name: "private", tier: Private, expected: true},
		{name: "public", tier: Public, expected: true},
		{name: "empty string", tier: "", expected: false},
		{name: "unknown value", tier: "something", expected: false},
		{name: "legacy proto local", tier: "TIER_LOCAL", expected: false},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			require.Equal(t, tc.expected, tc.tier.IsRemote())
		})
	}
}

func TestTierValues(t *testing.T) {
	t.Parallel()

	require.Equal(t, Tier("local"), Local)
	require.Equal(t, Tier("private"), Private)
	require.Equal(t, Tier("public"), Public)
}

func TestFlagReasonValues(t *testing.T) {
	t.Parallel()

	require.Equal(t, FlagReason("stale"), Stale)
	require.Equal(t, FlagReason("incorrect"), Incorrect)
	require.Equal(t, FlagReason("duplicate"), Duplicate)
}
