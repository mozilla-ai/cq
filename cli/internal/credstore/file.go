package credstore

import (
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
)

const (
	// credentialsDirMode is the POSIX mode used when creating the storage
	// directory. Has no effect on Windows, which relies on the inherited
	// per-user ACL.
	credentialsDirMode os.FileMode = 0o700

	// credentialsFileMode is the POSIX mode applied to the credentials
	// file. Same Windows caveat as credentialsDirMode.
	credentialsFileMode os.FileMode = 0o600

	// credentialsFilename is the name of the JSON file written under the
	// configured directory.
	credentialsFilename = "credentials"

	// jsonIndentSpaces is the number of spaces used per indent level when
	// serialising the on-disk credentials JSON.
	jsonIndentSpaces = 2
)

// jsonIndent is the indent string used by encoding/json when writing the
// credentials file. Derived from jsonIndentSpaces so the count and string
// can never drift apart.
var jsonIndent = strings.Repeat(" ", jsonIndentSpaces)

// Compile-time assertion that *fileStore satisfies Store.
var _ Store = (*fileStore)(nil)

// fileStore persists Credentials as a JSON file inside dir.
//
// On POSIX systems the file is written with mode 0600 and the directory is
// created with mode 0700 so the credentials are readable only by the
// owning user. Windows applies its inherited per-user ACL instead; the
// permission bits passed to the standard library are advisory there.
//
// fileStore is the fallback used when the OS keyring is unreachable
// (typically headless Linux without D-Bus). It is not as resistant to
// same-user processes as the keyring backend; see package documentation.
type fileStore struct {
	dir string
}

// newFileStore returns a fileStore writing to dir. The directory is not
// created until Save is called. dir must be non-empty.
func newFileStore(dir string) (*fileStore, error) {
	if dir == "" {
		return nil, errors.New("credstore: file store directory must not be empty")
	}

	return &fileStore{dir: dir}, nil
}

// Delete removes the stored credentials file. Returns nil if it does not exist.
func (s *fileStore) Delete() error {
	err := os.Remove(s.path())
	if err != nil && !errors.Is(err, fs.ErrNotExist) {
		return fmt.Errorf("removing credentials file: %w", err)
	}

	return nil
}

// Load reads and decodes the stored credentials, or returns ErrNotFound if
// the file does not exist.
func (s *fileStore) Load() (Credentials, error) {
	raw, err := os.ReadFile(s.path())
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return Credentials{}, ErrNotFound
		}

		return Credentials{}, fmt.Errorf("reading credentials file: %w", err)
	}

	var creds Credentials
	if err := json.Unmarshal(raw, &creds); err != nil {
		return Credentials{}, fmt.Errorf("decoding credentials file: %w", err)
	}

	return creds, nil
}

// Save writes creds atomically as JSON, ensuring the directory exists with
// credentialsDirMode and the file is written with credentialsFileMode.
func (s *fileStore) Save(creds Credentials) error {
	if err := os.MkdirAll(s.dir, credentialsDirMode); err != nil {
		return fmt.Errorf("creating credentials directory: %w", err)
	}

	body, err := json.MarshalIndent(creds, "", jsonIndent)
	if err != nil {
		return fmt.Errorf("encoding credentials: %w", err)
	}

	if err := s.writeAtomic(body); err != nil {
		return fmt.Errorf("writing credentials file: %w", err)
	}

	return nil
}

// path returns the full path to the credentials file.
func (s *fileStore) path() string {
	return filepath.Join(s.dir, credentialsFilename)
}

// writeAtomic writes data to a temporary file in the same directory and
// renames it over the credentials file. The temporary file is created with
// credentialsFileMode so the final file never exists at broader permissions,
// even transiently. On any error the temporary file is removed.
func (s *fileStore) writeAtomic(data []byte) (rerr error) {
	final := s.path()

	tmp, err := os.CreateTemp(filepath.Dir(final), filepath.Base(final)+".tmp-*")
	if err != nil {
		return err
	}

	tmpName := tmp.Name()

	defer func() {
		if rerr != nil {
			_ = os.Remove(tmpName)
		}
	}()

	if err := tmp.Chmod(credentialsFileMode); err != nil {
		_ = tmp.Close()

		return err
	}

	if _, err := tmp.Write(data); err != nil {
		_ = tmp.Close()

		return err
	}

	if err := tmp.Close(); err != nil {
		return err
	}

	return os.Rename(tmpName, final)
}
