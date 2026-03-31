package cmd

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"time"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// defaultCLITimeout is the CLI operation timeout when CQ_TIMEOUT is not set.
const defaultCLITimeout = 30 * time.Second

// cliTimeout returns the CLI operation timeout from CQ_TIMEOUT env var or the default.
func cliTimeout() time.Duration {
	if v := os.Getenv("CQ_TIMEOUT"); v != "" {
		if d, err := strconv.Atoi(v); err == nil && d > 0 {
			return time.Duration(d) * time.Second
		}
	}

	return defaultCLITimeout
}

// cliContext returns a context with the CLI timeout applied.
func cliContext() (context.Context, context.CancelFunc) {
	return context.WithTimeout(context.Background(), cliTimeout())
}

// newCLIClient creates a new SDK client for CLI use.
func newCLIClient() (*cq.Client, error) {
	c, err := cq.NewClient()
	if err != nil {
		return nil, fmt.Errorf("creating client: %w", err)
	}

	return c, nil
}
