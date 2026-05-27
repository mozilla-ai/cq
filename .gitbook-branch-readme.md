# GitBook Documentation Branch

The `gitbook-docs` branch contains **generated** GitBook-compatible documentation,
automatically updated by GitHub Actions on every push to `main`.

**Do not edit this branch manually** — all changes will be overwritten.

## How it works

1. `scripts/prepare_gitbook_site.py` copies `docs/` into `site/`, maps root
   files (`README.md`, `CONTRIBUTING.md`, `DEVELOPMENT.md`) into the site, and
   expands any `{{#include ...}}` markers
2. The contents of `site/` are pushed to this branch
3. GitBook syncs from this branch
