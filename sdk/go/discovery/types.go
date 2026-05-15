// Package discovery resolves a user-supplied cq node address into the
// concrete API base URL and protocol version that client code should use.
// It implements the protocol described in docs/node-discovery-protocol.md.
package discovery

import "time"

// Protocol constants for the node discovery handshake.
// These are applied when a node does not publish a discovery
// document and define the well-known location and supported version
// that the client expects to see when one is published.
const (
	// DefaultAPIPath is the API base path assumed when a node does
	// not publish a discovery document.
	// It is appended to the user-supplied address to form the
	// effective API base URL.
	DefaultAPIPath = "/api/v1"

	// DefaultAPIVersion is the protocol version assumed when a node
	// does not publish a discovery document.
	DefaultAPIVersion = "v1"

	// WellKnownPath is the URL path at which a node publishes its
	// discovery document, relative to the user-supplied address.
	WellKnownPath = "/.well-known/cq-node.json"

	// SupportedAPIVersion is the protocol version this client speaks.
	// A node advertising any other version is rejected with a clear error.
	SupportedAPIVersion = "v1"

	// SupportedDiscoveryVersion is the discovery-document schema
	// version this client understands.
	// A document declaring any other value is rejected with a clear
	// error so a future incompatible schema cannot be silently parsed
	// with this client's assumptions.
	SupportedDiscoveryVersion = 1

	// DefaultCacheTTL is how long a successful discovery result is
	// considered fresh on disk before re-probing.
	DefaultCacheTTL = 24 * time.Hour
)

// NodeInfo is the resolved view of a node after running discovery.
// All fields are populated either from the discovery document or
// from defaults, so callers never see an empty APIBaseURL or
// APIVersion on a successful resolve.
//
// NOTE: callers should treat APIBaseURL as the complete URL to
// append resource paths to — there is no implicit version prefix to
// add on top.
type NodeInfo struct {
	// Version is the discovery-document schema version.
	// It matches SupportedDiscoveryVersion on every successful resolve.
	Version int `json:"version"`

	// APIBaseURL is the fully-qualified URL that resource paths are
	// joined onto, including any version segment the node advertises.
	APIBaseURL string `json:"api_base_url"`

	// APIVersion is the protocol version the node speaks.
	// It matches SupportedAPIVersion on every successful resolve.
	APIVersion string `json:"api_version"`

	// NodeName is the optional human-readable label a node may
	// publish for display in user-facing output.
	// Empty when the node does not publish one.
	NodeName string `json:"node_name,omitempty"`
}
