package cq

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"time"
)

// Client-level defaults and bounds for query parameters and new knowledge units.
const (
	// defaultQueryLimit is used when QueryParams.Limit is unset or invalid.
	defaultQueryLimit = 5

	// defaultRecentLimit controls how many recent units Status returns.
	defaultRecentLimit = 5

	// maxClientQueryLimit caps QueryParams.Limit to bound local/remote fan-out.
	maxClientQueryLimit = 50

	// defaultKnowledgeUnitVersion is the schema version assigned to new units.
	defaultKnowledgeUnitVersion = 1

	// defaultEvidenceConfidence is the starting confidence for a new unit.
	defaultEvidenceConfidence = 0.5

	// defaultEvidenceConfirmations is the starting confirmation count for a new unit.
	defaultEvidenceConfirmations = 1
)

// Client provides access to the cq knowledge store.
// Create one with NewClient and close it when done.
type Client struct {
	store   *localStore
	remote  *remoteClient
	timeout time.Duration
}

// NewClient creates a new cq client.
// It reads CQ_ADDR, CQ_API_KEY, and CQ_LOCAL_DB_PATH from the environment.
// Options override environment variables.
// If no remote address is configured, the client operates in local-only mode.
func NewClient(opts ...ClientOption) (*Client, error) {
	cfg, err := resolveConfig(opts...)
	if err != nil {
		return nil, err
	}

	s, err := newLocalStore(cfg.localDBPath)
	if err != nil {
		return nil, fmt.Errorf("opening local store: %w", err)
	}

	c := &Client{store: s, timeout: cfg.timeout}
	if cfg.addr != "" {
		c.remote = newRemoteClient(cfg.addr, cfg.apiKey, cfg.timeout)
	}

	return c, nil
}

// Close releases all resources held by the client.
func (c *Client) Close() error {
	c.store.close()

	return nil
}

// HasRemote reports whether the client is configured with a remote API.
func (c *Client) HasRemote() bool {
	return c.remote != nil
}

// Confirm boosts the confidence of a knowledge unit.
// Routes to local store or remote API based on the unit's tier.
func (c *Client) Confirm(ctx context.Context, ku KnowledgeUnit) (KnowledgeUnit, error) {
	ctx, cancel := c.operationContext(ctx)
	defer cancel()

	if err := ctx.Err(); err != nil {
		return KnowledgeUnit{}, err
	}

	if !ku.Tier.IsRemote() {
		stored, err := c.store.get(ku.ID)
		if err != nil {
			return KnowledgeUnit{}, fmt.Errorf("reading knowledge unit: %w", err)
		}

		if stored == nil {
			return KnowledgeUnit{}, fmt.Errorf("%w: %s", ErrNotFound, ku.ID)
		}

		updated := applyConfirmation(*stored)
		if err := c.store.update(updated); err != nil {
			return KnowledgeUnit{}, fmt.Errorf("updating knowledge unit: %w", err)
		}

		return updated, nil
	}

	if c.remote == nil {
		return KnowledgeUnit{}, fmt.Errorf(
			"knowledge unit %s has tier %s but no remote API is configured",
			ku.ID,
			ku.Tier,
		)
	}

	result, err := c.remote.confirm(ctx, ku.ID)
	if err != nil {
		return KnowledgeUnit{}, fmt.Errorf("remote confirm failed: %w", err)
	}

	return result, nil
}

// Drain pushes all locally-stored knowledge units to the remote API.
// Successfully pushed units are deleted from local storage.
func (c *Client) Drain(ctx context.Context) (DrainResult, error) {
	ctx, cancel := c.operationContext(ctx)
	defer cancel()

	if err := ctx.Err(); err != nil {
		return DrainResult{}, err
	}

	if c.remote == nil {
		return DrainResult{}, fmt.Errorf("no remote API configured")
	}

	units, err := c.store.all()
	if err != nil {
		return DrainResult{}, fmt.Errorf("reading local units: %w", err)
	}

	var result DrainResult

	for _, ku := range units {
		if err := ctx.Err(); err != nil {
			result.Warnings = append(result.Warnings, err)
			break
		}

		if ku.Tier != Local {
			continue
		}

		_, err := c.remote.propose(ctx, ku)
		if err != nil {
			result.Warnings = append(result.Warnings, fmt.Errorf("pushing %s: %w", ku.ID, err))

			continue
		}

		if err := c.store.delete(ku.ID); err != nil {
			result.Warnings = append(result.Warnings, fmt.Errorf("deleting local %s: %w", ku.ID, err))

			continue
		}

		result.Pushed++
	}

	return result, nil
}

// DrainableCount returns the number of local units that Drain would push.
func (c *Client) DrainableCount(ctx context.Context) (int, error) {
	select {
	case <-ctx.Done():
		return 0, ctx.Err()
	default:
	}

	units, err := c.store.all()
	if err != nil {
		return 0, fmt.Errorf("reading local units: %w", err)
	}

	var count int
	for _, ku := range units {
		if ku.Tier == Local {
			count++
		}
	}

	return count, nil
}

// Flag marks a knowledge unit as problematic and reduces its confidence.
// Routes to local store or remote API based on the unit's tier.
// When reason is Duplicate, WithDuplicateOf must be provided.
func (c *Client) Flag(ctx context.Context, ku KnowledgeUnit, reason FlagReason, opts ...FlagOption) (KnowledgeUnit, error) {
	ctx, cancel := c.operationContext(ctx)
	defer cancel()

	if err := ctx.Err(); err != nil {
		return KnowledgeUnit{}, err
	}

	cfg := resolveFlagConfig(opts)

	if reason == Duplicate && cfg.duplicateOf == "" {
		return KnowledgeUnit{}, fmt.Errorf("duplicate requires WithDuplicateOf option")
	}

	if cfg.duplicateOf != "" {
		if err := ValidateID(cfg.duplicateOf); err != nil {
			return KnowledgeUnit{}, fmt.Errorf("invalid duplicate_of: %w", err)
		}
	}

	if !ku.Tier.IsRemote() {
		stored, err := c.store.get(ku.ID)
		if err != nil {
			return KnowledgeUnit{}, fmt.Errorf("reading knowledge unit: %w", err)
		}

		if stored == nil {
			return KnowledgeUnit{}, fmt.Errorf("%w: %s", ErrNotFound, ku.ID)
		}

		updated := applyFlag(*stored, reason, cfg)
		if err := c.store.update(updated); err != nil {
			return KnowledgeUnit{}, fmt.Errorf("updating knowledge unit: %w", err)
		}

		return updated, nil
	}

	if c.remote == nil {
		return KnowledgeUnit{}, fmt.Errorf(
			"knowledge unit %s has tier %s but no remote API is configured",
			ku.ID,
			ku.Tier,
		)
	}

	result, err := c.remote.flag(ctx, ku.ID, reason, cfg)
	if err != nil {
		return KnowledgeUnit{}, fmt.Errorf("remote flag failed: %w", err)
	}

	return result, nil
}

// Prompt returns the canonical cq agent protocol prompt.
// This is a convenience method that delegates to the package-level Prompt function.
func (c *Client) Prompt() string {
	return Prompt()
}

// Propose creates a new knowledge unit.
// When a remote API is configured and reachable, the unit is sent to the
// remote only and returned with no error. The remote is the source of
// truth for server-assigned fields; in particular, Tier is promoted to
// Private and CreatedBy is overwritten with the authenticated caller.
// If the remote is unreachable (transport/5xx) or rejects the request
// with an auth error (401/403), the unit is stored locally with Tier
// Local and a *FallbackError is returned carrying the local unit and
// the underlying cause; the unit will drain on the next successful
// connection. Other 4xx errors (400, 409, 422) are returned as
// *RemoteError with nothing stored — the data is the problem, not
// connectivity. With no remote configured, always stores locally with
// no error.
func (c *Client) Propose(ctx context.Context, params ProposeParams) (KnowledgeUnit, error) {
	ctx, cancel := c.operationContext(ctx)
	defer cancel()

	if err := ctx.Err(); err != nil {
		return KnowledgeUnit{}, err
	}

	ku := KnowledgeUnit{
		ID:      GenerateID(),
		Version: defaultKnowledgeUnitVersion,
		Domains: params.Domains,
		Insight: Insight{
			Summary: params.Summary,
			Detail:  params.Detail,
			Action:  params.Action,
		},
		Context: Context{
			Languages:  params.Languages,
			Frameworks: params.Frameworks,
			Pattern:    params.Pattern,
		},
		Evidence: Evidence{
			Confidence:    defaultEvidenceConfidence,
			Confirmations: defaultEvidenceConfirmations,
		},
		Tier:      Local,
		CreatedBy: params.CreatedBy,
	}

	var remoteErr error

	if c.remote != nil {
		result, err := c.remote.propose(ctx, ku)
		if err == nil {
			return result, nil
		}

		var re *RemoteError
		isAuthReject := errors.As(err, &re) &&
			(re.StatusCode == http.StatusUnauthorized || re.StatusCode == http.StatusForbidden)
		if !isAuthReject && !errors.Is(err, errUnreachable) {
			return KnowledgeUnit{}, err
		}
		remoteErr = err
	}

	now := time.Now()
	ku.Evidence.FirstObserved = &now
	ku.Evidence.LastConfirmed = &now

	if err := c.store.insert(ku); err != nil {
		insertErr := fmt.Errorf("inserting knowledge unit: %w", err)
		if remoteErr != nil {
			return KnowledgeUnit{}, fmt.Errorf("fallback insert after remote failure: %w", errors.Join(remoteErr, insertErr))
		}
		return KnowledgeUnit{}, insertErr
	}

	if remoteErr != nil {
		return ku, &FallbackError{LocalUnit: ku, Err: remoteErr}
	}
	return ku, nil
}

// Query searches for knowledge units matching the given domain tags.
// When a remote API is configured, results from both local and remote are
// merged, deduplicated by ID (local wins), and truncated to the limit.
func (c *Client) Query(ctx context.Context, params QueryParams) (QueryResult, error) {
	ctx, cancel := c.operationContext(ctx)
	defer cancel()

	if err := ctx.Err(); err != nil {
		return QueryResult{}, err
	}

	limit := params.Limit
	if limit <= 0 {
		limit = defaultQueryLimit
	}

	if limit > maxClientQueryLimit {
		limit = maxClientQueryLimit
	}

	qOpts := []queryOption{withLimit(limit)}
	for _, d := range params.Domains {
		qOpts = append(qOpts, withDomain(d))
	}

	for _, l := range params.Languages {
		qOpts = append(qOpts, withLanguage(l))
	}

	for _, f := range params.Frameworks {
		qOpts = append(qOpts, withFramework(f))
	}

	if params.Pattern != "" {
		qOpts = append(qOpts, withPattern(params.Pattern))
	}

	storeResult, err := c.store.query(qOpts...)
	if err != nil {
		return QueryResult{}, fmt.Errorf("querying store: %w", err)
	}

	localResults := storeResult.KUs

	if c.remote == nil {
		return QueryResult{
			Units:    localResults,
			Source:   SourceLocal,
			Warnings: storeResult.Warnings,
		}, nil
	}

	normalised := params
	normalised.Limit = limit
	remoteResults := c.remote.query(ctx, normalised)

	return QueryResult{
		Units:    mergeResults(localResults, remoteResults, limit),
		Source:   SourceRemote,
		Warnings: storeResult.Warnings,
	}, nil
}

// Status returns aggregated statistics about the knowledge store.
// When a remote API is configured and reachable, tier counts include
// both local and remote breakdowns. If the remote is unreachable,
// only local counts are returned.
func (c *Client) Status(ctx context.Context) (StoreStats, error) {
	ctx, cancel := c.operationContext(ctx)
	defer cancel()

	if err := ctx.Err(); err != nil {
		return StoreStats{}, err
	}

	stats, err := c.store.stats(defaultRecentLimit)
	if err != nil {
		return StoreStats{}, fmt.Errorf("reading store stats: %w", err)
	}

	if err := ctx.Err(); err != nil {
		return StoreStats{}, err
	}

	stats.TierCounts = map[Tier]int{Local: stats.TotalCount}

	if c.remote != nil {
		remote, err := c.remote.stats(ctx)
		if err == nil {
			for tier, count := range remote.Tiers {
				// The remote store should never report a "local" tier, but guard
				// against it to prevent overwriting the local count we already set.
				if tier == Local {
					continue
				}
				stats.TierCounts[tier] = count
				stats.TotalCount += count
			}
			for domain, count := range remote.Domains {
				stats.DomainCounts[domain] += count
			}
		}
	}

	return stats, nil
}

// operationContext ensures client operations consistently respect request timeout.
func (c *Client) operationContext(ctx context.Context) (context.Context, context.CancelFunc) {
	if ctx == nil {
		ctx = context.Background()
	}

	if _, hasDeadline := ctx.Deadline(); hasDeadline {
		return ctx, func() {}
	}

	if c.timeout <= 0 {
		return ctx, func() {}
	}

	return context.WithTimeout(ctx, c.timeout)
}

// mergeResults deduplicates local and remote results by ID (local wins)
// and truncates to the limit.
func mergeResults(local []KnowledgeUnit, remote []KnowledgeUnit, limit int) []KnowledgeUnit {
	seen := make(map[string]struct{}, len(local))
	merged := make([]KnowledgeUnit, 0, len(local)+len(remote))

	for _, u := range local {
		seen[u.ID] = struct{}{}
		merged = append(merged, u)
	}

	for _, u := range remote {
		if _, ok := seen[u.ID]; !ok {
			merged = append(merged, u)
		}
	}

	if len(merged) > limit {
		merged = merged[:limit]
	}

	return merged
}
