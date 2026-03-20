# Contributing to cq

Thank you for your interest in contributing to cq. This guide explains how to get involved.

## Types of Contribution

There are two distinct types of contribution to this project, each with its own governance:

- **Code contributions** to the cq software (source code, tests, documentation, tooling). These are governed by the [Apache 2.0 license](LICENSE) and the standard open-source practices described in this file.
- **Knowledge unit contributions** to the shared commons (structured agent learnings submitted through cq itself). These are governed by the [Contributor Agreement](CONTRIBUTOR_AGREEMENT.md), which covers licensing, provenance, and quality expectations specific to knowledge contributions.

If you are contributing code, this file is all you need. If you are contributing knowledge units, please read the Contributor Agreement.

## Before You Start

- **Search for duplicates.** Check [existing issues](https://github.com/mozilla-ai/cq/issues) and [open pull requests](https://github.com/mozilla-ai/cq/pulls) before starting work.
- **Discuss major changes first.** Open an issue before starting work on: new features, API changes, architectural changes, breaking changes, or new dependencies. This avoids wasted effort and helps maintainers provide early guidance.
- **Set up your development environment.** See [DEVELOPMENT.md](DEVELOPMENT.md) for prerequisites, installation, and how to run tests and linters.

## Making Changes

### Branch Naming

Use descriptive branch names with one of these prefixes:

| Prefix | Use case |
|--------|----------|
| `feature/` | New features |
| `fix/` | Bug fixes |
| `refactor/` | Code improvements |
| `docs/` | Documentation changes |
| `chore/` | Maintenance tasks |

### Tests and Commits

- Write tests for every change. Bug fixes should include a test that reproduces the issue.
- Write clear commit messages that explain *why* the change was made, not just *what* changed.
- Keep commits atomic; each commit should represent one logical change.

## Submitting Your Contribution

1. Fork the repository and clone your fork.
2. Add the upstream remote: `git remote add upstream https://github.com/mozilla-ai/cq.git`
3. Create a branch from `main` following the naming conventions above.
4. Make your changes, including tests.
5. Push your branch to your fork and open a pull request against `main`.

Your PR description should include:

- What changed and why.
- How to test the change.
- Links to related issues (use `Fixes #123` or `Closes #456` to auto-close them).

## Review Process

- Expect an initial response within 5 business days.
- Simple fixes typically take around 1 week to merge; complex features may take 2-3 weeks.
- Address review comments with new commits rather than force-pushing during review. This makes it easier for reviewers to see incremental changes.
- Pull requests with no activity for 30 or more days may be closed. You are welcome to reopen or re-submit if you return to the work.

## Your First Contribution

- Look for issues labeled [`good-first-issue`](https://github.com/mozilla-ai/cq/labels/good-first-issue) or [`help-wanted`](https://github.com/mozilla-ai/cq/labels/help-wanted).
- Comment on the issue to claim it so others know you are working on it.
- Ask questions early; maintainers are happy to help.
- Start small. A well-scoped first PR is easier to review and merge.

## Code of Conduct

This project follows Mozilla's [Community Participation Guidelines](https://www.mozilla.org/about/governance/policies/participation/). Please treat all participants with respect.

## Security

If you discover a security vulnerability, do **not** open a public issue. See [SECURITY.md](SECURITY.md) for responsible disclosure instructions.

## License

By contributing code to this project, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE), the same license that covers the project.
