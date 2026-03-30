package cq

import (
	"encoding/hex"
	"fmt"
	"regexp"

	"github.com/google/uuid"
)

// kuIDPattern matches the required knowledge unit ID format: ku_ followed by 32 lowercase hex characters.
var kuIDPattern = regexp.MustCompile(`^ku_[0-9a-f]{32}$`)

// GenerateID creates a new knowledge unit ID in the format ku_ + 32 hex chars.
func GenerateID() string {
	u := uuid.New()
	return "ku_" + hex.EncodeToString(u[:])
}

// ValidateID checks that id matches the required ku_ + 32 hex chars format.
func ValidateID(id string) error {
	if !kuIDPattern.MatchString(id) {
		return fmt.Errorf("invalid knowledge unit ID %q: must match ku_<32 lowercase hex chars>", id)
	}
	return nil
}
