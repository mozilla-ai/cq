package cmd

import (
	"context"
	"fmt"
	"time"

	"github.com/mark3labs/mcp-go/server"
	"github.com/spf13/cobra"

	"github.com/mozilla-ai/cq/cli/internal/version"
	"github.com/mozilla-ai/cq/cli/mcpserver"
)

// drainTimeout bounds the background drain of local to remote KUs at MCP server startup.
const drainTimeout = 30 * time.Second

// NewMCPCmd returns the mcp command.
func NewMCPCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "mcp",
		Short: "Start the MCP server on stdio.",
		Long: "Start cq as an MCP (Model Context Protocol) server on stdio. " +
			"Use this when integrating cq into IDE plugins or agent frameworks " +
			"that communicate via MCP.",
		RunE: func(_ *cobra.Command, _ []string) error {
			c, err := newCLIClient()
			if err != nil {
				return err
			}
			defer func() { _ = c.Close() }()

			if c.HasRemote() {
				go func() {
					ctx, cancel := context.WithTimeout(context.Background(), drainTimeout)
					defer cancel()
					_, _ = c.Drain(ctx)
				}()
			}

			srv := mcpserver.New(c, version.Version())
			if err := server.ServeStdio(srv.MCPServer()); err != nil {
				return fmt.Errorf("mcp server error: %w", err)
			}

			return nil
		},
	}
}
