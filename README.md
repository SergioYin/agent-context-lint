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
- Creates a concise starter `AGENTS.md` for repositories that do not have one yet.
- Safely previews or applies low-risk hygiene fixes for scanned instruction files.
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

JSON output for CI/local automation:

```bash
python -m agent_context_lint /path/to/repo --format json
```

Scan additional custom files:

```bash
python -m agent_context_lint . --pattern "docs/agent/*.md"
```

Create a starter `AGENTS.md`:

```bash
python -m agent_context_lint init /path/to/repo
```

Preview the starter file without writing:

```bash
python -m agent_context_lint init . --dry-run
```

The init command refuses to overwrite an existing `AGENTS.md` unless `--force` is provided.

Preview safe hygiene fixes without writing:

```bash
python -m agent_context_lint fix . --dry-run
```

Apply safe hygiene fixes to scanned agent instruction files:

```bash
python -m agent_context_lint fix .
```

The fix command trims trailing whitespace, collapses excessive blank lines, and removes standalone placeholder-only lines such as `TODO`, `TBD`, and `replace me`. It only considers the same known agent instruction files scanned by the linter, plus any files matched with `--pattern`. To append a minimal Verification section when one is missing, pass `--add-verification`.

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

For machine-readable output:

```bash
python -m agent_context_lint . --format json
```

The JSON report includes `scanned_files`, per-file `issues`, a flattened top-level `issues` list, `summary` counts, and the `exit_code` the command returns. Each issue includes `severity`, `message`, `path`, and `line` when a source line is available. The older `--json` flag remains available as an alias for `--format json`.

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
- Richer examples from real-world Python, Node, and docs-only repositories.
