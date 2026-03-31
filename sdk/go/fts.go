package cq

import "strings"

const (
	// ftsMaxTerms is the maximum number of search terms included in an FTS5 MATCH expression.
	ftsMaxTerms = 20

	// ftsMaxTermLength is the maximum rune length of a single search term after sanitisation.
	ftsMaxTermLength = 200
)

// buildFTSMatchExpr builds a safe FTS5 MATCH expression from untrusted search terms.
// It strips double quotes (the only character that breaks FTS5 phrase queries),
// truncates to ftsMaxTermLength, wraps each surviving term in double quotes,
// and joins with OR. At most ftsMaxTerms terms are included.
// Returns empty string when no usable terms remain.
func buildFTSMatchExpr(terms []string) string {
	safe := make([]string, 0, min(len(terms), ftsMaxTerms))

	for _, t := range terms {
		if len(safe) >= ftsMaxTerms {
			break
		}

		cleaned := strings.ReplaceAll(t, `"`, "")
		cleaned = strings.TrimSpace(cleaned)

		if len(cleaned) > ftsMaxTermLength {
			// Truncate at a rune boundary to avoid splitting multi-byte UTF-8.
			cleaned = string([]rune(cleaned)[:ftsMaxTermLength])
		}

		if cleaned == "" {
			continue
		}

		safe = append(safe, `"`+cleaned+`"`)
	}

	return strings.Join(safe, " OR ")
}
