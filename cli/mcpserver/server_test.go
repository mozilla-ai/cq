package mcpserver

import (
	"context"
	"errors"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

var errMockNotImplemented = errors.New("mock method not implemented")

type mockClient struct {
	confirmFn func(ctx context.Context, ku cq.KnowledgeUnit) (cq.KnowledgeUnit, error)
	drainFn   func(ctx context.Context) (cq.DrainResult, error)
	flagFn    func(ctx context.Context, ku cq.KnowledgeUnit, reason cq.FlagReason, opts ...cq.FlagOption) (cq.KnowledgeUnit, error)
	promptFn  func() string
	proposeFn func(ctx context.Context, params cq.ProposeParams) (cq.KnowledgeUnit, error)
	queryFn   func(ctx context.Context, params cq.QueryParams) (cq.QueryResult, error)
	statusFn  func(ctx context.Context) (cq.StoreStats, error)
}

func (m *mockClient) Confirm(ctx context.Context, ku cq.KnowledgeUnit) (cq.KnowledgeUnit, error) {
	if m.confirmFn == nil {
		return cq.KnowledgeUnit{}, errMockNotImplemented
	}

	return m.confirmFn(ctx, ku)
}

func (m *mockClient) Drain(ctx context.Context) (cq.DrainResult, error) {
	if m.drainFn == nil {
		return cq.DrainResult{}, errMockNotImplemented
	}

	return m.drainFn(ctx)
}

func (m *mockClient) Flag(
	ctx context.Context,
	ku cq.KnowledgeUnit,
	reason cq.FlagReason,
	opts ...cq.FlagOption,
) (cq.KnowledgeUnit, error) {
	if m.flagFn == nil {
		return cq.KnowledgeUnit{}, errMockNotImplemented
	}

	return m.flagFn(ctx, ku, reason, opts...)
}

func (m *mockClient) Prompt() string {
	if m.promptFn == nil {
		return ""
	}

	return m.promptFn()
}

func (m *mockClient) Propose(ctx context.Context, params cq.ProposeParams) (cq.KnowledgeUnit, error) {
	if m.proposeFn == nil {
		return cq.KnowledgeUnit{}, errMockNotImplemented
	}

	return m.proposeFn(ctx, params)
}

func (m *mockClient) Query(ctx context.Context, params cq.QueryParams) (cq.QueryResult, error) {
	if m.queryFn == nil {
		return cq.QueryResult{}, errMockNotImplemented
	}

	return m.queryFn(ctx, params)
}

func (m *mockClient) Status(ctx context.Context) (cq.StoreStats, error) {
	if m.statusFn == nil {
		return cq.StoreStats{}, errMockNotImplemented
	}

	return m.statusFn(ctx)
}
