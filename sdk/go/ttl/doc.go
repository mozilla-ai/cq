// Package ttl parses the duration grammar shared by the cq platform's
// API-key TTL field. The grammar is a strict subset of Go's
// time.ParseDuration: a single positive ASCII integer followed by
// exactly one unit suffix from {s, m, h, d}. Zero is rejected because
// a zero-TTL key is meaningless. Parsing is case-insensitive on input
// but always returns the canonical lower-case form so the value the
// platform validates and persists is unambiguous regardless of which
// client emitted it.
package ttl
