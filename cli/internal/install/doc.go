// Package install installs cq into supported agent hosts by writing each
// host's skill and MCP configuration.
//
// NOTE: every file operation must be idempotent and must not overwrite
// user-modified files; re-running an install is always safe.
package install
