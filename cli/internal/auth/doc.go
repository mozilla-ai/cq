// Package auth implements the interactive sign-in flow used by
// "cq auth login", the local-state inspection used by "cq auth status",
// and the local-credential cleanup used by "cq auth logout".
//
// The package wires together five concerns:
//
//   - PKCE helpers (RFC 7636) for the verifier/challenge pair.
//   - A loopback HTTP listener (RFC 8252) that catches the browser
//     callback after the user authenticates with the OAuth provider.
//   - A platform HTTP client behind the Client interface so tests can
//     swap in a stub.
//   - An interactive onboarding loop for first-time users that need to
//     pick a username.
//   - Persistence of the resulting session state via a
//     credstore.Store.
//
// Long-lived API keys never enter this package: data-plane authentication
// stays on the agent side via the CQ_API_KEY environment variable.
package auth
