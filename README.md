# Agent Context Lint

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

**Lint AGENTS.md, CLAUDE.md, Cursor rules, and Copilot instructions before they mislead your coding agent.**

A tiny zero-dependency CLI that audits `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, Cursor rules, and GitHub Copilot instruction files before you hand a repo to an AI coding agent.

It catches the boring-but-costly problems that make agents drift: missing build/test commands, oversized context files, vague TODO placeholders, untracked instruction files, and accidental token/secret leaks.

## Why this exists

AI coding tools increasingly depend on repository-level instruction/context files. That creates a new maintenance surface: stale, bloated, or vague instructions silently reduce agent quality. `agent-context-lint` gives teams a quick pre-flight check they can run locally or in CI.

## Features

- Scans common agent instruction files:
  - `AGENTS.md`, `AGENT.md`, `CLAUDE.md`, `GEMINI.md`
  - `.cursorrules`, `.cursor/rules/*.mdc`
  - `.github/copilot-instructions.md`
  - `.github/instructions/*.instructions.md`
- Scores each file from 0-100.
- Flags:
  - missing actionable sections (Build, Test, Constraints, Verification, etc.)
  - missing concrete shell commands
  - files likely to exceed context byte budgets
  - possible hard-coded secrets/tokens
  - TODO/TBD placeholders
  - untracked context files in git repos
- Outputs Markdown by default, JSON for automation.
- No runtime dependencies beyond Python 3.10+.


## Who is this for?

- Developers using Codex, Claude Code, Cursor, GitHub Copilot, Gemini CLI, or custom coding agents.
- Maintainers who want repositories to be easier for AI agents and human contributors to understand.
- Teams building repeatable context-engineering workflows without sending entire repositories to a model.

## Why it can earn stars

- It solves a concrete, recurring AI-coding pain: bad context causes bad agent output.
- It is tiny, auditable, and dependency-light.
- It works locally and can be added to CI.
- It produces artifacts maintainers can inspect before handing work to an AI agent.

## Install / Run

From a checkout:

```bash
python -m agent_context_lint /path/to/repo
```

JSON output:

```bash
python -m agent_context_lint /path/to/repo --json
```

Scan additional custom files:

```bash
python -m agent_context_lint . --pattern "docs/agent/*.md"
```

## Example

```bash
python -m agent_context_lint examples/demo-repo
```

Sample output:

```md
# Agent Context Lint Report
Files scanned: **1**
Average score: **45.0/100**

### `AGENTS.md` — 45/100
- ⚠️ `missing_commands`: No concrete shell commands detected...
- ℹ️ `placeholder`: Placeholder language can reduce agent reliability.
```

## CI usage

The CLI exits non-zero only for `error` findings, such as likely secret leaks. Warnings are shown but do not fail the build.

```yaml
- name: Lint AI agent context
  run: python -m agent_context_lint .
```

## Project layout

```text
agent_context_lint/   # CLI implementation
examples/demo-repo/   # intentionally imperfect demo context file
tests/                # pytest tests
```

## License

MIT
## Roadmap

- GitHub Action packaging for one-line CI adoption.
- More ecosystem-specific command detection.
- Optional autofix/init commands for common agent context files.
- Richer examples from real-world Python, Node, and docs-only repositories.
