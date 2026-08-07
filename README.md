# Claude Toolz

[![CI](https://github.com/taylorleese/claude-toolz/actions/workflows/ci.yml/badge.svg)](https://github.com/taylorleese/claude-toolz/actions/workflows/ci.yml)
[![GitHub last commit](https://img.shields.io/github/last-commit/taylorleese/claude-toolz)](https://github.com/taylorleese/claude-toolz/commits/main)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Claude Code plugin marketplace: four plugins for second opinions, security triage, docs upkeep, and pre-commit setup.

Nothing here needs to be installed from a package index. The plugins are markdown, shell, and one standard-library Python script.

## Install

```text
/plugin marketplace add taylorleese/claude-toolz
/plugin install ask-llm@claude-toolz
/plugin install precommit-detect@claude-toolz
/plugin install resolve-github-alerts@claude-toolz
/plugin install revise-all-docs@claude-toolz
```

Install only the ones you want — they are independent.

## Plugins

### `ask-llm`

Gets a second opinion from a non-Claude frontier model: Codex (OpenAI's coding agent), Gemini (Google), or DeepSeek.

Two ways in. Ask in plain language — "ask Codex what it thinks of this schema", "get a second opinion on this plan", "what would another model say about
this bug" — and Claude invokes the skill. Or drive it explicitly:

```text
/ask-llm codex is this migration reversible?
/ask-llm all which caching strategy would you pick here?
/ask-llm does this error handling miss anything?
```

The first word selects the provider when it is `codex`, `gemini`, `deepseek`, or `all`; otherwise the whole argument is the question and it
defaults to Codex. `all` runs Codex, Gemini, and DeepSeek concurrently — three different vendors — and summarizes where they agree and disagree.

Providers come in two flavors. **CLI providers** drive a locally installed agent that authenticates with your own subscription, so there is no API key to
manage at all. **HTTP providers** call a REST endpoint and need a key exported in the shell profile Claude Code inherits (`~/.zshrc`, `~/.bashrc`).

| Provider | Transport | Auth | Default model | Model override |
| --- | --- | --- | --- | --- |
| `codex` | CLI | `codex login` — no API key | CLI default | `ASK_LLM_CODEX_MODEL` |
| `gemini` | HTTP | `GOOGLE_API_KEY` | `gemini-2.5-flash` | `ASK_LLM_GEMINI_MODEL` |
| `deepseek` | HTTP | `DEEPSEEK_API_KEY` | `deepseek-chat` | `ASK_LLM_DEEPSEEK_MODEL` |

`codex` is the best default: no key to manage, a coding agent rather than a raw chat model, and it runs in a read-only sandbox so it cannot touch your
working tree. It reasons before answering, so it takes seconds — use `gemini` when you want an answer immediately.

#### Checking readiness

`/ask-llm status` prints what is actually usable on this machine — no model call, so it costs nothing:

```text
PROVIDER    TRANSPORT  STATE     DETAIL
gemini      http       ready     GOOGLE_API_KEY is set
deepseek    http       ready     DEEPSEEK_API_KEY is set
codex       cli        ready     Logged in using ChatGPT
```

When a CLI provider's session has lapsed it reports `unauthenticated` along with the exact command to run. Logins are interactive, so the script never
tries to drive one itself — it names the command and Claude relays it.

#### Turning a provider off

Set `ASK_LLM_DISABLED_PROVIDERS` to a comma-separated list to hide providers you cannot use, so they are never picked and never surface an error:

```bash
export ASK_LLM_DISABLED_PROVIDERS=deepseek
```

The script uses only the Python standard library — nothing to install and no dependency to keep patched.

### `precommit-detect`

Read-only check for pre-commit setup state. Registers `SessionStart` and `PostToolUse:EnterWorktree` hooks that detect whether the current repo's
`.pre-commit-config.yaml` is wired up — pre-commit binary present, `.git/hooks/pre-commit` installed, Docker daemon reachable when the config requires it.
When something is missing, the hook surfaces the gap as `additionalContext` so Claude can walk you through approval-gated installs (one prompt per missing
item — never auto-installs).

### `resolve-github-alerts`

Triages and resolves GitHub security alerts (Dependabot, code scanning, secret scanning) across **pip / pip-tools / poetry / uv / npm / yarn / pnpm / cargo /
go-modules / Docker / GitHub Actions** ecosystems. Run it in any repo to:

- Fix failing Dependabot PRs (lint/test issues)
- Bump vulnerable dependencies and recompile lockfiles
- Remediate code scanning and secret scanning alerts
- Submit a single PR with all fixes for manual review

Auto-detects the project's verify commands (Makefile targets, pre-commit, ruff, pytest, npm scripts) — no per-project configuration required.

Two ways in, same as `ask-llm`. Run it explicitly, optionally narrowing the scope:

```text
/resolve-github-alerts
/resolve-github-alerts dependabot only
```

Or just ask — "fix the security alerts on this repo", "clean up the failing Dependabot PRs" — and Claude invokes the skill. Because it creates a branch and
opens a pull request, the skill is written to trigger only on a clear request to remediate, not when you are merely asking what the alerts are.

### `revise-all-docs`

Two ways to keep **CLAUDE.md**, **README.md**, and **`docs/**/*.md`** in sync — pick by intent.

#### `/revise-all-docs` — *"I just finished some work. Capture what we learned."*

Reads the current conversation, pulls out commands discovered, gotchas hit, and patterns enforced, and proposes additions to the right doc file for each
finding (project-internal context → `CLAUDE.md`, user-facing onboarding → `README.md`, deeper how-to → `docs/`). Run this at the end of a session that
uncovered something worth recording.

#### `/improve-all-docs` — *"Forget the session. Audit the docs as they stand today."*

Statically scans every doc file, scores each against type-appropriate rubrics (install steps actually work? public command/API surface complete? versions and
paths current? intra-doc links resolve? duplicated content?), then proposes targeted fixes — including **deletions** of stale or duplicated content, not just
additions. Run this during cleanup passes, before a release, or when docs feel out of sync with the code.

The `all-docs-improver` skill is the same audit auto-invoked when you ask in plain language ("are my docs up to date?", "check the README and docs"). The
slash command is explicit; the skill is hands-free.

#### Required dependency

Both surfaces delegate `CLAUDE.md` work to the official `claude-md-management` plugin:

```text
/plugin install claude-md-management@anthropics
```

## Development

```bash
git clone https://github.com/taylorleese/claude-toolz.git
cd claude-toolz
make install-dev
```

| Command | What it does |
| --- | --- |
| `make test` | Run the test suite |
| `make lint` | Run all linters via pre-commit |
| `make format` | Auto-format |
| `make check-plugins` | Verify every plugin in `marketplace.json` resolves on disk |
| `make refresh-plugins` | Refresh the local marketplace mirror and installed plugins |
| `make all` | format + lint + test |

### Releasing a plugin change

There is no package to publish. Bump `version` in the plugin's `.claude-plugin/plugin.json`, merge to `main`, then run `make refresh-plugins`. Claude Code
keys its install cache by version, so skipping the bump makes the update a silent no-op.

### Repository layout

```text
claude-toolz/
├── .claude-plugin/
│   └── marketplace.json          # the four plugins advertised to Claude Code
├── plugins/
│   ├── ask-llm/
│   ├── precommit-detect/
│   ├── resolve-github-alerts/
│   └── revise-all-docs/
├── scripts/
│   └── check_plugins.py          # marketplace manifest validator
└── tests/
```

## License

MIT
