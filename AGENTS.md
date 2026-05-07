# AGENTS.md

Guidance for AI coding agents working on this repository.

- Keep the package zero-dependency unless there is a strong reason.
- Prefer deterministic output and standard-library Python.
- After changes, run `python -m pytest -q`.
- Do not scan or commit `.git`, caches, virtualenvs, build outputs, or private data.
- README examples should remain copy-paste runnable.
