// Package cq provides a Go SDK for the cq shared agent knowledge commons.
//
// Create a client to query, propose, confirm, and flag knowledge units:
//
//	c, err := cq.NewClient()
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer c.Close()
//
//	result, err := c.Query(ctx, cq.QueryParams{
//	    Domains: []string{"api", "stripe"},
//	})
//
// The client reads CQ_TEAM_ADDR, CQ_API_KEY, and CQ_LOCAL_DB_PATH from the
// environment. Use WithAddr, WithAPIKey, and WithLocalDBPath to override.
// If no remote address is configured, the client operates in local-only mode.
package cq
