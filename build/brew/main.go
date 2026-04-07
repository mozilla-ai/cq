// Command brew renders the Homebrew cask template from a checksums file.
//
// It parses archive filenames matching cq_{OS}_{Arch}.{ext} and builds a
// lookup so the template can iterate over platforms without hardcoding them.
//
// Usage:
//
//	cd build/brew && go run . -checksums checksums.txt -base-url <url> -version <ver>
package main

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"strings"
	"text/template"
)

type artifact struct {
	OS     string
	Arch   string
	URL    string
	SHA256 string
}

// caskData is the template context.
type caskData struct {
	Version   string
	artifacts []artifact
}

// Platforms returns the OS-to-Homebrew-keyword mapping for OSes present in the
// artifacts. Homebrew uses "macos" for Darwin and "linux" for Linux. Order is
// stable: macOS first, then Linux.
func (d caskData) Platforms() []kv {
	order := []struct{ os, brew string }{
		{"Darwin", "macos"},
		{"Linux", "linux"},
	}
	var out []kv
	for _, o := range order {
		for _, a := range d.artifacts {
			if a.OS == o.os {
				out = append(out, kv{Key: o.os, Value: o.brew})
				break
			}
		}
	}
	return out
}

// Arches returns the Arch-to-Homebrew-keyword mapping. Homebrew uses "intel"
// for x86_64 and "arm" for arm64.
func (d caskData) Arches() []kv {
	order := []struct{ arch, brew string }{
		{"x86_64", "intel"},
		{"arm64", "arm"},
	}
	var out []kv
	for _, o := range order {
		for _, a := range d.artifacts {
			if a.Arch == o.arch {
				out = append(out, kv{Key: o.arch, Value: o.brew})
				break
			}
		}
	}
	return out
}

// Artifact looks up an artifact by OS and Arch. Returns nil if not found.
func (d caskData) Artifact(os, arch string) *artifact {
	for i := range d.artifacts {
		if d.artifacts[i].OS == os && d.artifacts[i].Arch == arch {
			return &d.artifacts[i]
		}
	}
	return nil
}

// kv is a key-value pair for ordered iteration in templates.
type kv struct {
	Key   string
	Value string
}

// parseFilename extracts OS and Arch from a filename like cq_Darwin_arm64.tar.gz.
func parseFilename(filename string) (string, string) {
	name := strings.TrimSuffix(filename, ".tar.gz")
	name = strings.TrimSuffix(name, ".zip")

	parts := strings.SplitN(name, "_", 3)
	if len(parts) != 3 || parts[0] != "cq" {
		return "", ""
	}
	return parts[1], parts[2]
}

func run(args []string) error {
	fs := flag.NewFlagSet("brew", flag.ContinueOnError)
	checksums := fs.String("checksums", "", "Path to checksums.txt file.")
	baseURL := fs.String("base-url", "", "Base download URL for release artifacts.")
	version := fs.String("version", "", "Release version (e.g. 0.1.0).")
	tplPath := fs.String("template", "cq.rb.tpl", "Path to cask template.")
	output := fs.String("output", "", "Output file (default: stdout).")
	if err := fs.Parse(args); err != nil {
		return err
	}

	if *checksums == "" || *baseURL == "" || *version == "" {
		return fmt.Errorf("required flags: -checksums, -base-url, -version")
	}

	f, err := os.Open(*checksums)
	if err != nil {
		return fmt.Errorf("opening checksums: %w", err)
	}
	defer f.Close()

	base := strings.TrimRight(*baseURL, "/")
	data := caskData{Version: *version}

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		parts := strings.Fields(scanner.Text())
		if len(parts) != 2 {
			continue
		}
		sha, filename := parts[0], parts[1]

		osName, arch := parseFilename(filename)
		if osName == "" {
			continue
		}

		data.artifacts = append(data.artifacts, artifact{
			OS:     osName,
			Arch:   arch,
			URL:    base + "/" + filename,
			SHA256: sha,
		})
	}
	if err := scanner.Err(); err != nil {
		return fmt.Errorf("reading checksums: %w", err)
	}

	tpl, err := template.ParseFiles(*tplPath)
	if err != nil {
		return fmt.Errorf("parsing template: %w", err)
	}

	out := os.Stdout
	if *output != "" {
		out, err = os.Create(*output)
		if err != nil {
			return fmt.Errorf("creating output: %w", err)
		}
		defer out.Close()
	}

	return tpl.Execute(out, data)
}

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintf(os.Stderr, "error: %s\n", err)
		os.Exit(1)
	}
}
