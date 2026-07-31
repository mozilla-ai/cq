package cq

import (
	"context"
	"fmt"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"

	cqschema "github.com/mozilla-ai/cq/schema"
)

// validParams returns propose params with every field within its ceiling, so a
// test can push exactly one field over the limit in isolation.
func validParams() ProposeParams {
	return ProposeParams{
		Summary: "s",
		Detail:  "d",
		Action:  "a",
		Domains: []string{"test"},
	}
}

// makeTags returns n single-character tags, each well within any per-item
// ceiling, so only the item count varies.
func makeTags(n int) []string {
	tags := make([]string, n)
	for i := range tags {
		tags[i] = "t"
	}
	return tags
}

// lengthCase pushes a single free-text field of ProposeParams to a chosen
// length. field is the token the rejection message must name.
type lengthCase struct {
	field string
	limit int
	set   func(params *ProposeParams, value string)
}

func proposeLengthCases() []lengthCase {
	return []lengthCase{
		{"summary", cqschema.SummaryMaxLength(), func(p *ProposeParams, v string) { p.Summary = v }},
		{"detail", cqschema.DetailMaxLength(), func(p *ProposeParams, v string) { p.Detail = v }},
		{"action", cqschema.ActionMaxLength(), func(p *ProposeParams, v string) { p.Action = v }},
		{"created_by", cqschema.CreatedByMaxLength(), func(p *ProposeParams, v string) { p.CreatedBy = v }},
		{"pattern", cqschema.PatternMaxLength(), func(p *ProposeParams, v string) { p.Pattern = v }},
		{"domain", cqschema.DomainMaxLength(), func(p *ProposeParams, v string) { p.Domains = []string{v} }},
		{"language", cqschema.LanguageMaxLength(), func(p *ProposeParams, v string) { p.Languages = []string{v} }},
		{"framework", cqschema.FrameworkMaxLength(), func(p *ProposeParams, v string) { p.Frameworks = []string{v} }},
	}
}

// countCase pushes a single tag list of ProposeParams to a chosen cardinality.
type countCase struct {
	field string
	limit int
	set   func(params *ProposeParams, n int)
}

func proposeCountCases() []countCase {
	return []countCase{
		{"domains", cqschema.DomainsMaxItems(), func(p *ProposeParams, n int) { p.Domains = makeTags(n) }},
		{"languages", cqschema.LanguagesMaxItems(), func(p *ProposeParams, n int) { p.Languages = makeTags(n) }},
		{"frameworks", cqschema.FrameworksMaxItems(), func(p *ProposeParams, n int) { p.Frameworks = makeTags(n) }},
	}
}

func TestValidateProposeParamsAcceptsAtMaxLength(t *testing.T) {
	t.Parallel()
	for _, tc := range proposeLengthCases() {
		t.Run(tc.field, func(t *testing.T) {
			t.Parallel()
			params := validParams()
			tc.set(&params, strings.Repeat("x", tc.limit))
			require.NoError(t, validateProposeParams(params))
		})
	}
}

func TestValidateProposeParamsRejectsOverMaxLength(t *testing.T) {
	t.Parallel()
	for _, tc := range proposeLengthCases() {
		t.Run(tc.field, func(t *testing.T) {
			t.Parallel()
			params := validParams()
			over := tc.limit + 1
			tc.set(&params, strings.Repeat("x", over))
			want := fmt.Sprintf("%s must be at most %d characters, got %d", tc.field, tc.limit, over)
			require.EqualError(t, validateProposeParams(params), want)
		})
	}
}

func TestValidateProposeParamsAcceptsAtMaxItems(t *testing.T) {
	t.Parallel()
	for _, tc := range proposeCountCases() {
		t.Run(tc.field, func(t *testing.T) {
			t.Parallel()
			params := validParams()
			tc.set(&params, tc.limit)
			require.NoError(t, validateProposeParams(params))
		})
	}
}

func TestValidateProposeParamsRejectsOverMaxItems(t *testing.T) {
	t.Parallel()
	for _, tc := range proposeCountCases() {
		t.Run(tc.field, func(t *testing.T) {
			t.Parallel()
			params := validParams()
			over := tc.limit + 1
			tc.set(&params, over)
			want := fmt.Sprintf("%s must have at most %d items, got %d", tc.field, tc.limit, over)
			require.EqualError(t, validateProposeParams(params), want)
		})
	}
}

// TestValidateProposeParamsCountsRunesNotBytes guards the schema's maxLength
// semantics: length is measured in Unicode code points, so a multibyte string
// at the character ceiling is accepted even though its byte length is larger.
func TestValidateProposeParamsCountsRunesNotBytes(t *testing.T) {
	t.Parallel()
	params := validParams()
	params.Summary = strings.Repeat("汉", cqschema.SummaryMaxLength())
	require.NoError(t, validateProposeParams(params))
}

// TestProposeRejectsOverLimitFieldStoresNothing proves the boundary rejects
// over-limit input rather than truncating or persisting it.
func TestProposeRejectsOverLimitFieldStoresNothing(t *testing.T) {
	c := newTestClient(t)
	ctx := context.Background()

	params := validParams()
	params.Summary = strings.Repeat("x", cqschema.SummaryMaxLength()+1)

	_, err := c.Propose(ctx, params)
	want := fmt.Sprintf(
		"summary must be at most %d characters, got %d",
		cqschema.SummaryMaxLength(), cqschema.SummaryMaxLength()+1,
	)
	require.EqualError(t, err, want)

	count, err := c.DrainableCount(ctx)
	require.NoError(t, err)
	require.Zero(t, count)
}

func TestFlagAcceptsAtMaxLengthDetail(t *testing.T) {
	c := newTestClient(t)
	ctx := context.Background()

	ku, err := c.Propose(ctx, validParams())
	require.NoError(t, err)

	_, err = c.Flag(ctx, ku, Stale, WithDetail(strings.Repeat("x", cqschema.FlagDetailMaxLength())))
	require.NoError(t, err)
}

func TestFlagRejectsOverMaxLengthDetail(t *testing.T) {
	c := newTestClient(t)
	ctx := context.Background()

	ku, err := c.Propose(ctx, validParams())
	require.NoError(t, err)

	over := cqschema.FlagDetailMaxLength() + 1
	_, err = c.Flag(ctx, ku, Stale, WithDetail(strings.Repeat("x", over)))
	want := fmt.Sprintf("flag detail must be at most %d characters, got %d", cqschema.FlagDetailMaxLength(), over)
	require.EqualError(t, err, want)
}
