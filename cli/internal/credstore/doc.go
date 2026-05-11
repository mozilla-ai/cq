// Package credstore stores cq session credentials (the OIDC session JWT and
// the cached identity that goes with it) on the user's machine.
//
// The package never stores long-lived API keys: those belong on the agent side
// via the CQ_API_KEY environment variable. credstore deals only with the
// short-lived session state created by an interactive "cq auth login".
package credstore
