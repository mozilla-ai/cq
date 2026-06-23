package cq

import (
	"fmt"
	"regexp"
)

// extensionKeyPattern matches the required namespace:key format for extension keys.
var extensionKeyPattern = regexp.MustCompile(`^[a-z0-9][a-z0-9_-]*:\S+$`)

// ValidateExtensionKeys checks that every key in extensions uses namespace:key format.
func ValidateExtensionKeys(extensions map[string]any) error {
	for k := range extensions {
		if !extensionKeyPattern.MatchString(k) {
			return fmt.Errorf("extension key %s must match namespace:key format (e.g. myimpl:field)", k)
		}
	}
	return nil
}
