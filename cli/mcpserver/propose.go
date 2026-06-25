package mcpserver

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/mark3labs/mcp-go/mcp"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// ProposeTool returns the MCP tool definition for propose.
func ProposeTool() mcp.Tool {
	return mcp.NewTool(
		"propose",
		mcp.WithDescription(
			"Share a non-obvious insight so other agents avoid the same pitfall. "+
				"Call IMMEDIATELY after resolving a non-obvious error, discovering undocumented API behavior, "+
				"finding a version-specific incompatibility, or working around a known issue. "+
				"Do not batch to end-of-task. "+
				"Strip project-specific details; the insight must be generalizable.",
		),
		mcp.WithString(
			"summary",
			mcp.Required(),
			mcp.Description(
				"One-line description of the discovery (e.g. \"webpack 5 removes built-in Node.js polyfills\").",
			),
		),
		mcp.WithString(
			"detail",
			mcp.Required(),
			mcp.Description(
				"Fuller explanation with enough context to understand the issue. Include when you verified and against what version.",
			),
		),
		mcp.WithString(
			"action",
			mcp.Required(),
			mcp.Description(
				"Concrete instruction starting with an imperative verb (e.g. \"Use\", \"Set\", \"When X, do Y\"). Prefer principle and verification method over exact pinned values.",
			),
		),
		mcp.WithArray(
			"domains",
			mcp.Required(),
			mcp.Description(
				"Subject-area tags capturing what the insight is about (e.g. \"api\", \"payments\", \"connection-pooling\"). Do not repeat languages or frameworks here.",
			),
			mcp.WithStringItems(),
		),
		mcp.WithArray("languages",
			mcp.Description("Programming languages the insight applies to (e.g. \"python\", \"go\")."),
			mcp.WithStringItems(),
		),
		mcp.WithArray("frameworks",
			mcp.Description("Libraries or frameworks involved (e.g. \"webpack\", \"react\", \"fastapi\")."),
			mcp.WithStringItems(),
		),
		mcp.WithString(
			"pattern",
			mcp.Description(
				"Reusable cross-cutting concern (e.g. \"shell-quoting\", \"build-tooling\"). Omit if it just rephrases the summary.",
			),
		),
		mcp.WithObject(
			"extensions",
			mcp.Description(
				"Implementation-specific fields. Keys MUST use namespace:key format (e.g., myimpl:severity).",
			),
			func(schema map[string]any) { schema["additionalProperties"] = true },
		),
	)
}

// HandlePropose creates a knowledge unit.
func (s *Server) HandlePropose(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	summary, err := req.RequireString("summary")
	if err != nil {
		return mcp.NewToolResultError("summary is required"), nil
	}
	detail, err := req.RequireString("detail")
	if err != nil {
		return mcp.NewToolResultError("detail is required"), nil
	}
	action, err := req.RequireString("action")
	if err != nil {
		return mcp.NewToolResultError("action is required"), nil
	}
	domains, err := req.RequireStringSlice("domains")
	if err != nil {
		return mcp.NewToolResultError(fmt.Sprintf("invalid 'domains' argument: '%s'", err)), nil
	}
	if len(domains) == 0 {
		return mcp.NewToolResultError("domains must contain at least one tag"), nil
	}

	var extensions map[string]any
	if raw, ok := req.GetArguments()["extensions"]; ok {
		m, ok := raw.(map[string]any)
		if !ok {
			return mcp.NewToolResultError("extensions must be an object"), nil
		}
		extensions = m
	}

	if err := cq.ValidateExtensionKeys(extensions); err != nil {
		return mcp.NewToolResultError(err.Error()), nil
	}

	params := cq.ProposeParams{
		Summary:    summary,
		Detail:     detail,
		Action:     action,
		Domains:    domains,
		Languages:  req.GetStringSlice("languages", nil),
		Frameworks: req.GetStringSlice("frameworks", nil),
		Pattern:    req.GetString("pattern", ""),
		Extensions: extensions,
	}

	result, err := s.client.Propose(ctx, params)
	// Remote unreachable/rejected: unit was stored locally. Surface the unit
	// alongside a warning so the caller can summarise the partial success.
	var fb *cq.FallbackError
	if errors.As(err, &fb) {
		data, mErr := json.Marshal(fb.LocalUnit)
		if mErr != nil {
			return nil, fmt.Errorf("encoding result: %w", mErr)
		}

		return mcp.NewToolResultText(fmt.Sprintf("warning: %s\n%s", fb, data)), nil
	}
	if err != nil {
		return nil, fmt.Errorf("proposing: %w", err)
	}

	data, err := json.Marshal(result)
	if err != nil {
		return nil, fmt.Errorf("encoding result: %w", err)
	}

	return mcp.NewToolResultText(string(data)), nil
}
