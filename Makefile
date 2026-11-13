.PHONY: all help install-dev test lint format check-plugins refresh-plugins clean

# Default target - format, lint, and test
all: format lint test

help:
	@echo "Available targets:"
	@echo "  make install-dev      - Install dev tooling and the pre-commit hook"
	@echo "  make test             - Run tests"
	@echo "  make lint             - Run all linters via pre-commit"
	@echo "  make format           - Auto-format code"
	@echo "  make check-plugins    - Verify every plugin in marketplace.json resolves"
	@echo "  make refresh-plugins  - Refresh the local marketplace mirror + installed plugins"
	@echo "  make clean            - Remove caches and generated files"

# The plugins are markdown and shell, and the one Python script is standard
# library only, so pytest and pre-commit (the dev group in pyproject.toml,
# locked in uv.lock) are the entire dev dependency set.
install-dev:
	uv sync
	uv run pre-commit install

test:
	uv run pytest

lint:
	uv run pre-commit run --all-files

format:
	uv run pre-commit run trailing-whitespace --all-files
	uv run pre-commit run end-of-file-fixer --all-files
	uv run pre-commit run ruff --all-files
	uv run pre-commit run ruff-format --all-files
	uv run pre-commit run markdownlint --all-files

check-plugins:
	@python3 scripts/check_plugins.py

# Pulls origin/main into the local marketplace mirror, then updates each
# installed plugin. Use after pushing a plugin change with a version bump in
# its plugin.json. Without the version bump the update is a no-op, because
# Claude Code keys its install cache by version — fall back to:
#   claude plugin uninstall <p>@claude-toolz && claude plugin install <p>@claude-toolz
# After this completes, run /reload-plugins in your Claude Code session.
refresh-plugins:
	@echo "Refreshing claude-toolz marketplace mirror from origin..."
	@claude plugin marketplace update claude-toolz
	@echo "Updating installed plugins..."
	@for p in ask-llm precommit-detect resolve-github-alerts revise-all-docs; do \
		claude plugin update $$p@claude-toolz; \
	done
	@echo "✅ Plugins refreshed. Run /reload-plugins in your Claude Code session to apply."

clean:
	@echo "Cleaning up..."
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".DS_Store" -delete
	@echo "✅ Cleaned!"
