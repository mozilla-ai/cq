package cmd

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/spf13/pflag"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

const (
	// envVarAddr is the environment variable for the remote API address.
	envVarAddr = "CQ_ADDR"

	// envVarAPIKey is the environment variable for the API key.
	envVarAPIKey = "CQ_API_KEY" // pragma: allowlist secret

	// envVarDBPath is the environment variable for the local database path.
	envVarDBPath = "CQ_LOCAL_DB_PATH"

	// envVarTimeout is the environment variable for the CLI operation timeout in seconds.
	envVarTimeout = "CQ_TIMEOUT"

	// defaultCLITimeout is the CLI operation timeout when CQ_TIMEOUT is not set.
	defaultCLITimeout = 30 * time.Second

	// jsonIndentSpaces is the number of spaces used for JSON indentation in CLI output.
	jsonIndentSpaces = 2
)

var (
	// flagAddr holds the resolved --addr persistent flag value.
	flagAddr string

	// flagAPIKey holds the resolved --api-key persistent flag value.
	flagAPIKey string

	// flagDBPath holds the resolved --db-path persistent flag value.
	flagDBPath string

	// jsonIndent is the indent string for JSON output.
	jsonIndent = strings.Repeat(" ", jsonIndentSpaces)
)

// InitFlags registers persistent flags that apply to all subcommands.
func InitFlags(fs *pflag.FlagSet) {
	fs.StringVar(&flagAddr, "addr", os.Getenv(envVarAddr), "Remote API address (env: "+envVarAddr+")")
	fs.StringVar(&flagAPIKey, "api-key", "", "API key for remote authentication (env: "+envVarAPIKey+")")
	fs.StringVar(&flagDBPath, "db-path", os.Getenv(envVarDBPath), "Local database path (env: "+envVarDBPath+")")
}


// cliTimeout returns the CLI operation timeout from CQ_TIMEOUT env var or the default.
func cliTimeout() time.Duration {
	if v := os.Getenv(envVarTimeout); v != "" {
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

// newCLIClient creates a new SDK client using the persistent flag values.
func newCLIClient() (*cq.Client, error) {
	var opts []cq.ClientOption
	if flagAddr != "" {
		opts = append(opts, cq.WithAddr(flagAddr))
	}

	apiKey := flagAPIKey // pragma: allowlist secret
	if apiKey == "" {
		apiKey = os.Getenv(envVarAPIKey)
	}

	if apiKey != "" {
		opts = append(opts, cq.WithAPIKey(apiKey))
	}

	if flagDBPath != "" {
		opts = append(opts, cq.WithLocalDBPath(flagDBPath))
	}

	c, err := cq.NewClient(opts...)
	if err != nil {
		return nil, fmt.Errorf("creating client: %w", err)
	}

	return c, nil
}
