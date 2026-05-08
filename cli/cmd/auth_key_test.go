package cmd

import (
	"bytes"
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/spf13/cobra"
	"github.com/stretchr/testify/require"

	"github.com/mozilla-ai/cq/cli/internal/auth"
	"github.com/mozilla-ai/cq/cli/internal/credstore"
)

// signedInStore returns a memStore preloaded with a session JWT, the
// usual prerequisite for any `cq auth key` subcommand.
func signedInStore(t *testing.T) *memStore {
	t.Helper()

	s := &memStore{}
	require.NoError(t, s.Save(credstore.Credentials{SessionJWT: "test-jwt", Username: "alice"}))

	return s
}

// runKey runs the named `cq auth key` subcommand against the supplied
// client and store, returning the stdout, stderr, and error.
func runKey(t *testing.T, client auth.Client, store credstore.Store, args ...string) (string, string, error) {
	t.Helper()
	testSetup(t)
	setFlag(t, &flagAddr, "https://platform.example.com")

	cmd := NewAuthCmd(stubStore(store), stubClient(client))
	cmd.SetArgs(append([]string{"key"}, args...))

	var stdout, stderr bytes.Buffer
	cmd.SetOut(&stdout)
	cmd.SetErr(&stderr)

	err := cmd.ExecuteContext(context.Background())

	return stdout.String(), stderr.String(), err
}

// TestParseTTL pins the CLI-facing wrapper around the SDK parser. The
// SDK owns the grammar and coverage (see sdk/go/ttl); this test only
// confirms the wrapper reshapes typed SDK errors into --ttl-prefixed
// cobra messages with the user-supplied (un-normalised) value quoted
// back. Coverage is therefore deliberately narrow: one case per error
// class plus the canonicalisation paths.
func TestParseTTL(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name    string
		input   string
		want    string
		wantErr string
	}{
		{name: "lower-case canonical accepted", input: "30d", want: "30d"},
		{name: "upper-case canonicalised", input: "3D", want: "3d"},
		{name: "whitespace trimmed", input: "  90d  ", want: "90d"},
		{name: "max boundary accepted", input: "365d", want: "365d"},

		{name: "empty rejected", input: "", wantErr: "--ttl is required"},
		{name: "grammar error quotes original input", input: "1w", wantErr: `--ttl "1w" is not a valid duration`},
		{name: "negative rejected via grammar", input: "-1d", wantErr: `--ttl "-1d" is not a valid duration`},
		{name: "over-cap rejected with cap message", input: "366d", wantErr: `--ttl "366d" exceeds the maximum of 365d`},
		{name: "huge value rejected with cap message", input: "99999999999999999999d", wantErr: `--ttl "99999999999999999999d" exceeds the maximum of 365d`},
		{name: "zero rejected with positive message", input: "0d", wantErr: `--ttl "0d" must be greater than zero`},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			got, err := parseTTL(tc.input)
			if tc.wantErr != "" {
				require.Error(t, err)
				require.Contains(t, err.Error(), tc.wantErr)

				return
			}

			require.NoError(t, err)
			require.Equal(t, tc.want, got)
		})
	}
}

func TestNewAuthKeyCmd_RegistersExpectedSubcommands(t *testing.T) {
	cmd := NewAuthCmd()

	var keyCmd *cobra.Command
	for _, sub := range cmd.Commands() {
		if sub.Name() == "key" {
			keyCmd = sub
		}
	}

	require.NotNil(t, keyCmd, "expected `key` subcommand under `auth`")

	got := make(map[string]bool)
	for _, sub := range keyCmd.Commands() {
		got[sub.Name()] = true
	}

	require.True(t, got["create"], "expected create subcommand")
	require.True(t, got["list"], "expected list subcommand")
	require.True(t, got["revoke"], "expected revoke subcommand")
}

// --- cq auth key create -----------------------------------------------------

// TestAuthKeyCreate_HappyPath_StdoutTokenStderrBanner pins the exact
// terminal output a successful `cq auth key create` produces. Stdout
// carries only the plaintext token (one trailing newline) so a shell
// can capture it cleanly with command substitution. Stderr carries the
// human banner with the key's ID, prefix, labels, expiry, and the
// "shown only once" warning.
func TestAuthKeyCreate_HappyPath_StdoutTokenStderrBanner(t *testing.T) {
	expires := time.Date(2026, 8, 6, 12, 0, 0, 0, time.UTC)
	created := auth.CreatedAPIKey{
		APIKey: auth.APIKey{
			ID:        "00000000-0000-0000-0000-000000000001",
			Name:      "claude-cursor",
			Labels:    []string{"ci", "laptop"},
			Prefix:    "cqa12345",
			TTL:       "90d",
			ExpiresAt: expires,
			IsActive:  true,
		},
		Token: "cqa.v1.0123.secret",
	}

	var gotJWT string
	var gotReq auth.CreateAPIKeyRequest

	client := &stubAuthClient{
		createAPIKey: func(_ context.Context, jwt string, req auth.CreateAPIKeyRequest) (auth.CreatedAPIKey, error) {
			gotJWT = jwt
			gotReq = req

			return created, nil
		},
	}

	stdout, stderr, err := runKey(t, client, signedInStore(t),
		"create", "--name", "claude-cursor", "--ttl", "90d", "--labels", "ci,laptop",
	)
	require.NoError(t, err)
	require.Equal(t, "test-jwt", gotJWT)
	require.Equal(t, "claude-cursor", gotReq.Name)
	require.Equal(t, "90d", gotReq.TTL)
	require.Equal(t, []string{"ci", "laptop"}, gotReq.Labels)

	require.Equal(t, "cqa.v1.0123.secret\n", stdout)
	require.Equal(t,
		"Created API key 'claude-cursor' (id=00000000-0000-0000-0000-000000000001 prefix=cqa12345 labels=ci,laptop expires=2026-08-06T12:00:00Z).\n"+
			"The API key above is shown only once. Save it now (e.g. export CQ_API_KEY=...).\n",
		stderr,
	)
}

// TestAuthKeyCreate_NoLabels_BannerRendersDashSentinel pins the banner
// shape when no --labels are supplied: the labels= field renders as a
// literal "-" so the column does not collapse.
func TestAuthKeyCreate_NoLabels_BannerRendersDashSentinel(t *testing.T) {
	client := &stubAuthClient{
		createAPIKey: func(context.Context, string, auth.CreateAPIKeyRequest) (auth.CreatedAPIKey, error) {
			return auth.CreatedAPIKey{
				APIKey: auth.APIKey{
					ID:        "id-1",
					Name:      "no-label-key",
					Prefix:    "cqaPPPP",
					TTL:       "30d",
					ExpiresAt: time.Date(2026, 6, 7, 0, 0, 0, 0, time.UTC),
				},
				Token: "cqa.v1.token",
			}, nil
		},
	}

	stdout, stderr, err := runKey(t, client, signedInStore(t), "create", "--name", "no-label-key", "--ttl", "30d")
	require.NoError(t, err)
	require.Equal(t, "cqa.v1.token\n", stdout)
	require.Equal(t,
		"Created API key 'no-label-key' (id=id-1 prefix=cqaPPPP labels=- expires=2026-06-07T00:00:00Z).\n"+
			"The API key above is shown only once. Save it now (e.g. export CQ_API_KEY=...).\n",
		stderr,
	)
}

// TestAuthKeyCreate_RequiresTTL pins the missing-TTL shape: the user
// must spell out the lifetime themselves; there is no default. cobra's
// MarkFlagRequired runs before RunE and emits a single Error: line.
func TestAuthKeyCreate_RequiresTTL(t *testing.T) {
	client := &stubAuthClient{}

	_, stderr, err := runKey(t, client, signedInStore(t), "create", "--name", "k")
	require.EqualError(t, err, `required flag(s) "ttl" not set`)
	require.Equal(t, "Error: required flag(s) \"ttl\" not set\n", stderr)
}

// TestAuthKeyCreate_TTLAcceptedCaseInsensitively confirms that the CLI
// accepts mixed-case duration units on input and forwards the canonical
// lower-case form to the platform (the platform validator is
// case-sensitive today).
func TestAuthKeyCreate_TTLAcceptedCaseInsensitively(t *testing.T) {
	var gotTTL string

	client := &stubAuthClient{
		createAPIKey: func(_ context.Context, _ string, req auth.CreateAPIKeyRequest) (auth.CreatedAPIKey, error) {
			gotTTL = req.TTL

			return auth.CreatedAPIKey{Token: "x"}, nil
		},
	}

	_, _, err := runKey(t, client, signedInStore(t), "create", "--name", "k", "--ttl", "3D")
	require.NoError(t, err)
	require.Equal(t, "3d", gotTTL)
}

// TestAuthKeyCreate_TTLRejectsInvalidGrammar pins the parseability
// error message a user sees when the value does not match the
// platform's grammar. The CLI fails fast without a network round-trip.
func TestAuthKeyCreate_TTLRejectsInvalidGrammar(t *testing.T) {
	client := &stubAuthClient{}

	_, stderr, err := runKey(t, client, signedInStore(t), "create", "--name", "k", "--ttl", "1w")
	require.EqualError(t, err, `--ttl "1w" is not a valid duration: expected <integer><s|m|h|d>, e.g. 30d, 12h`)
	require.Equal(t, "Error: --ttl \"1w\" is not a valid duration: expected <integer><s|m|h|d>, e.g. 30d, 12h\n", stderr)
}

// TestAuthKeyCreate_RequiresName_EmitsCobraMissingFlagError asserts
// the missing-required-flag shape when only --name is missing: a
// single "Error:" line on stderr, no usage banner. cobra produces
// this verbatim from MarkFlagRequired before RunE runs.
func TestAuthKeyCreate_RequiresName_EmitsCobraMissingFlagError(t *testing.T) {
	client := &stubAuthClient{}

	_, stderr, err := runKey(t, client, signedInStore(t), "create", "--ttl", "30d")
	require.EqualError(t, err, `required flag(s) "name" not set`)
	require.Equal(t, "Error: required flag(s) \"name\" not set\n", stderr)
}

// TestAuthKeyCreate_NotSignedIn_HintsCqAuthLogin pins the user-visible
// stderr when the credstore has no entry. The error is operational
// (not a syntax problem) so cobra suppresses the usage banner; only
// the "Error: ..." line is shown.
func TestAuthKeyCreate_NotSignedIn_HintsCqAuthLogin(t *testing.T) {
	client := &stubAuthClient{}

	_, stderr, err := runKey(t, client, &memStore{}, "create", "--name", "k", "--ttl", "30d")
	require.EqualError(t, err, `not signed in. Run "cq auth login <provider>" first`)
	require.Equal(t, "Error: not signed in. Run \"cq auth login <provider>\" first\n", stderr)
}

// TestAuthKeyCreate_SessionExpired_PromptsToReLogin pins the stderr
// for the case where the credstore had a JWT but the platform refuses
// it (HTTP 401 from the platform's auth gate).
func TestAuthKeyCreate_SessionExpired_PromptsToReLogin(t *testing.T) {
	client := &stubAuthClient{
		createAPIKey: func(context.Context, string, auth.CreateAPIKeyRequest) (auth.CreatedAPIKey, error) {
			return auth.CreatedAPIKey{}, auth.ErrSessionExpired
		},
	}

	_, stderr, err := runKey(t, client, signedInStore(t), "create", "--name", "k", "--ttl", "30d")
	require.EqualError(t, err, `session expired or invalid. Run "cq auth login <provider>" to sign in again`)
	require.Equal(t, "Error: session expired or invalid. Run \"cq auth login <provider>\" to sign in again\n", stderr)
}

// TestAuthKeyCreate_LimitReached_SurfacesPlatformDetail pins the
// stderr for HTTP 409 from the platform when the active-key cap is
// hit. The platform's detail string is reproduced verbatim so the
// user sees the exact reason.
func TestAuthKeyCreate_LimitReached_SurfacesPlatformDetail(t *testing.T) {
	client := &stubAuthClient{
		createAPIKey: func(context.Context, string, auth.CreateAPIKeyRequest) (auth.CreatedAPIKey, error) {
			return auth.CreatedAPIKey{}, &auth.APIKeyLimitReachedError{Detail: "Maximum of 20 active API keys per user"}
		},
	}

	_, stderr, err := runKey(t, client, signedInStore(t), "create", "--name", "k", "--ttl", "30d")
	require.EqualError(t, err, "cannot create key: Maximum of 20 active API keys per user")
	require.Equal(t, "Error: cannot create key: Maximum of 20 active API keys per user\n", stderr)
}

// TestAuthKeyCreate_ValidationError_SurfacesDetail pins the stderr for
// a platform-side HTTP 422 (e.g. name too long, too many labels) on a
// request whose TTL passed client-side parseability. Same
// verbatim-detail contract as the cap-reached case.
func TestAuthKeyCreate_ValidationError_SurfacesDetail(t *testing.T) {
	client := &stubAuthClient{
		createAPIKey: func(context.Context, string, auth.CreateAPIKeyRequest) (auth.CreatedAPIKey, error) {
			return auth.CreatedAPIKey{}, &auth.APIKeyValidationError{Detail: "name exceeds maximum length"}
		},
	}

	_, stderr, err := runKey(t, client, signedInStore(t), "create", "--name", "k", "--ttl", "30d")
	require.EqualError(t, err, "invalid request: name exceeds maximum length")
	require.Equal(t, "Error: invalid request: name exceeds maximum length\n", stderr)
}

// --- cq auth key list -------------------------------------------------------

// TestAuthKeyList_PlainTextEmpty_StderrMessageStdoutEmpty pins the
// no-keys output. Stdout stays empty so `KEYS=$(cq auth key list)`
// returns "" cleanly; humans still see "No API keys." on stderr.
func TestAuthKeyList_PlainTextEmpty_StderrMessageStdoutEmpty(t *testing.T) {
	client := &stubAuthClient{
		listAPIKeys: func(context.Context, string) ([]auth.APIKey, error) {
			return nil, nil
		},
	}

	stdout, stderr, err := runKey(t, client, signedInStore(t), "list")
	require.NoError(t, err)
	require.Empty(t, stdout)
	require.Equal(t, "No API keys.\n", stderr)
}

// TestAuthKeyList_PlainTextRendersTabSeparatedRows pins the row format:
// id, prefix, status, expiry (RFC3339 UTC), name, labels (or "-"),
// tab-separated, one row per key. Status is one of {active, expired,
// revoked, inactive}; the example covers active and revoked.
func TestAuthKeyList_PlainTextRendersTabSeparatedRows(t *testing.T) {
	revoked := time.Date(2026, 5, 1, 0, 0, 0, 0, time.UTC)

	client := &stubAuthClient{
		listAPIKeys: func(context.Context, string) ([]auth.APIKey, error) {
			return []auth.APIKey{
				{
					ID:        "id-a",
					Name:      "alpha",
					Labels:    []string{"ci", "laptop"},
					Prefix:    "cqaAAAA",
					ExpiresAt: time.Date(2026, 8, 1, 0, 0, 0, 0, time.UTC),
					IsActive:  true,
				},
				{
					ID:        "id-b",
					Name:      "beta",
					Prefix:    "cqaBBBB",
					ExpiresAt: time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC),
					RevokedAt: &revoked,
				},
			}, nil
		},
	}

	stdout, stderr, err := runKey(t, client, signedInStore(t), "list")
	require.NoError(t, err)
	require.Empty(t, stderr)
	require.Equal(t,
		"id-a\tcqaAAAA\tactive\t2026-08-01T00:00:00Z\talpha\tci,laptop\n"+
			"id-b\tcqaBBBB\trevoked\t2026-06-01T00:00:00Z\tbeta\t-\n",
		stdout,
	)
}

// TestAuthKeyList_JSONRendersIndentedEnvelope pins the --json output:
// a `{data, count}` envelope, two-space indent, with a trailing
// newline from the encoder.
func TestAuthKeyList_JSONRendersIndentedEnvelope(t *testing.T) {
	client := &stubAuthClient{
		listAPIKeys: func(context.Context, string) ([]auth.APIKey, error) {
			return []auth.APIKey{
				{
					ID:        "id-a",
					Name:      "alpha",
					Labels:    []string{"ci"},
					Prefix:    "cqaAAAA",
					TTL:       "30d",
					ExpiresAt: time.Date(2026, 8, 1, 0, 0, 0, 0, time.UTC),
					CreatedAt: time.Date(2026, 7, 2, 0, 0, 0, 0, time.UTC),
					IsActive:  true,
				},
			}, nil
		},
	}

	stdout, stderr, err := runKey(t, client, signedInStore(t), "list", "--json")
	require.NoError(t, err)
	require.Empty(t, stderr)
	require.Equal(t,
		"{\n"+
			"  \"data\": [\n"+
			"    {\n"+
			"      \"id\": \"id-a\",\n"+
			"      \"name\": \"alpha\",\n"+
			"      \"labels\": [\n"+
			"        \"ci\"\n"+
			"      ],\n"+
			"      \"key_prefix\": \"cqaAAAA\",\n"+
			"      \"ttl\": \"30d\",\n"+
			"      \"expires_at\": \"2026-08-01T00:00:00Z\",\n"+
			"      \"created_at\": \"2026-07-02T00:00:00Z\",\n"+
			"      \"is_expired\": false,\n"+
			"      \"is_active\": true\n"+
			"    }\n"+
			"  ],\n"+
			"  \"count\": 1\n"+
			"}\n",
		stdout,
	)
}

// TestAuthKeyList_NotSignedIn_HintsCqAuthLogin pins the same operational
// "not signed in" UX for the list path.
func TestAuthKeyList_NotSignedIn_HintsCqAuthLogin(t *testing.T) {
	client := &stubAuthClient{}

	_, stderr, err := runKey(t, client, &memStore{}, "list")
	require.EqualError(t, err, `not signed in. Run "cq auth login <provider>" first`)
	require.Equal(t, "Error: not signed in. Run \"cq auth login <provider>\" first\n", stderr)
}

// TestAuthKeyList_SessionExpired_PromptsToReLogin pins the same
// operational "session expired" UX for the list path.
func TestAuthKeyList_SessionExpired_PromptsToReLogin(t *testing.T) {
	client := &stubAuthClient{
		listAPIKeys: func(context.Context, string) ([]auth.APIKey, error) {
			return nil, auth.ErrSessionExpired
		},
	}

	_, stderr, err := runKey(t, client, signedInStore(t), "list")
	require.EqualError(t, err, `session expired or invalid. Run "cq auth login <provider>" to sign in again`)
	require.Equal(t, "Error: session expired or invalid. Run \"cq auth login <provider>\" to sign in again\n", stderr)
}

// --- cq auth key revoke -----------------------------------------------------

// TestAuthKeyRevoke_HappyPath_ConfirmationOnStderrStdoutEmpty pins the
// success output: stdout is silent, stderr carries a one-line
// confirmation.
func TestAuthKeyRevoke_HappyPath_ConfirmationOnStderrStdoutEmpty(t *testing.T) {
	var gotKeyID string

	client := &stubAuthClient{
		revokeAPIKey: func(_ context.Context, _, keyID string) error {
			gotKeyID = keyID

			return nil
		},
	}

	stdout, stderr, err := runKey(t, client, signedInStore(t), "revoke", "abc-123")
	require.NoError(t, err)
	require.Equal(t, "abc-123", gotKeyID)
	require.Empty(t, stdout)
	require.Equal(t, "Revoked API key abc-123.\n", stderr)
}

// TestAuthKeyRevoke_RequiresKeyID asserts the missing-positional-arg
// shape from the Args validator: a single "Error:" line with the
// hint about `cq auth key list`. cobra does not print a usage banner
// for args-validator failures by default.
func TestAuthKeyRevoke_RequiresKeyID(t *testing.T) {
	client := &stubAuthClient{}

	_, stderr, err := runKey(t, client, signedInStore(t), "revoke")
	require.EqualError(t, err, `key ID required. Run "cq auth key list" to find one`)
	require.Equal(t, "Error: key ID required. Run \"cq auth key list\" to find one\n", stderr)
}

// TestAuthKeyRevoke_NotFound_EchoesKeyIDInError pins the per-key
// "not found" message: the user sees the exact key ID they asked for.
func TestAuthKeyRevoke_NotFound_EchoesKeyIDInError(t *testing.T) {
	client := &stubAuthClient{
		revokeAPIKey: func(context.Context, string, string) error {
			return &auth.APIKeyNotFoundError{KeyID: "missing"}
		},
	}

	_, stderr, err := runKey(t, client, signedInStore(t), "revoke", "missing")
	require.EqualError(t, err, "API key missing not found")
	require.Equal(t, "Error: API key missing not found\n", stderr)
}

// TestAuthKeyRevoke_SessionExpired_PromptsToReLogin pins the same
// operational "session expired" UX for the revoke path.
func TestAuthKeyRevoke_SessionExpired_PromptsToReLogin(t *testing.T) {
	client := &stubAuthClient{
		revokeAPIKey: func(context.Context, string, string) error {
			return auth.ErrSessionExpired
		},
	}

	_, stderr, err := runKey(t, client, signedInStore(t), "revoke", "any")
	require.EqualError(t, err, `session expired or invalid. Run "cq auth login <provider>" to sign in again`)
	require.Equal(t, "Error: session expired or invalid. Run \"cq auth login <provider>\" to sign in again\n", stderr)
}

// TestAuthKeyRevoke_PropagatesUnexpectedError preserves the existing
// "untyped errors pass through" contract. When a transport-level or
// otherwise unmapped error reaches the revoke command, its message is
// surfaced verbatim with cobra's "Error:" prefix.
func TestAuthKeyRevoke_PropagatesUnexpectedError(t *testing.T) {
	want := errors.New("upstream boom")
	client := &stubAuthClient{
		revokeAPIKey: func(context.Context, string, string) error { return want },
	}

	_, stderr, err := runKey(t, client, signedInStore(t), "revoke", "any")
	require.ErrorIs(t, err, want)
	require.True(t, strings.HasPrefix(stderr, "Error: upstream boom\n"))
}
