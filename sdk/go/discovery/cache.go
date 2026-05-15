package discovery

import (
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"time"
)

// cache stores discovery results on disk, keyed by SHA-256 of the
// user-supplied address.
// Entries expire by file mtime plus the configured time-to-live (TTL).
//
// The on-disk format is one JSON file per address.
// Writes are atomic via temp-file plus rename so a crashed process
// never leaves a half-written entry visible to the next invocation.
//
// NOTE: instances are not safe for concurrent use across processes;
// concurrent writers to the same address race on the final rename,
// and the last writer wins.
type cache struct {
	dir string
	ttl time.Duration
}

// newCache returns a cache rooted at dir with the given freshness TTL.
// The directory is created lazily on the first successful put so that
// constructing a cache for a never-used address is free.
func newCache(dir string, ttl time.Duration) *cache {
	return &cache{dir: dir, ttl: ttl}
}

// get returns the cached NodeInfo for addr and true when a fresh,
// valid entry exists, or the zero NodeInfo and false otherwise.
// An entry is fresh when its file mtime is within the configured TTL.
// Unreadable, expired, or schema-invalid entries are reported as a
// miss; invalid entries are also removed from disk so the next read
// is a clean miss rather than a repeated rejection.
func (c *cache) get(addr string) (NodeInfo, bool) {
	p := c.pathFor(addr)
	stat, err := os.Stat(p)
	if err != nil {
		return NodeInfo{}, false
	}
	if time.Since(stat.ModTime()) > c.ttl {
		return NodeInfo{}, false
	}
	raw, err := os.ReadFile(p)
	if err != nil {
		return NodeInfo{}, false
	}
	ni, err := decodeNodeInfo(raw)
	if err != nil {
		_ = os.Remove(p)
		return NodeInfo{}, false
	}
	if err := validate(ni); err != nil {
		_ = os.Remove(p)
		return NodeInfo{}, false
	}
	return ni, true
}

// invalidate removes the cache entry for addr if one exists.
// A missing entry is not an error.
func (c *cache) invalidate(addr string) error {
	err := os.Remove(c.pathFor(addr))
	if err != nil && !errors.Is(err, fs.ErrNotExist) {
		return fmt.Errorf("invalidate cache entry: %w", err)
	}
	return nil
}

// pathFor returns the on-disk path of the cache entry for addr.
// The filename is the lowercase hex SHA-256 of the address so that
// arbitrary URL characters never appear on disk.
func (c *cache) pathFor(addr string) string {
	hash := sha256.Sum256([]byte(addr))
	return filepath.Join(c.dir, fmt.Sprintf("%x.json", hash))
}

// put writes info to disk as the cache entry for addr.
// The write is atomic: data is first written to a temp file in the
// cache directory and then renamed into place, so a partial write
// from a crashed process is never observable on the next read.
// The cache directory is created if it does not already exist.
func (c *cache) put(addr string, info NodeInfo) error {
	if err := os.MkdirAll(c.dir, 0o755); err != nil {
		return fmt.Errorf("create cache dir: %w", err)
	}
	tmp, err := os.CreateTemp(c.dir, "tmp-*.json")
	if err != nil {
		return fmt.Errorf("create temp cache file: %w", err)
	}
	tmpPath := tmp.Name()
	defer func() { _ = os.Remove(tmpPath) }()

	if err := json.NewEncoder(tmp).Encode(info); err != nil {
		_ = tmp.Close()
		return fmt.Errorf("encode cache entry: %w", err)
	}
	if err := tmp.Close(); err != nil {
		return fmt.Errorf("close temp cache file: %w", err)
	}
	if err := os.Rename(tmpPath, c.pathFor(addr)); err != nil {
		return fmt.Errorf("install cache entry: %w", err)
	}
	return nil
}
