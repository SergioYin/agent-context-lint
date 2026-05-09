# Changelog

## v0.2.2 - 2026-05

- Added `agent-context-lint fix [path]` for conservative instruction-file hygiene autofixes.
- Added `fix --dry-run` to preview which scanned agent instruction files would change without writing.
- Added `fix --add-verification` to optionally append a minimal Verification section when one is missing.

## v0.2.1 - 2026-05

- Added `agent-context-lint init [path]` to create a concise starter `AGENTS.md`.
- Added `--dry-run` to preview the starter file and `--force` to overwrite an existing `AGENTS.md`.
- Documented init examples in the README.

## v0.2.0 - 2026-05

- Added `--format text|json` with text as the default output format.
- Expanded JSON output with scanned files, per-file and flattened issues, summary counts, and the returned exit code.
- Kept `--json` as a compatibility alias for JSON output.

## v0.1.0 - 2026-05

- Initial public release of **agent-context-lint**.
- Added CLI, examples, tests, MIT license, and GitHub Actions CI.
