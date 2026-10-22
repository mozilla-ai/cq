# Release credentials

Every credential that publishes a cq artifact is a **deployment environment** secret, never a repository or organization secret.

GitHub hands a repository or organization secret to a workflow running on **any** ref, and any user with write access can read every one of them. A `workflow_dispatch` run executes the workflow file from the ref it was dispatched on, so a branch that edits a publishing workflow can publish without ever touching `main`. An environment's deployment policy limits a credential to the refs that policy names, and its secrets stay unreadable until the policy and any required reviewers are satisfied.

## Environments

| Environment | Workflow | Credentials | Allowed refs |
| --- | --- | --- | --- |
| `docker-hub` | `release-server-image.yaml` | none: Docker Hub OIDC | tag `server/v*` |
| `homebrew-tap` | `release-cli.yaml` | `TAP_APP_PRIVATE_KEY`, variable `TAP_APP_CLIENT_ID` | tag `cli/v*` |
| `pypi` | `release-schema.yaml`, `release-sdk-python.yaml` | none: PyPI trusted publishing | tags `schema/*`, `sdk/python/*` |

That leaves one stored credential in the whole release path, `TAP_APP_PRIVATE_KEY`. Docker Hub and PyPI both trust the run's OIDC token instead of a secret, and `DOCKERHUB_OIDC_CONNECTIONID` and `TAP_APP_CLIENT_ID` are identifiers rather than credentials.

Each release workflow also asserts that the tag it builds is the tag the run is on. The deployment policy gates the run's ref, so a job that checked out some other ref would satisfy the policy and then build unreviewed code with the credential.

The checkout steps name `refs/tags/<tag>` rather than the bare tag. An unqualified ref is ambiguous when a branch shares the tag's name, and the tools disagree about which one wins: `actions/checkout` and `git checkout` take the branch, while `git rev-parse` takes the tag. Each warns that the name is ambiguous and then exits 0, so the only signal is a warning on a green run. Qualifying the ref removes the question rather than relying on any one precedence.

## Setup

These are repository and provider settings. They are not part of any diff, and the Docker Hub and Homebrew steps must be in place **before** the workflows that depend on them run.

Do step 3 first. A workflow that names an environment which does not exist creates it on the first run with no protection rules and no secrets, so merging ahead of step 3 produces two unprotected environments rather than an error.

### 1. Docker Hub OIDC connection

Docker Hub issues a short-lived token in exchange for the run's GitHub OIDC token, so no Docker credential is stored and there is nothing to rotate.

1. In Docker Home for the `mzdotai` organization, open **Identity & auth > OIDC connections** and create a connection.
2. Set the subject claim to `repo:mozilla-ai/cq:environment:docker-hub`. Only a job running in that environment can then log in.
3. Copy the connection ID and set it as the `docker-hub` environment **variable** `DOCKERHUB_OIDC_CONNECTIONID`. It is an identifier, not a secret. The action rejects anything that is not a UUID.

Only organization accounts can sign in with OIDC, which is why the workflow's `username` is the organization name rather than a user.

### 2. Homebrew tap App

1. Create a GitHub App in the `mozilla-ai` organization with the single repository permission **Contents: read and write**.
2. Install it on `mozilla-ai/cq` and `mozilla-ai/homebrew-tap`, and on no other repository.
3. Set its client ID as the `homebrew-tap` environment variable `TAP_APP_CLIENT_ID`, and a freshly generated private key as the environment secret `TAP_APP_PRIVATE_KEY`.

The workflow narrows the token it mints to the tap's contents, and the token expires within the hour. If the private key leaks, it reaches two repositories rather than the whole organization.

### 3. Deployment policies

```bash
for env in docker-hub homebrew-tap pypi; do
  gh api -X PUT "repos/mozilla-ai/cq/environments/${env}" \
    -F 'deployment_branch_policy[protected_branches]=false' \
    -F 'deployment_branch_policy[custom_branch_policies]=true'
done

gh api -X POST repos/mozilla-ai/cq/environments/docker-hub/deployment-branch-policies \
  -f 'name=server/v*' -f 'type=tag'
gh api -X POST repos/mozilla-ai/cq/environments/homebrew-tap/deployment-branch-policies \
  -f 'name=cli/v*' -f 'type=tag'
gh api -X POST repos/mozilla-ai/cq/environments/pypi/deployment-branch-policies \
  -f 'name=schema/*' -f 'type=tag'
gh api -X POST repos/mozilla-ai/cq/environments/pypi/deployment-branch-policies \
  -f 'name=sdk/python/*' -f 'type=tag'
```

A pattern's `*` is not documented to cross a `/`, so every pattern above keeps its wildcard inside the last tag segment.

### 4. Required reviewers

A tag pattern says which refs may deploy. It does not say who may create such a ref, and this repository has no tag ruleset, so anyone with write access can create a `cli/v*` or `server/v*` tag and satisfy the policy.

Add required reviewers to each publishing environment and enable **Prevent self-review**. A job cannot read an environment secret until a reviewer who did not trigger the run approves it. That is the control that actually closes the gap.

### 5. The old credentials are already gone

The organization secrets this repository used to read were deleted organization-wide on 2026-10-22, so there is nothing left to unshare or revoke. The deleted names were `DOCKERHUB_TOKEN`, `DOCKERHUB_USERNAME`, `DOCKERHUB_RO_TOKEN`, `DOCKERHUB_RO_USERNAME`, `HOMEBREW_TAP_GITHUB_TOKEN` and `GHA_PAT`. Confirm with `gh api 'orgs/mozilla-ai/audit-log?phrase=action:org.remove_actions_secret' --jq '.[] | "\(.created_at|tonumber/1000|todate)  \(.actor)  \(.key)  op=\(.operation_type)"'`, which is readable without organization admin.

Nothing in this repository reads any of those names now. Should a future workflow need a shared credential, give it an environment secret rather than an organization secret, for the reasons at the top of this file.

An environment and the job that binds it are separate objects, and nothing reports a mismatch between them. An environment holding a secret that no job binds is a credential no run can reach; a bound environment with no policy gates nothing. Cross-reference the two with `gh api repos/mozilla-ai/cq/environments --jq '.environments[].name'` against `grep -rn 'environment:' .github/workflows/`, and check each name's `protection_rules` and `deployment_branch_policy`.

## Verifying

- A `workflow_dispatch` of a release workflow from a branch is refused with "Branch is not allowed to deploy to ...".
- A `workflow_dispatch` whose tag input does not match the ref it runs on fails in the tag step before any credential is read.
- The next server release logs in to Docker Hub with no password, as a `docker-hub` deployment.
- The next CLI release pushes the cask as a `homebrew-tap` deployment, and the tap commit's author is the App.
