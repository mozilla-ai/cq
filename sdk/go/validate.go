package cq

import (
	"errors"
	"fmt"
	"unicode/utf8"

	cqschema "github.com/mozilla-ai/cq/schema"
)

// validateCount rejects items when it holds more than limit entries, naming the
// plural field, the ceiling, and the actual count.
func validateCount(field string, items []string, limit int) error {
	if n := len(items); n > limit {
		return fmt.Errorf("%s must have at most %d items, got %d", field, limit, n)
	}
	return nil
}

// validateItemLengths rejects any element of items that exceeds limit
// characters, naming the singular field for each violation.
func validateItemLengths(field string, items []string, limit int) error {
	errs := make([]error, 0, len(items))
	for _, item := range items {
		errs = append(errs, validateLength(field, item, limit))
	}
	return errors.Join(errs...)
}

// validateLength rejects value when it exceeds limit characters, naming the
// field, the ceiling, and the actual length. Length is counted in Unicode code
// points to match the schema's maxLength semantics, so a multibyte string is
// measured the same way here as at the wire boundary.
func validateLength(field string, value string, limit int) error {
	if n := utf8.RuneCountInString(value); n > limit {
		return fmt.Errorf("%s must be at most %d characters, got %d", field, limit, n)
	}
	return nil
}

// validateNonEmpty rejects an empty tag list, naming the plural field. It
// enforces the schema's minItems:1 lower bound, a bare presence check with no
// ceiling value to source and so no schema accessor.
func validateNonEmpty(field string, items []string) error {
	if len(items) == 0 {
		return fmt.Errorf("%s must not be empty", field)
	}
	return nil
}

// validateProposeParams rejects params that break a schema-declared bound —
// its required at-least-one-domain lower bound, or any free-text or tag-list
// ceiling — collecting every violation so a producer can fix them in one pass.
// Each ceiling comes from the schema package, never a hardcoded literal, and a
// violating value fails the whole propose rather than being truncated.
func validateProposeParams(params ProposeParams) error {
	return errors.Join(
		validateLength("summary", params.Summary, cqschema.SummaryMaxLength()),
		validateLength("detail", params.Detail, cqschema.DetailMaxLength()),
		validateLength("action", params.Action, cqschema.ActionMaxLength()),
		validateLength("created_by", params.CreatedBy, cqschema.CreatedByMaxLength()),
		validateLength("pattern", params.Pattern, cqschema.PatternMaxLength()),
		validateItemLengths("domain", params.Domains, cqschema.DomainMaxLength()),
		validateItemLengths("language", params.Languages, cqschema.LanguageMaxLength()),
		validateItemLengths("framework", params.Frameworks, cqschema.FrameworkMaxLength()),
		validateNonEmpty("domains", params.Domains),
		validateCount("domains", params.Domains, cqschema.DomainsMaxItems()),
		validateCount("languages", params.Languages, cqschema.LanguagesMaxItems()),
		validateCount("frameworks", params.Frameworks, cqschema.FrameworksMaxItems()),
	)
}
