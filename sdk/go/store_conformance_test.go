package cq_test

import (
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"

	cq "github.com/mozilla-ai/cq/sdk/go"
	"github.com/mozilla-ai/cq/sdk/go/storetest"
)

func TestConformanceSQLite(t *testing.T) {
	t.Parallel()

	storetest.RunConformance(t, func() cq.Store {
		dbPath := filepath.Join(t.TempDir(), "conformance.db")
		s, err := cq.StoreFromURL("sqlite:///" + dbPath)
		require.NoError(t, err)

		return s
	})
}

func TestConformanceInMemory(t *testing.T) {
	t.Parallel()

	storetest.RunConformance(t, func() cq.Store {
		return cq.NewInMemoryStore()
	})
}
