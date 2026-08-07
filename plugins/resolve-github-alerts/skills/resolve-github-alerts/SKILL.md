---
name: resolve-github-alerts
description: Resolve GitHub security alerts — Dependabot, code scanning, and secret scanning — across pip / pip-tools / poetry / uv / npm / yarn / pnpm / cargo / go-modules / Docker / GitHub Actions ecosystems. Use when the user asks to fix, triage, resolve, or clean up security alerts, vulnerable dependencies, CVEs, or failing Dependabot PRs in a repository. Creates a branch and opens a pull request, so invoke it only on a clear request to actually remediate — not when the user is merely asking what the alerts are, or discussing them.
allowed-tools: Bash, Read, Edit, Write, Glob, Grep
---

# Resolve GitHub Alerts

This skill resolves all GitHub security alerts: Dependabot alerts,
code scanning alerts, and secret scanning alerts.

## Constants

- **Label**: `automated/resolve-github-alerts`
- **Branch**: `automated/resolve-github-alerts`
- **Base branch**: detect at runtime — do not hardcode `main`. Most
  repos use `main`, but some use `master`, `develop`, or `trunk`. Run
  `gh repo view --json defaultBranchRef --jq .defaultBranchRef.name`
  once at the start of execution and use the result everywhere a base
  branch is needed (PR creation, branch creation, etc.).

### Setup

At the start of execution, derive the GitHub owner and repo. Use
`git remote get-url origin` from the **current working directory**
(works in both the main checkout and git worktrees):

```bash
OWNER_REPO=$(git remote get-url origin | sed -E 's#.*(github\.com[:/])##;s/\.git$//')
OWNER=${OWNER_REPO%/*}
REPO=${OWNER_REPO#*/}
```

Use `$OWNER` and `$REPO` in all `gh` CLI commands below.

### Worktree Awareness

This skill may run inside a git worktree. Observe these rules:

- **Derive repo root** from `git rev-parse --show-toplevel`, never
  hard-code a path.
- **All file reads/edits** must use paths relative to the worktree
  root, not the main checkout.
- `git remote`, `git fetch`, `git push`, and `gh` commands work
  unchanged in a worktree because they share the main repo's
  remote configuration.
- **Do not run** `git worktree add/remove` — the caller manages the
  worktree lifecycle.

## Resolution Priority

1. **Fix the root cause in code** — All fixes must be committed as code
   changes: dependency upgrades in the project's manifest/lockfiles
   (e.g. `requirements*.{in,txt}`, `pyproject.toml`, `poetry.lock`,
   `uv.lock`, `package.json`, `Cargo.toml`, `go.mod`), Dockerfile base
   image tags, GitHub Actions versions, or application code fixes in
   the project's source tree. Never apply ad hoc fixes via manual
   steps. Never add lint exclusions or scanner ignores.
2. **Dismiss only for confirmed false positives** — Only dismiss alerts
   for test credentials, false positives, or transitive dependencies
   with no available patch.
3. **Create GitHub issues as last resort** — Only when the fix requires
   human judgment or access you don't have.

## PR Management Pattern

Maintain **at most ONE** open PR at a time for non-Dependabot fixes.
Identified by the `automated/resolve-github-alerts` label.

### Before creating or updating a PR

1. Search for an existing open PR:

   ```bash
   gh pr list --repo $OWNER/$REPO --label automated/resolve-github-alerts --state open --json number,title
   ```

2. **If PR exists**: Push additional commits to the existing
   `automated/resolve-github-alerts` branch and update the PR body.
3. **If no PR exists**: Create the branch from the detected base
   branch, push fixes, create the PR, and add labels/assignee:
   - **Labels**: `automated/resolve-github-alerts`, `security`, `dependencies`
   - **Assignees**: `$OWNER`

## Execution Phases

Run all four phases in order. Track results for the final summary.

---

### Phase 1: Triage Dependabot PRs

**Goal**: List open Dependabot PRs, check CI status, and fix ones with
CI failures if possible. Never auto-merge — leave merging to the user.

#### Step 1.1: List open Dependabot PRs

```bash
gh pr list --repo $OWNER/$REPO --state open --author "app/dependabot" --json number,title,headRefName
```

#### Step 1.2: Check CI status for each Dependabot PR

For each Dependabot PR, check CI status:

```bash
gh pr checks <PR_NUMBER> --repo $OWNER/$REPO
```

Categorize each PR:

- **Passing**: All required checks are successful — ready for manual merge
- **Failing**: One or more checks failed
- **Pending**: Checks still running

#### Step 1.3: Fix failing Dependabot PRs

For each failing Dependabot PR:

1. Get the PR diff to understand the dependency change:

   ```bash
   gh pr diff <PR_NUMBER> --repo $OWNER/$REPO
   ```

2. Get the failure details from the checks output.
3. Determine if the failure is fixable:
   - **Lint failures** (ruff, mypy, type errors): Read the failing
     files, determine the fix, and push a commit to the Dependabot
     branch.
   - **Test failures**: Read the test files, understand the breakage,
     fix the tests, and push.
   - **Security check failures**: Do NOT attempt to fix. Skip and
     report as "unfixable - security check failure".
4. After pushing fixes, re-check CI status and report result.

#### Step 1.4: Report Phase 1 results

Track counts: passing (ready to merge), fixed (ready to merge),
attempted fix (still failing), pending, skipped.

---

### Phase 2: Fix Remaining Dependabot Alerts

**Goal**: Resolve open Dependabot vulnerability alerts that don't have
associated PRs.

#### Step 2.1: Discover open alerts

```bash
gh api repos/$OWNER/$REPO/dependabot/alerts --jq '[.[] | select(.state == "open")] | length'
```

Get full alert details:

```bash
gh api repos/$OWNER/$REPO/dependabot/alerts \
  --jq '[.[] | select(.state == "open")] | .[] | {
    number, state,
    dependency: .dependency.package.name,
    ecosystem: .dependency.package.ecosystem,
    manifest: .dependency.manifest_path,
    severity: .security_advisory.severity,
    summary: .security_advisory.summary,
    fixed_in: .security_vulnerability.first_patched_version.identifier
  }'
```

If no open alerts, skip to Phase 3.

#### Step 2.2: Map alerts to files

Each Dependabot alert payload includes a `dependency.manifest_path`
field — that's the ground-truth file holding the vulnerable pin.
**Always prefer `manifest_path` over guesswork.** The discovery globs
below are only for finding *related* files (e.g. when a
`requirements.in` change cascades into a `requirements.txt` regen, or
when a `package.json` bump must update its lockfile).

Map by `dependency.package.ecosystem`:

| Alert ecosystem | Discovery globs (related files) |
| --- | --- |
| `pip` | `requirements*.{in,txt}`, `pyproject.toml`, `setup.py`, `setup.cfg`, `Pipfile{,.lock}`, `poetry.lock`, `uv.lock` |
| `npm` | `package.json`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` |
| `cargo` | `Cargo.toml`, `Cargo.lock` |
| `go` | `go.mod`, `go.sum` |
| `composer` | `composer.json`, `composer.lock` |
| `bundler` | `Gemfile`, `Gemfile.lock` |
| `nuget` | `*.csproj`, `packages.config`, `*.props` |
| `docker` | `**/Dockerfile*` |
| `github-actions` | `.github/workflows/*.{yml,yaml}` |

If the ecosystem isn't in the table, fall back to reading
`dependency.manifest_path` and applying the smallest possible edit
that bumps the pin — most ecosystems use a "manifest + lockfile" pair
that's straightforward to update once you've read both.

#### Step 2.3: Apply fixes

For each alert:

1. Read the file at `dependency.manifest_path` to confirm the current
   pin.
2. Determine the fix command by `dependency.package.ecosystem`:

   - **`pip` with pip-tools** (detect: any `requirements*.in` exists
     alongside its `.txt`): bump the version pin in the matching `.in`
     file. Recompile via the project's lockfile command (see
     Step 2.4).
   - **`pip` without pip-tools** (no `.in` files): bump the pin
     directly in `requirements.txt` / `pyproject.toml`'s
     `[project] dependencies` / `setup.py` `install_requires`.
   - **`pip` with poetry** (detect: `pyproject.toml` `[tool.poetry]`
     with `poetry.lock`): `poetry add <pkg>@<version>`, then
     `poetry lock --no-update`.
   - **`pip` with uv** (detect: `uv.lock`): edit the dep in
     `pyproject.toml` (or run `uv pip install <pkg>==<version>`),
     then `uv lock --upgrade-package <pkg>`.
   - **`npm`** (detect: `package-lock.json`): bump in `package.json`,
     then `npm install <pkg>@<version>` (regenerates the lockfile).
   - **`yarn`** (detect: `yarn.lock`): `yarn add <pkg>@<version>`.
   - **`pnpm`** (detect: `pnpm-lock.yaml`): `pnpm add <pkg>@<version>`.
   - **`cargo`**: bump in `Cargo.toml`, then
     `cargo update -p <pkg> --precise <version>`.
   - **`go`**: `go get <module>@<version> && go mod tidy`.
   - **`docker`**: update the image tag in the Dockerfile at
     `manifest_path`. Prefer immutable tags (digest pinning with
     `@sha256:...`) when the original used digest pinning.
   - **`github-actions`**: update the action version in the workflow
     at `manifest_path`. Prefer SHA + comment pinning (e.g.
     `uses: actions/checkout@<sha>  # v5.0.1`) when the rest of the
     repo follows that style.
3. Apply edits via the Edit tool. For commands that mutate lockfiles,
   run them in the worktree root.

#### Step 2.4: Verify the fix

**Before running ANY Python verify command below, detect the project's
Python runner.** If pip/python isn't on the default PATH, every
subsequent make/pip-compile/pytest/ruff invocation will fail with
"command not found". Detect in this order — first match wins — and
prefix all subsequent shell commands accordingly:

- `venv/bin/activate` exists → prefix with `source venv/bin/activate &&`
- `.venv/bin/activate` exists → prefix with `source .venv/bin/activate &&`
- `poetry.lock` exists → wrap commands as `poetry run <cmd>`
- `Pipfile.lock` exists → wrap commands as `pipenv run <cmd>`
- `uv.lock` exists → wrap commands as `uv run <cmd>`
- None of the above → assume system Python; run commands as-is

Apply the chosen prefix to lockfile-recompile, lint, AND test
sub-steps below. Skip this preamble entirely for npm/yarn/pnpm/cargo/go
projects — their tooling is typically on PATH via system package
managers.

After detecting the runner, run the project's verify commands in this
order — first match wins:

1. **Recompile lockfile** (only when applicable):
   - `Makefile` defines `compile-deps`, `compile-requirements`, `lock`,
     or `update-deps` → `make <target>`. Prefer `compile-deps` if it
     exists, since it usually compiles BOTH prod and dev requirements.
   - **Dev-requirements follow-up**: if you ran `make compile-requirements`
     (which typically only updates the prod tree) AND a sibling
     `make compile-requirements-dev` target exists alongside a
     `requirements-dev*.in` file, run that next so the dev lockfile
     stays in sync.
   - Else if `requirements*.in` files exist →
     `pip-compile --generate-hashes <input>.in` for EACH `.in` file
     (production AND dev).
   - Else if `poetry.lock` exists → `poetry lock --no-update`.
   - Else if `uv.lock` exists → `uv lock`.
   - npm/yarn/pnpm/cargo/go: the install command from Step 2.3
     already updated the lockfile — no separate step.

2. **Lint**:
   - `Makefile` defines `lint` → `make lint`.
   - Else `.pre-commit-config.yaml` exists →
     `pre-commit run --all-files`.
   - Else for Python: `ruff check .` if available.
   - Else for JS/TS: `npm run lint` if `package.json` has a `lint`
     script.
   - Else: surface "no lint command detected — manual review needed"
     in the PR body and continue.

3. **Test**:
   - `Makefile` defines `test` → `make test`.
   - Else for Python: `pytest` if available.
   - Else for JS/TS: `npm test` if `package.json` has a `test`
     script.
   - Else: surface "no test command detected — manual review needed"
     in the PR body and continue.

A missing lint/test step is **not** a hard failure for opening the
PR — note it in the PR body so the human reviewer knows what wasn't
auto-verified.

#### Step 2.5: Push fixes as a PR

Follow the PR Management Pattern above. Commit all Dependabot alert
fixes together with a clear message describing what was bumped and why.

---

### Phase 3: Resolve Code Scanning Alerts

**Goal**: Fix SAST/code scanning findings in source code.

#### Step 3.1: Discover open alerts

```bash
gh api repos/$OWNER/$REPO/code-scanning/alerts --jq '[.[] | select(.state == "open")] | length'
```

Get full alert details:

```bash
gh api repos/$OWNER/$REPO/code-scanning/alerts \
  --jq '[.[] | select(.state == "open")] | .[] | {
    number, state,
    rule: .rule.id,
    severity: .rule.severity,
    description: .rule.description,
    path: .most_recent_instance.location.path,
    start_line: .most_recent_instance.location.start_line,
    end_line: .most_recent_instance.location.end_line
  }'
```

If no open alerts, skip to Phase 4.

#### Step 3.2: Analyze each alert

Read the affected source file at the identified line range to
understand the context and determine the correct fix.

#### Step 3.3: Fix each alert

Apply the appropriate fix based on the alert type:

| Alert Type | Fix Pattern |
| ------------ | ------------- |
| SQL injection | Use parameterized queries |
| Command injection | Use `subprocess.run()` with list args, never `shell=True` with user input |
| Path traversal | Validate and sanitize paths, use `os.path.realpath()` + prefix check |
| XSS | Escape output, use safe templating |
| Insecure deserialization | Replace `pickle.loads` with JSON or safe alternatives |
| Hardcoded credentials | Move to environment variables |
| Weak cryptography | Upgrade to strong algorithms (AES-256, SHA-256+) |

Apply fixes using the Edit tool.

#### Step 3.4: Push fixes

Add code scanning fixes to the same PR branch (following PR Management
Pattern). If no PR exists yet, create one.

---

### Phase 4: Resolve Secret Scanning Alerts

**Goal**: Handle exposed secrets detected by GitHub secret scanning.

#### Step 4.1: Discover open alerts

```bash
gh api repos/$OWNER/$REPO/secret-scanning/alerts --jq '[.[] | select(.state == "open")] | length'
```

If no open alerts, skip to Summary.

#### Step 4.2: Triage each alert

```bash
gh api repos/$OWNER/$REPO/secret-scanning/alerts \
  --jq '[.[] | select(.state == "open")] | .[] | {
    number, state,
    secret_type: .secret_type_display_name,
    created_at
  }'
```

#### Step 4.3: Handle each alert

**For false positives** (test keys, example values, already-rotated
secrets):

- Verify the secret is not real/active.
- Note in the summary as "false positive" for manual resolution.

**For real credentials**:

1. **Always create a GitHub issue** with:
   - Title: `[Secret Scanning] Rotate exposed <secret_type>`
   - Body: Details of what was exposed, where, and what rotation steps
     are needed
   - Labels: `security`, `automated/resolve-github-alerts`
   - Assignees: `$OWNER`
2. Remove the secret from code if still present:
   - Replace with environment variable reference
   - Add the file pattern to `.gitignore` if it's a credentials file
3. Push the code fix to the PR branch

#### Guardrails for Phase 4

- **Always create a GitHub issue** for confirmed real credentials,
  even after rotation.
- Never log or echo the actual secret value in any output.
- Check if the secret is referenced in other files before removing.

---

## Summary Report

After all phases complete, output a summary table:

```markdown
## Security Alert Resolution Summary

### Phase 1: Dependabot PRs
| PR | Title | CI Status | Action |
| ---- | ------- | ---------- | -------- |
| #XX | Bump foo from 1.0 to 1.1 | Passing | Ready to merge |
| #YY | Bump bar from 2.0 to 2.1 | Fixed | Ready to merge |

### Phase 2: Dependabot Alerts
| Alert | Package | Severity | Action | Result |
| ------- | --------- | ---------- | -------- | -------- |
| #NN | package-name | high | Version bump | Fixed in PR #ZZ |

### Phase 3: Code Scanning Alerts
| Alert | Rule | File | Action | Result |
| ------- | ------ | ------ | -------- | -------- |
| #NN | rule-id | src/file.py | Fixed pattern | Fixed in PR #ZZ |

### Phase 4: Secret Scanning Alerts
| Alert | Type | Action | Result |
| ------- | ------ | -------- | -------- |
| #NN | secret-type | False positive | Noted for manual review |

### Totals
- Dependabot PRs ready to merge: X
- Dependabot alerts fixed: X
- Code scanning alerts fixed: X
- Secret scanning alerts handled: X
- Items requiring manual attention: X
```

If no issues were found across all phases, report:

```markdown
## All Clear

No open security alerts found.
- Dependabot PRs checked: 0 open
- Dependabot alerts: 0 open
- Code scanning alerts: 0 open
- Secret scanning alerts: 0 open
```

End the summary with: **Generated by `/resolve-github-alerts`**

---

## PR Format

When creating or updating the fix PR, use this format:

**Title**: `fix: resolve GitHub security alerts`

**Body**:

```markdown
## Summary

Automated resolution of GitHub security alerts.

<insert summary table from above>

## Changes

<bulleted list of specific changes made>

## Test Plan

- [ ] CI checks pass
- [ ] No new security alerts introduced
- [ ] Dependency compatibility verified

Generated by `/resolve-github-alerts`
```
