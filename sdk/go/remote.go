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
)

// errUnreachable indicates the remote API was not reachable (transport error or 5xx).
var errUnreachable = errors.New("remote API unreachable")

// remoteClient handles HTTP communication with the remote cq API.
type remoteClient struct {
	baseURL    string
	apiKey     string
	httpClient *http.Client
}

// newRemoteClient creates a remote API client with the given base URL, API key, and timeout.
func newRemoteClient(baseURL string, apiKey string, timeout time.Duration) *remoteClient {
	return &remoteClient{
		baseURL: baseURL,
		apiKey:  apiKey,
		httpClient: &http.Client{
			Timeout: timeout,
		},
	}
}

// confirm confirms a unit on the remote API.
// Returns errUnreachable on transport/5xx, RemoteError on 4xx.
func (r *remoteClient) confirm(ctx context.Context, unitID string) (KnowledgeUnit, error) {
	confirmURL, err := r.url("/confirm/" + url.PathEscape(unitID))
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
func (r *remoteClient) flag(ctx context.Context, unitID string, reason FlagReason, cfg flagConfig) (KnowledgeUnit, error) {
	body := map[string]string{"reason": string(reason)}
	if cfg.detail != "" {
		body["detail"] = cfg.detail
	}
	if cfg.duplicateOf != "" {
		body["duplicate_of"] = cfg.duplicateOf
	}

	flagURL, err := r.url("/flag/" + url.PathEscape(unitID))
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

	proposeURL, err := r.url("/propose")
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
		return KnowledgeUnit{}, fmt.Errorf("%w: decoding response: %w", errUnreachable, err)
	}

	return result, nil
}

// query fetches knowledge units from the remote API.
// Returns nil on transport or HTTP errors for graceful degradation.
func (r *remoteClient) query(ctx context.Context, params QueryParams) []KnowledgeUnit {
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

	if params.Limit > 0 {
		qv.Set("limit", fmt.Sprintf("%d", params.Limit))
	}

	base, err := r.url("/query")
	if err != nil {
		return nil
	}

	resp, err := r.do(ctx, http.MethodGet, base+"?"+qv.Encode(), nil)
	if err != nil {
		return nil
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		return nil
	}

	var units []KnowledgeUnit
	if err := json.NewDecoder(resp.Body).Decode(&units); err != nil {
		// Query degrades gracefully; log-worthy but not a hard error.
		return nil
	}

	return units
}

// url builds a full URL from the base URL and a path segment.
func (r *remoteClient) url(path string) (string, error) {
	return url.JoinPath(r.baseURL, path)
}
