# CLAUDE.md

## Project Overview

A Claude Code plugin marketplace. Four plugins live under `plugins/`, each advertised in `.claude-plugin/marketplace.json`.

This repo is **not** a Python package. There is no `[project]` table, no lockfile, and nothing is published to a package index. The only Python is
`plugins/ask-llm/skills/ask-llm/scripts/ask.py` (standard library only) and its tests.

## Key Commands

- `make test` - Run tests (pytest)
- `make lint` - Run all linters via pre-commit
- `make format` - Auto-format code
- `make check-plugins` - Verify every plugin in `marketplace.json` resolves on disk
- `make refresh-plugins` - Refresh the local marketplace mirror + installed plugins from origin/main
- `make all` - format + lint + test

## Project Structure

- `.claude-plugin/marketplace.json` - the plugin list Claude Code reads
- `plugins/<name>/.claude-plugin/plugin.json` - per-plugin manifest; `name` must match the marketplace entry
- `plugins/<name>/commands/` - slash commands
- `plugins/<name>/skills/` - skills (model-invoked)
- `plugins/<name>/hooks/` - hooks
- `scripts/check_plugins.py` - validates the manifest; run by CI
- `tests/` - pytest tests for `ask.py`; all network calls are mocked

## Plugins

- `ask-llm` - `ask.py` calls ChatGPT / Gemini / DeepSeek REST endpoints directly. Keep it standard-library only; adding a dependency reintroduces the
  packaging and patching burden this plugin exists to avoid.
- `precommit-detect` - SessionStart/PostToolUse hooks that detect pre-commit setup state and walk through approval-gated installs.
- `revise-all-docs` - `/revise-all-docs` captures session learnings; `/improve-all-docs` (and the `all-docs-improver` skill) run static quality audits.
  Depends on `claude-md-management@anthropics`.
- `resolve-github-alerts` - `/resolve-github-alerts` triages and resolves GitHub security alerts across pip/pip-tools/poetry/uv/npm/cargo/go/docker/actions
  ecosystems and opens a single PR for review.

## Releasing

No package publish step exists. To ship a plugin change: bump `version` in that plugin's `.claude-plugin/plugin.json`, merge to `main`, then
`make refresh-plugins`. Claude Code keys its install cache by version, so an unbumped version makes the update a silent no-op.

## Code Style

- Line length: 140 (ruff)
- ruff is the whole Python toolchain — linting, import sorting, formatting, docstrings (`D`), and security rules (`S`). There is no separate black, isort,
  flake8, pydocstyle, or bandit hook; do not re-add one.
- Strict mypy
- Google-style docstrings
- Error messages use `msg = "..."; raise ValueError(msg)` pattern (ruff EM rules)
- Markdown line length: 240 (markdownlint MD013) — wrap long paragraphs manually; the hook fails, it doesn't auto-wrap
- Avoid `+` at the start of continuation lines in markdown — markdownlint MD004 silently rewrites it to `-`

## Testing

- `ask.py` is imported by path in `tests/test_ask.py`; there is no installed package to import
- All provider HTTP calls are mocked by patching `urllib.request.urlopen`
- Adding a provider means adding an entry to `PROVIDERS` plus a payload builder and a response parser — the parametrized tests pick it up automatically

## Dependencies

Dev tooling only: `pytest` and `pre-commit`, installed unpinned by `make install-dev`. Dependabot tracks GitHub Actions only, because that is the sole
dependency surface left. Keep it that way.
