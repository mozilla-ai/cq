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

func TestFlagReasons(t *testing.T) {
	t.Parallel()

	reasons := AllFlagReasons()
	require.Len(t, reasons, 3)
	require.Equal(t, Duplicate, reasons[0])
	require.Equal(t, Incorrect, reasons[1])
	require.Equal(t, Stale, reasons[2])
}

func TestFlagReasonsString(t *testing.T) {
	t.Parallel()

	require.Equal(t, "duplicate, incorrect, stale", AllFlagReasons().String())
}

func TestTiers(t *testing.T) {
	t.Parallel()

	tiers := AllTiers()
	require.Len(t, tiers, 3)
	require.Equal(t, Local, tiers[0])
	require.Equal(t, Private, tiers[1])
	require.Equal(t, Public, tiers[2])
}

func TestTiersString(t *testing.T) {
	t.Parallel()

	require.Equal(t, "local, private, public", AllTiers().String())
}
