package cq

import (
	"context"
	"errors"
	"fmt"
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
// It reads CQ_TEAM_ADDR, CQ_ADDR, CQ_API_KEY, and CQ_LOCAL_DB_PATH from the environment.
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
// remote only. If the remote is unreachable, falls back to local storage.
// If the remote rejects the proposal, returns a RemoteError.
// With no remote configured, always stores locally.
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

	if c.remote != nil {
		result, err := c.remote.propose(ctx, ku)
		if err != nil && !errors.Is(err, errUnreachable) {
			return KnowledgeUnit{}, err
		}

		if err == nil {
			return result, nil
		}

		// Remote unreachable; fall back to local storage.
	}

	now := time.Now()
	ku.Evidence.FirstObserved = &now
	ku.Evidence.LastConfirmed = &now

	if err := c.store.insert(ku); err != nil {
		return KnowledgeUnit{}, fmt.Errorf("inserting knowledge unit: %w", err)
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

	storeResult, err := c.store.query(qOpts...)
	if err != nil {
		return QueryResult{}, fmt.Errorf("querying store: %w", err)
	}

	localResults := storeResult.KUs

	if c.remote == nil {
		return QueryResult{
			Units:    localResults,
			Source:   "local",
			Warnings: storeResult.Warnings,
		}, nil
	}

	normalised := params
	normalised.Limit = limit
	remoteResults := c.remote.query(ctx, normalised)

	source := "local"
	if len(remoteResults) > 0 && len(localResults) > 0 {
		source = "both"
	} else if len(remoteResults) > 0 {
		source = "remote"
	}

	return QueryResult{
		Units:    mergeResults(localResults, remoteResults, limit),
		Source:   source,
		Warnings: storeResult.Warnings,
	}, nil
}

// Status returns aggregated statistics about the knowledge store.
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
