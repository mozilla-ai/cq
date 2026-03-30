// Package mcpserver exposes cq operations as MCP tool handlers over stdio.
package mcpserver

import (
	"context"

	"github.com/mark3labs/mcp-go/server"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// Client is the cq client this server delegates to.
type Client interface {
	Confirm(ctx context.Context, ku cq.KnowledgeUnit) (cq.KnowledgeUnit, error)
	Drain(ctx context.Context) (cq.DrainResult, error)
	Flag(ctx context.Context, ku cq.KnowledgeUnit, reason cq.FlagReason, opts ...cq.FlagOption) (cq.KnowledgeUnit, error)
	Prompt() string
	Propose(ctx context.Context, params cq.ProposeParams) (cq.KnowledgeUnit, error)
	Query(ctx context.Context, params cq.QueryParams) (cq.QueryResult, error)
	Status(ctx context.Context) (cq.StoreStats, error)
}

// Server wraps a Client and exposes MCP tool handlers.
type Server struct {
	client Client
	mcpSrv *server.MCPServer
}

// New creates an MCP tool server backed by the given client.
func New(client Client, ver string) *Server {
	srv := &Server{client: client}

	srv.mcpSrv = server.NewMCPServer(
		"cq",
		ver,
		server.WithToolCapabilities(false),
		server.WithRecovery(),
	)

	srv.mcpSrv.AddTool(QueryTool(), srv.HandleQuery)
	srv.mcpSrv.AddTool(ProposeTool(), srv.HandlePropose)
	srv.mcpSrv.AddTool(ConfirmTool(), srv.HandleConfirm)
	srv.mcpSrv.AddTool(FlagTool(), srv.HandleFlag)
	srv.mcpSrv.AddTool(StatusTool(), srv.HandleStatus)

	return srv
}

// MCPServer returns the underlying mcp-go server for stdio transport.
func (s *Server) MCPServer() *server.MCPServer {
	return s.mcpSrv
}
