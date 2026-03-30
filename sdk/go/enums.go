package cq

// FlagReason describes why a knowledge unit was flagged.
type FlagReason string

// Tier indicates the storage tier of a knowledge unit.
type Tier string

const (
	// Local is a locally-stored knowledge unit.
	Local Tier = "local"

	// Private is shared within a team.
	Private Tier = "private"

	// Public is publicly shared.
	Public Tier = "public"
)

const (
	// Duplicate means another unit covers the same insight.
	Duplicate FlagReason = "duplicate"

	// Incorrect means the knowledge is factually wrong.
	Incorrect FlagReason = "incorrect"

	// Stale means the knowledge is outdated.
	Stale FlagReason = "stale"
)

// IsRemote reports whether the tier represents a remotely-stored unit.
func (t Tier) IsRemote() bool {
	return t == Private || t == Public
}
