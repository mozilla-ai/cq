# GitBook Documentation Branch

The `gitbook-docs` branch contains **generated** GitBook-compatible documentation,
automatically updated by GitHub Actions when a `docs/v*` tag is pushed.

**Do not edit this branch manually** — all changes will be overwritten.

## How it works

1. Push a `docs/v*` tag (e.g. `docs/v1.0.0`) to trigger a build
2. `scripts/prepare_gitbook_site.py --from-tags` extracts each component's
   docs from its latest release tag and assembles them into a site
3. The contents of `site/` are pushed to this branch
4. GitBook syncs from this branch

The workflow can also be triggered manually via `workflow_dispatch`.
