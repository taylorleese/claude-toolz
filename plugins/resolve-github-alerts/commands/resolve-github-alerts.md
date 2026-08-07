---
description: Resolve GitHub security alerts (Dependabot, code scanning, secret scanning) and open a PR for review
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, Skill
---

Resolve every open GitHub security alert in the current repository and submit the fixes as a single pull request.

Invoke the `resolve-github-alerts:resolve-github-alerts` skill via the Skill tool. It owns the full workflow:

1. **Triage** — enumerate Dependabot, code scanning, and secret scanning alerts.
2. **Detect** — identify the repo's ecosystems (pip / pip-tools / poetry / uv / npm / yarn / pnpm / cargo / go-modules / Docker / GitHub Actions) and its verify commands.
3. **Fix** — repair failing Dependabot PRs, bump vulnerable dependencies, recompile lockfiles, and remediate code and secret scanning alerts.
4. **Verify** — run the project's own lint and test commands before proposing anything.
5. **Submit** — open one pull request with all fixes, for manual review.

`$ARGUMENTS`, when present, narrows the scope — e.g. `dependabot only`, `skip docker`, or a specific advisory ID. Pass it to the skill verbatim.

After the skill returns, summarize: which alerts were resolved, which were left and why, and the PR URL.
