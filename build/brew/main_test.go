package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestParseFilename(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name     string
		filename string
		wantOS   string
		wantArch string
	}{
		{
			name:     "darwin arm64 tar.gz",
			filename: "cq_Darwin_arm64.tar.gz",
			wantOS:   "Darwin",
			wantArch: "arm64",
		},
		{
			name:     "linux x86_64 tar.gz",
			filename: "cq_Linux_x86_64.tar.gz",
			wantOS:   "Linux",
			wantArch: "x86_64",
		},
		{
			name:     "windows x86_64 zip",
			filename: "cq_Windows_x86_64.zip",
			wantOS:   "Windows",
			wantArch: "x86_64",
		},
		{
			name:     "no prefix",
			filename: "checksums.txt",
			wantOS:   "",
			wantArch: "",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			gotOS, gotArch := parseFilename(tc.filename)
			if gotOS != tc.wantOS || gotArch != tc.wantArch {
				t.Errorf("parseFilename(%q) = (%q, %q), want (%q, %q)",
					tc.filename, gotOS, gotArch, tc.wantOS, tc.wantArch)
			}
		})
	}
}

func TestCaskDataArtifact(t *testing.T) {
	t.Parallel()

	data := caskData{
		Version: "0.1.0",
		artifacts: []artifact{
			{OS: "Darwin", Arch: "arm64", URL: "https://example.com/arm64", SHA256: "aaa"},
			{OS: "Linux", Arch: "x86_64", URL: "https://example.com/x86", SHA256: "bbb"},
		},
	}

	t.Run("found", func(t *testing.T) {
		t.Parallel()
		a := data.Artifact("Darwin", "arm64")
		if a == nil {
			t.Fatal("expected artifact, got nil")
		}
		if a.SHA256 != "aaa" {
			t.Errorf("got SHA256 %q, want %q", a.SHA256, "aaa")
		}
	})

	t.Run("not found", func(t *testing.T) {
		t.Parallel()
		a := data.Artifact("Windows", "x86_64")
		if a != nil {
			t.Errorf("expected nil, got %+v", a)
		}
	})
}

func TestCaskDataPlatforms(t *testing.T) {
	t.Parallel()

	data := caskData{
		artifacts: []artifact{
			{OS: "Linux", Arch: "arm64"},
			{OS: "Darwin", Arch: "arm64"},
		},
	}

	platforms := data.Platforms()
	if len(platforms) != 2 {
		t.Fatalf("got %d platforms, want 2", len(platforms))
	}
	// macOS should come first regardless of artifact order.
	if platforms[0].Key != "Darwin" {
		t.Errorf("first platform = %q, want Darwin", platforms[0].Key)
	}
	if platforms[1].Key != "Linux" {
		t.Errorf("second platform = %q, want Linux", platforms[1].Key)
	}
}

func TestCaskDataPlatformsExcludesWindows(t *testing.T) {
	t.Parallel()

	data := caskData{
		artifacts: []artifact{
			{OS: "Windows", Arch: "x86_64"},
			{OS: "Darwin", Arch: "arm64"},
		},
	}

	platforms := data.Platforms()
	if len(platforms) != 1 {
		t.Fatalf("got %d platforms, want 1", len(platforms))
	}
	if platforms[0].Key != "Darwin" {
		t.Errorf("platform = %q, want Darwin", platforms[0].Key)
	}
}

func TestRenderTemplate(t *testing.T) {
	t.Parallel()

	checksums := "aaaa cq_Darwin_arm64.tar.gz\nbbbb cq_Darwin_x86_64.tar.gz\ncccc cq_Linux_arm64.tar.gz\ndddd cq_Linux_x86_64.tar.gz\neeee cq_Windows_x86_64.zip\n"
	checksumFile := filepath.Join(t.TempDir(), "checksums.txt")
	if err := os.WriteFile(checksumFile, []byte(checksums), 0o644); err != nil {
		t.Fatal(err)
	}

	outputFile := filepath.Join(t.TempDir(), "cq.rb")

	err := run([]string{
		"-checksums", checksumFile,
		"-base-url", "https://github.com/mozilla-ai/cq/releases/download/cli/v0.1.0",
		"-version", "0.1.0",
		"-template", "cq.rb.tpl",
		"-output", outputFile,
	})
	if err != nil {
		t.Fatalf("run() error: %s", err)
	}

	got, err := os.ReadFile(outputFile)
	if err != nil {
		t.Fatal(err)
	}

	output := string(got)

	// Verify expected content is present.
	for _, want := range []string{
		`version "0.1.0"`,
		"on_macos do",
		"on_linux do",
		"on_intel do",
		"on_arm do",
		"sha256 \"aaaa\"",
		"sha256 \"bbbb\"",
		"cli/v0.1.0/cq_Darwin_arm64.tar.gz",
	} {
		if !strings.Contains(output, want) {
			t.Errorf("output missing %q", want)
		}
	}

	// Verify Windows is excluded.
	if strings.Contains(output, "Windows") {
		t.Error("output should not contain Windows")
	}
}
