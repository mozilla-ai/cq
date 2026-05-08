package auth

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

const (
	// apiVersionPrefix is prepended to every platform path. The constant
	// keeps version routing in one place; if the platform later adds /v2,
	// the change lives here rather than scattered across method bodies.
	apiVersionPrefix = "/api/v1"

	// errorBodyByteLimit caps how much of an error response body mapError
	// will read. Defense-in-depth: a misbehaving or compromised platform
	// could otherwise stream gigabytes into our process when reporting an
	// error. 64 KiB is two orders of magnitude beyond any legitimate
	// error payload the platform produces.
	errorBodyByteLimit = 64 << 10
)

// Compile-time assertion that httpClient satisfies Client.
var _ Client = (*httpClient)(nil)

// httpClient is the HTTP-backed Client used in production. Tests
// substitute their own implementation of the Client interface.
type httpClient struct {
	baseURL string
	http    *http.Client
}

// ClaimUsername implements Client.
func (c *httpClient) ClaimUsername(ctx context.Context, jwt, username string) (User, error) {
	body := struct {
		Username string `json:"username"`
	}{Username: username}

	req, err := c.newRequest(ctx, http.MethodPost, apiVersionPrefix+"/users/me/username", body)
	if err != nil {
		return User{}, err
	}

	req.Header.Set("Authorization", "Bearer "+jwt)

	var resp User
	if err := c.send(req, &resp); err != nil {
		return User{}, err
	}

	return resp, nil
}

// CreateAPIKey implements Client.
func (c *httpClient) CreateAPIKey(ctx context.Context, jwt string, in CreateAPIKeyRequest) (CreatedAPIKey, error) {
	req, err := c.newRequest(ctx, http.MethodPost, apiVersionPrefix+"/users/me/api-keys", in)
	if err != nil {
		return CreatedAPIKey{}, err
	}

	req.Header.Set("Authorization", "Bearer "+jwt)

	var resp CreatedAPIKey
	if err := c.send(req, &resp); err != nil {
		return CreatedAPIKey{}, err
	}

	return resp, nil
}

// ListAPIKeys implements Client.
func (c *httpClient) ListAPIKeys(ctx context.Context, jwt string) ([]APIKey, error) {
	req, err := c.newRequest(ctx, http.MethodGet, apiVersionPrefix+"/users/me/api-keys", nil)
	if err != nil {
		return nil, err
	}

	req.Header.Set("Authorization", "Bearer "+jwt)

	var resp struct {
		Data  []APIKey `json:"data"`
		Count int      `json:"count"`
	}
	if err := c.send(req, &resp); err != nil {
		return nil, err
	}

	return resp.Data, nil
}

// Me implements Client.
func (c *httpClient) Me(ctx context.Context, jwt string) (User, error) {
	req, err := c.newRequest(ctx, http.MethodGet, apiVersionPrefix+"/users/me", nil)
	if err != nil {
		return User{}, err
	}

	req.Header.Set("Authorization", "Bearer "+jwt)

	var resp User
	if err := c.send(req, &resp); err != nil {
		return User{}, err
	}

	return resp, nil
}

// OAuthNativeExchange implements Client.
func (c *httpClient) OAuthNativeExchange(ctx context.Context, params NativeExchangeRequest) (string, error) {
	req, err := c.newRequest(ctx, http.MethodPost, apiVersionPrefix+"/oauth/native/exchange", params)
	if err != nil {
		return "", err
	}

	var resp struct {
		AccessToken string `json:"access_token"`
	}
	if err := c.send(req, &resp); err != nil {
		return "", err
	}

	return resp.AccessToken, nil
}

// OAuthNativeStart implements Client.
func (c *httpClient) OAuthNativeStart(ctx context.Context, params NativeStartRequest) (string, error) {
	req, err := c.newRequest(ctx, http.MethodPost, apiVersionPrefix+"/oauth/native/start", params)
	if err != nil {
		return "", err
	}

	var resp struct {
		AuthorizationURL string `json:"authorization_url"`
	}
	if err := c.send(req, &resp); err != nil {
		return "", err
	}

	return resp.AuthorizationURL, nil
}

// OAuthProviders implements Client.
func (c *httpClient) OAuthProviders(ctx context.Context) ([]Provider, error) {
	req, err := c.newRequest(ctx, http.MethodGet, apiVersionPrefix+"/oauth/providers", nil)
	if err != nil {
		return nil, err
	}

	var resp struct {
		Providers []Provider `json:"providers"`
	}
	if err := c.send(req, &resp); err != nil {
		return nil, err
	}

	// Normalise machine-readable Name on the way out so consumers can
	// rely on a canonical form for matching, regardless of how the
	// platform happens to capitalise or pad its responses. DisplayName
	// is left untouched because it's user-facing.
	for i := range resp.Providers {
		resp.Providers[i].Name = strings.ToLower(strings.TrimSpace(resp.Providers[i].Name))
	}

	return resp.Providers, nil
}

// RevokeAPIKey implements Client.
func (c *httpClient) RevokeAPIKey(ctx context.Context, jwt string, keyID string) error {
	path := apiVersionPrefix + "/users/me/api-keys/" + url.PathEscape(keyID) + "/revoke"

	req, err := c.newRequest(ctx, http.MethodPost, path, nil)
	if err != nil {
		return err
	}

	req.Header.Set("Authorization", "Bearer "+jwt)

	if err := c.send(req, nil); err != nil {
		// A 404 on the revoke route is the route-level "API key not
		// found" signal. mapError leaves status-code interpretation to
		// the caller because the same code can mean "user record gone"
		// on list/create; here, with a key ID in hand, we know exactly
		// what to surface.
		var status *PlatformStatusError
		if errors.As(err, &status) && status.StatusCode == http.StatusNotFound {
			return &APIKeyNotFoundError{KeyID: keyID}
		}

		return err
	}

	return nil
}

// newRequest builds a JSON request rooted at httpClient.baseURL. body
// is JSON-marshalled and the appropriate Content-Type header is set
// when non-nil. Authorization headers are not set here; callers add
// them on the returned request when the route requires authentication.
func (c *httpClient) newRequest(ctx context.Context, method, path string, body any) (*http.Request, error) {
	var bodyReader io.Reader

	if body != nil {
		raw, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("encoding request body: %w", err)
		}

		bodyReader = bytes.NewReader(raw)
	}

	req, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, bodyReader)
	if err != nil {
		return nil, fmt.Errorf("building request: %w", err)
	}

	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}

	return req, nil
}

// send executes req, decoding a 2xx response into out (when non-nil)
// or mapping a non-2xx response to a typed error.
func (c *httpClient) send(req *http.Request, out any) error {
	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("performing request: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		if out == nil {
			return nil
		}

		if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
			return fmt.Errorf("decoding response: %w", err)
		}

		return nil
	}

	return mapError(resp)
}

// mapError reads the error body of resp and returns the matching typed
// error, falling back to a generic error including the status code.
func mapError(resp *http.Response) error {
	if resp.StatusCode == http.StatusTooManyRequests {
		return &RateLimitedError{RetryAfter: parseRetryAfter(resp.Header.Get("Retry-After"))}
	}

	raw, err := io.ReadAll(io.LimitReader(resp.Body, errorBodyByteLimit))
	if err != nil {
		return fmt.Errorf("platform returned %d: reading error body: %w", resp.StatusCode, err)
	}

	var body struct {
		Error       string   `json:"error"`
		Detail      string   `json:"detail"`
		Suggestions []string `json:"suggestions"`
	}

	// json.Unmarshal failure on an error body is non-fatal: many
	// non-2xx responses legitimately carry no JSON (proxy HTML,
	// upstream plain-text). The fall-through below produces a
	// generic-but-honest error including the raw body.
	_ = json.Unmarshal(raw, &body)

	switch resp.StatusCode {
	case http.StatusBadRequest:
		if body.Detail == "invalid_grant" {
			return ErrInvalidGrant
		}

	case http.StatusUnauthorized:
		// The platform deliberately collapses missing-token,
		// malformed-token, and expired-token into one wire response.
		return ErrSessionExpired

	case http.StatusConflict:
		switch body.Error {
		case "username_unavailable":
			return &UsernameUnavailableError{Suggestions: body.Suggestions}

		case "username_already_set":
			return ErrUsernameAlreadySet
		}

		// API-key cap responses use FastAPI's default "detail" field
		// without the structured "error" discriminator the username
		// endpoints supply.
		if body.Detail != "" {
			return &APIKeyLimitReachedError{Detail: body.Detail}
		}

	case http.StatusUnprocessableEntity:
		if body.Error == "username_invalid_format" {
			return &UsernameFormatError{Detail: body.Detail}
		}

		// API-key validation failures (TTL grammar, name/labels length)
		// arrive as plain FastAPI 422s with "detail" set.
		if body.Detail != "" {
			return &APIKeyValidationError{Detail: body.Detail}
		}
	}

	// Unmapped status codes return PlatformStatusError so callers that
	// care about a particular code (for example, RevokeAPIKey wrapping a
	// 404 with the requested key ID) can match on the type rather than
	// the rendered message. The rendered message preserves the prior
	// fmt.Errorf format so existing log surfaces stay stable.
	return &PlatformStatusError{
		StatusCode: resp.StatusCode,
		Detail:     body.Detail,
		Errored:    body.Error,
		Body:       string(raw),
	}
}

// parseRetryAfter parses the Retry-After header's delta-seconds form.
// Returns zero when the header is absent or unparseable; HTTP-date form
// is intentionally not handled because the platform always emits seconds.
func parseRetryAfter(h string) time.Duration {
	if h == "" {
		return 0
	}

	secs, err := strconv.Atoi(h)
	if err != nil || secs < 0 {
		return 0
	}

	return time.Duration(secs) * time.Second
}
