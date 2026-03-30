package cmd

import (
	"fmt"

	"github.com/mark3labs/mcp-go/server"
	"github.com/spf13/cobra"

	"github.com/mozilla-ai/cq/cli/internal/version"
	"github.com/mozilla-ai/cq/cli/mcpserver"
	cq "github.com/mozilla-ai/cq/sdk/go"
)

// NewMCPCmd returns the mcp command.
func NewMCPCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "mcp",
		Short: "Start the MCP server on stdio.",
		Long: "Start cq as an MCP (Model Context Protocol) server on stdio. " +
			"Use this when integrating cq into IDE plugins or agent frameworks " +
			"that communicate via MCP.",
		RunE: func(_ *cobra.Command, _ []string) error {
			c, err := cq.NewClient()
			if err != nil {
				return err
			}
			defer func() { _ = c.Close() }()

			srv := mcpserver.New(c, version.Version())
			if err := server.ServeStdio(srv.MCPServer()); err != nil {
				return fmt.Errorf("mcp server error: %w", err)
			}

			return nil
		},
	}
}
