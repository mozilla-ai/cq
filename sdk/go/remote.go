package cq

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"

	"github.com/mozilla-ai/cq/sdk/go/discovery"
)

// errUnreachable indicates the remote API was not reachable (transport error or 5xx).
var errUnreachable = errors.New("remote API unreachable")

// apiResolver is the slice of the discovery package used by remoteClient.
// It is an interface so tests can inject a static resolver without
// touching the disk or the network.
type apiResolver interface {
	Resolve(ctx context.Context, addr string) (discovery.NodeInfo, error)
}

// remoteClient handles HTTP communication with the remote cq API.
type remoteClient struct {
	addr       string
	apiKey     string
	httpClient *http.Client
	resolver   apiResolver
}

// newRemoteClient creates a remote API client.
// addr is the user-facing node address (no trailing slash, no version
// prefix); resolver determines the concrete API base URL via the node
// discovery protocol.
func newRemoteClient(addr string, apiKey string, timeout time.Duration, resolver apiResolver) *remoteClient {
	return &remoteClient{
		addr:   addr,
		apiKey: apiKey,
		httpClient: &http.Client{
			Timeout: timeout,
		},
		resolver: resolver,
	}
}

// confirm confirms a unit on the remote API.
// Returns errUnreachable on transport/5xx, RemoteError on 4xx.
func (r *remoteClient) confirm(ctx context.Context, unitID string) (KnowledgeUnit, error) {
	confirmURL, err := r.url(ctx, "/knowledge/"+url.PathEscape(unitID)+"/confirmations")
	if err != nil {
		return KnowledgeUnit{}, fmt.Errorf("%w: %w", errUnreachable, err)
	}

	resp, err := r.do(ctx, http.MethodPost, confirmURL, nil)
	if err != nil {
		return KnowledgeUnit{}, fmt.Errorf("%w: %w", errUnreachable, err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode >= 500 {
		return KnowledgeUnit{}, errUnreachable
	}

	if resp.StatusCode >= 400 {
		detail, _ := io.ReadAll(resp.Body)

		return KnowledgeUnit{}, &RemoteError{StatusCode: resp.StatusCode, Detail: string(detail)}
	}

	var result KnowledgeUnit
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return KnowledgeUnit{}, fmt.Errorf("%w: decoding response: %w", errUnreachable, err)
	}

	return result, nil
}

// do executes an HTTP request with optional JSON body and auth header.
// The endpoint parameter must be a fully-formed URL.
func (r *remoteClient) do(ctx context.Context, method string, endpoint string, body any) (*http.Response, error) {
	var bodyReader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("marshalling request body: %w", err)
		}

		bodyReader = bytes.NewReader(data)
	}

	req, err := http.NewRequestWithContext(ctx, method, endpoint, bodyReader)
	if err != nil {
		return nil, fmt.Errorf("creating request: %w", err)
	}

	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}

	if r.apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+r.apiKey)
	}

	return r.httpClient.Do(req)
}

// flag flags a unit on the remote API.
// Returns errUnreachable on transport/5xx, RemoteError on 4xx.
func (r *remoteClient) flag(
	ctx context.Context,
	unitID string,
	reason FlagReason,
	cfg flagConfig,
) (KnowledgeUnit, error) {
	body := map[string]string{"reason": string(reason)}
	if cfg.detail != "" {
		body["detail"] = cfg.detail
	}
	if cfg.duplicateOf != "" {
		body["duplicate_of"] = cfg.duplicateOf
	}

	flagURL, err := r.url(ctx, "/knowledge/"+url.PathEscape(unitID)+"/flags")
	if err != nil {
		return KnowledgeUnit{}, fmt.Errorf("%w: %w", errUnreachable, err)
	}

	resp, err := r.do(ctx, http.MethodPost, flagURL, body)
	if err != nil {
		return KnowledgeUnit{}, fmt.Errorf("%w: %w", errUnreachable, err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode >= 500 {
		return KnowledgeUnit{}, errUnreachable
	}

	if resp.StatusCode >= 400 {
		detail, _ := io.ReadAll(resp.Body)

		return KnowledgeUnit{}, &RemoteError{StatusCode: resp.StatusCode, Detail: string(detail)}
	}

	var result KnowledgeUnit
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return KnowledgeUnit{}, fmt.Errorf("%w: decoding response: %w", errUnreachable, err)
	}

	return result, nil
}

// propose pushes a knowledge unit to the remote API.
// Returns errUnreachable on transport/5xx errors, RemoteError on 4xx rejection.
func (r *remoteClient) propose(ctx context.Context, ku KnowledgeUnit) (KnowledgeUnit, error) {
	languages := ku.Context.Languages
	if languages == nil {
		languages = []string{}
	}

	frameworks := ku.Context.Frameworks
	if frameworks == nil {
		frameworks = []string{}
	}

	body := map[string]any{
		"domains": ku.Domains,
		"insight": map[string]string{
			"summary": ku.Insight.Summary,
			"detail":  ku.Insight.Detail,
			"action":  ku.Insight.Action,
		},
		"context": map[string]any{
			"languages":  languages,
			"frameworks": frameworks,
			"pattern":    ku.Context.Pattern,
		},
		"created_by": ku.CreatedBy,
	}

	proposeURL, err := r.url(ctx, "/knowledge")
	if err != nil {
		return KnowledgeUnit{}, fmt.Errorf("%w: %w", errUnreachable, err)
	}

	resp, err := r.do(ctx, http.MethodPost, proposeURL, body)
	if err != nil {
		return KnowledgeUnit{}, fmt.Errorf("%w: %w", errUnreachable, err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode >= 500 {
		return KnowledgeUnit{}, errUnreachable
	}

	if resp.StatusCode >= 400 {
		detail, _ := io.ReadAll(resp.Body)

		return KnowledgeUnit{}, &RemoteError{StatusCode: resp.StatusCode, Detail: string(detail)}
	}

	var result KnowledgeUnit
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		// Server accepted (2xx) but response isn't a parseable KU.
		// Return the unit with tier promoted and server-assigned fields
		// cleared; callers should not trust values that only the server
		// sets. Returning errUnreachable here would cause drain to
		// re-send the unit and create a duplicate on the server.
		ku.Tier = Private
		ku.CreatedBy = ""
		ku.Evidence.FirstObserved = nil
		ku.Evidence.LastConfirmed = nil
		return ku, nil
	}

	return result, nil
}

// query fetches knowledge units from the remote API matching params.
// Returns errUnreachable on transport/non-200 HTTP failure.
func (r *remoteClient) query(ctx context.Context, params QueryParams) ([]KnowledgeUnit, error) {
	qv := url.Values{}
	for _, d := range params.Domains {
		qv.Add("domains", d)
	}

	for _, l := range params.Languages {
		qv.Add("languages", l)
	}

	for _, f := range params.Frameworks {
		qv.Add("frameworks", f)
	}

	if params.Pattern != "" {
		qv.Set("pattern", params.Pattern)
	}

	if params.Limit > 0 {
		qv.Set("limit", fmt.Sprintf("%d", params.Limit))
	}

	base, err := r.url(ctx, "/knowledge")
	if err != nil {
		return nil, fmt.Errorf("%w: %w", errUnreachable, err)
	}

	resp, err := r.do(ctx, http.MethodGet, base+"?"+qv.Encode(), nil)
	if err != nil {
		return nil, fmt.Errorf("%w: %w", errUnreachable, err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("%w: HTTP %d", errUnreachable, resp.StatusCode)
	}

	// Pointer field distinguishes an absent or null "data" key (env.Data == nil)
	// from an empty array (env.Data != nil, *env.Data == []).
	var env struct {
		Data *[]KnowledgeUnit `json:"data"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&env); err != nil {
		return nil, fmt.Errorf("decoding remote knowledge response: %w", err)
	}

	if env.Data == nil {
		return nil, fmt.Errorf("decoding remote knowledge response: missing or null data field")
	}

	return *env.Data, nil
}

// remoteStatsResponse holds the server's knowledge stats response.
// Its fields mirror the StoreStats wire vocabulary, the canonical
// stats contract for cq-compatible servers.
type remoteStatsResponse struct {
	TotalCount             int            `json:"total_count"`
	DomainCounts           map[string]int `json:"domain_counts"`
	TierCounts             map[Tier]int   `json:"tier_counts"`
	ConfidenceDistribution map[string]int `json:"confidence_distribution"`
}

// stats fetches store statistics from the remote API.
// Returns errUnreachable on transport/5xx errors.
func (r *remoteClient) stats(ctx context.Context) (remoteStatsResponse, error) {
	statsURL, err := r.url(ctx, "/knowledge/stats")
	if err != nil {
		return remoteStatsResponse{}, fmt.Errorf("%w: %w", errUnreachable, err)
	}

	resp, err := r.do(ctx, http.MethodGet, statsURL, nil)
	if err != nil {
		return remoteStatsResponse{}, fmt.Errorf("%w: %w", errUnreachable, err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode >= 500 {
		return remoteStatsResponse{}, errUnreachable
	}

	if resp.StatusCode >= 400 {
		detail, _ := io.ReadAll(resp.Body)
		return remoteStatsResponse{}, &RemoteError{StatusCode: resp.StatusCode, Detail: string(detail)}
	}

	var result remoteStatsResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return remoteStatsResponse{}, fmt.Errorf("%w: decoding response: %w", errUnreachable, err)
	}

	return result, nil
}

// url returns the absolute URL for the given resource path on the
// configured node.
// path is the version-less API path (e.g. /knowledge or
// /knowledge/{id}/confirmations); the version prefix lives inside the
// node's advertised api_base_url.
func (r *remoteClient) url(ctx context.Context, path string) (string, error) {
	info, err := r.resolver.Resolve(ctx, r.addr)
	if err != nil {
		return "", err
	}
	return url.JoinPath(info.APIBaseURL, path)
}
