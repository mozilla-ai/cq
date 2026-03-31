package cq

import (
	"slices"
	"strings"
)

// FlagReason describes why a knowledge unit was flagged.
type FlagReason string

// FlagReasons is an ordered collection of flag reasons.
type FlagReasons []FlagReason

// Tier indicates the storage tier of a knowledge unit.
type Tier string

// Tiers is an ordered collection of tiers.
type Tiers []Tier

// Tier values identify where a knowledge unit is stored.
const (
	// Local is a locally-stored knowledge unit.
	Local Tier = "local"

	// Private is shared within a team.
	Private Tier = "private"

	// Public is publicly shared.
	Public Tier = "public"
)

// FlagReason values describe why a knowledge unit was flagged.
const (
	// Duplicate means another unit covers the same insight.
	Duplicate FlagReason = "duplicate"

	// Incorrect means the knowledge is factually wrong.
	Incorrect FlagReason = "incorrect"

	// Stale means the knowledge is outdated.
	Stale FlagReason = "stale"
)

// AllFlagReasons returns the valid flag reasons in sorted order.
func AllFlagReasons() FlagReasons {
	r := FlagReasons{Duplicate, Incorrect, Stale}
	slices.Sort(r)
	return r
}

// AllTiers returns the valid tiers in sorted order.
func AllTiers() Tiers {
	t := Tiers{Local, Private, Public}
	slices.Sort(t)
	return t
}

// IsRemote reports whether the tier represents a remotely-stored unit.
func (t Tier) IsRemote() bool {
	return t == Private || t == Public
}

// String returns a comma-separated list of flag reasons.
func (r FlagReasons) String() string {
	names := make([]string, len(r))
	for i, reason := range r {
		names[i] = string(reason)
	}
	return strings.Join(names, ", ")
}

// String returns a comma-separated list of tiers.
func (t Tiers) String() string {
	names := make([]string, len(t))
	for i, tier := range t {
		names[i] = string(tier)
	}
	return strings.Join(names, ", ")
}
