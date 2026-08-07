# Security Policy

## Reporting a Vulnerability

If you believe you have found a security vulnerability, please report it privately.

**Please do NOT report security vulnerabilities through public [GitHub issues](https://github.com/taylorleese/claude-toolz/issues).**

Instead, use GitHub's private vulnerability reporting: <https://github.com/taylorleese/claude-toolz/security/advisories/new>

Or email: **tleese22 [at] gmail [dot] com**

You should receive a response within 48 hours. If you do not, please follow up via email to confirm the report was received.

### What to Include

- Type of issue (e.g. command injection, credential disclosure, privilege escalation)
- Full path of the affected file, and the tag/branch/commit
- Any configuration required to reproduce
- Step-by-step reproduction instructions
- Proof-of-concept, if you have one
- Impact, including how an attacker might exploit it

### Disclosure Policy

- Please do not publicly disclose until a fix is released
- You will be credited when the fix is announced, unless you prefer to remain anonymous
- Reports are acknowledged within 48 hours and triaged within 96 hours

## Threat Model

This repository ships Claude Code plugins — markdown instructions, shell hooks, and one standard-library Python script. It has no server, no network
listener, and no persistent storage. The security-relevant surface is:

- **API keys.** `ask-llm`'s HTTP providers read `GOOGLE_API_KEY` and `DEEPSEEK_API_KEY` from the environment. They are sent only to that provider's
  official HTTPS endpoint, and are never logged, written to disk, or included in output. Its CLI providers (`codex`, `agy`) read no key at all — they
  delegate to a locally installed agent that holds its own credentials, so no secret passes through this code.
- **Subprocess execution.** CLI providers are invoked with an argument list and an absolute path resolved via `shutil.which` — never through a shell — so
  neither the context nor the question can be interpreted as a command. They run read-only: `codex` in a read-only sandbox and ephemeral, `agy` in `plan`
  mode, so neither can modify the working tree.
- **Outbound context.** `ask-llm` transmits whatever context you ask it to send to a third-party model provider. Treat it as you would any external API:
  do not send secrets or regulated data, and review the provider's data-retention policy.
- **Hooks.** `precommit-detect` registers hooks that run automatically in a Claude Code session. They are read-only — they inspect setup state and report
  it. They never install anything without an explicit approval prompt.
- **Plugin instructions.** Slash commands and skills are instructions to a model, and a model may act on them with your tool permissions. Review a plugin's
  markdown before installing it, the same as you would review a shell script.

## Security Practices

- Every workflow declares minimal `permissions`
- GitHub Actions are pinned by commit SHA
- CodeQL analysis runs on `python` and `actions` on every push, pull request, and weekly
- Dependabot alerts are enabled; Dependabot version-bump PRs cover GitHub Actions, which is the only dependency surface in the repo
- ruff's `S` (security) ruleset runs on every commit via pre-commit
- Strict mypy type checking

## Reporting Non-Vulnerabilities

For bugs, feature requests, or questions, please [open an issue](https://github.com/taylorleese/claude-toolz/issues).
