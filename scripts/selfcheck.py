#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> str:
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT, check=True, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.stdout


def main() -> int:
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    run([sys.executable, "-m", "pytest", "-q"])

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "README.md").write_text("Run checks with `python -m pytest -q`.\n", encoding="utf-8")
        (root / "AGENTS.md").write_text("# Lint\nRun `npm run lint` before handoff.\n", encoding="utf-8")
        output = run([sys.executable, "-m", "agent_context_lint", str(root), "--format", "json"])
        data = json.loads(output)
        assert any(issue["code"] == "command_drift" for issue in data["issues"])
        assert any(item["source"] == "pyproject.toml" for item in data["metadata"])
        assert any(item["source"] == "commands" and item["values"] == sorted(item["values"]) for item in data["metadata"])

    print("selfcheck ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
