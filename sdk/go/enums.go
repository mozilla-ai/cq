package cq

import (
	"slices"
	"strings"
)

// FlagReason describes why a knowledge unit was flagged.
type FlagReason string

// FlagReasons is an ordered collection of flag reasons.
type FlagReasons []FlagReason

// QuerySource indicates whether query results came from the local store or a remote API.
type QuerySource string

// ReviewStatus is the review lifecycle state of a knowledge unit.
type ReviewStatus string

// ReviewStatuses is an ordered collection of review statuses.
type ReviewStatuses []ReviewStatus

// Tier indicates the storage tier of a knowledge unit.
type Tier string

// Tiers is an ordered collection of tiers.
type Tiers []Tier

// QuerySource values indicate where query results were fetched from.
const (
	// SourceLocal means results came from the local store only (no remote configured).
	SourceLocal QuerySource = "local"

	// SourceRemote means a remote API was queried.
	SourceRemote QuerySource = "remote"
)

// ReviewStatus values identify a knowledge unit's point in the review
// lifecycle. The order below is the lifecycle, not alphabetical.
const (
	// Pending means the unit is awaiting review.
	Pending ReviewStatus = "pending"

	// Approved means a reviewer accepted the unit and it is in circulation.
	Approved ReviewStatus = "approved"

	// Rejected means a reviewer declined the unit.
	Rejected ReviewStatus = "rejected"

	// Revoked means the unit's own author withdrew it.
	Revoked ReviewStatus = "revoked"
)

// Tier values identify where a knowledge unit is stored.
const (
	// Local is a locally-stored knowledge unit.
	Local Tier = "local"

	// Private is shared on a remote store with restricted access.
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

// AllReviewStatuses returns the valid review statuses in lifecycle order.
func AllReviewStatuses() ReviewStatuses {
	return ReviewStatuses{Pending, Approved, Rejected, Revoked}
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

// Valid reports whether s is a known review status.
func (s ReviewStatus) Valid() bool {
	switch s {
	case Pending, Approved, Rejected, Revoked:
		return true
	default:
		return false
	}
}

// Valid reports whether t is a known tier.
func (t Tier) Valid() bool {
	switch t {
	case Local, Private, Public:
		return true
	default:
		return false
	}
}

// String returns a comma-separated list of flag reasons.
func (r FlagReasons) String() string {
	names := make([]string, len(r))
	for i, reason := range r {
		names[i] = string(reason)
	}
	return strings.Join(names, ", ")
}

// String returns a comma-separated list of review statuses.
func (r ReviewStatuses) String() string {
	names := make([]string, len(r))
	for i, status := range r {
		names[i] = string(status)
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
