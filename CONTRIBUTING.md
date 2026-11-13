# Contributing to claude-toolz

Thanks for your interest in contributing. This is a small repository and contributions of any size are welcome.

## Code of Conduct

Please be respectful and constructive in your interactions with other contributors.

## Getting Started

### Prerequisites

- Python 3.13 or later
- [uv](https://docs.astral.sh/uv/)
- Git

### Setup

```bash
git clone https://github.com/YOUR_USERNAME/claude-toolz.git
cd claude-toolz
make install-dev
```

`make install-dev` runs `uv sync` — creating `.venv` with `pytest` and `pre-commit` from `uv.lock`, the entire
dev dependency set — and registers the pre-commit hook. After changing the `dev` group in `pyproject.toml`, run `uv lock` and commit `uv.lock`.

## Repository Layout

```text
claude-toolz/
├── .claude-plugin/
│   └── marketplace.json          # the plugin list Claude Code reads
├── plugins/
│   ├── ask-llm/                  # skill + standard-library script
│   ├── precommit-detect/         # session hooks
│   ├── resolve-github-alerts/    # slash command
│   └── revise-all-docs/          # slash commands + skill
├── scripts/
│   └── check_plugins.py          # marketplace manifest validator
└── tests/
```

Each plugin has a `.claude-plugin/plugin.json` whose `name` must match its entry in `marketplace.json`. `make check-plugins` enforces this, and CI runs it.

## Development Workflow

```bash
git checkout -b feature/your-feature-name
```

Make your change, then:

```bash
make all      # format + lint + test
```

### Adding a plugin

1. Create `plugins/<name>/.claude-plugin/plugin.json` with `name`, `version`, `description`, and `author`
2. Add `commands/`, `skills/`, and/or `hooks/` as needed
3. Add a matching entry to `.claude-plugin/marketplace.json`
4. Run `make check-plugins` — it fails both on plugins listed but missing, and on directories present but unlisted
5. Document it in `README.md`

### Adding a provider to `ask-llm`

Add an entry to `PROVIDERS` in `plugins/ask-llm/skills/ask-llm/scripts/ask.py` with a payload builder and a response parser. If the provider exposes an
OpenAI-compatible endpoint, reuse `_openai_payload` and `_openai_parse` — only the URL and env vars differ. The parametrized tests pick up new entries
automatically.

**Keep `ask.py` standard-library only.** Adding a third-party dependency reintroduces exactly the packaging and patching burden this plugin is designed to
avoid.

## Coding Standards

- **Line length**: 140
- **Toolchain**: ruff handles linting, import sorting, formatting, docstrings, and security rules. There is no separate black, isort, flake8, pydocstyle, or
  bandit hook — please do not add one back.
- **Type hints**: required on all functions; `mypy --strict` must pass
- **Docstrings**: Google style
- **Error messages**: assign first, then raise — `msg = "..."; raise ValueError(msg)` (ruff `EM` rules)
- **Markdown**: 240-character lines (markdownlint MD013). The hook fails rather than wrapping for you.

## Testing Standards

- Mock all outbound HTTP by patching `urllib.request.urlopen`; tests must never hit a real API
- Cover both the success path and the error path
- `ask.py` is imported by path in `tests/test_ask.py` — there is no installed package to import

## Submitting Changes

1. Ensure `make all` passes
2. Update `README.md` and `CLAUDE.md` if behavior changed
3. Bump `version` in the affected plugin's `plugin.json` — without it, Claude Code's install cache makes the update a silent no-op
4. Push your branch and open a pull request describing what changed and how you tested it

CI must pass: tests on Python 3.13 and 3.14, pre-commit lint, plugin manifest validation, and CodeQL.

## Security

Please report security vulnerabilities privately — see [SECURITY.md](SECURITY.md). Do not open a public issue for them.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
