from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_FILES = [
    "AGENTS.md",
    "AGENT.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".cursorrules",
    ".cursor/rules/*.mdc",
    ".github/copilot-instructions.md",
    ".github/instructions/*.instructions.md",
]

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+\-=]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
]

ACTION_HEADINGS = re.compile(r"^#{1,3}\s*(build|test|lint|run|commands?|workflow|constraints?|style|do not|must|verification|release)", re.I | re.M)
COMMAND_HINT = re.compile(r"`{1,3}\s*(npm|pnpm|yarn|python|pytest|uv|pip|go test|cargo|make|docker|gh|git)\b", re.I)

@dataclass
class Finding:
    level: str
    file: str
    code: str
    message: str
    line: int | None = None

@dataclass
class FileScore:
    file: str
    bytes: int
    approx_tokens: int
    score: int
    findings: list[Finding]


def discover(root: Path, patterns: Iterable[str]) -> list[Path]:
    found: list[Path] = []
    for pattern in patterns:
        found.extend(p for p in root.glob(pattern) if p.is_file())
    return sorted(set(found))


def line_for(text: str, needle_start: int) -> int:
    return text.count("\n", 0, needle_start) + 1


def git_tracked(root: Path) -> set[str]:
    try:
        out = subprocess.check_output(["git", "ls-files"], cwd=root, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return set()
    return {line.strip() for line in out.splitlines() if line.strip()}


def lint_file(path: Path, root: Path, tracked: set[str], max_bytes: int) -> FileScore:
    rel = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    findings: list[Finding] = []
    size = len(text.encode("utf-8"))

    if size == 0:
        findings.append(Finding("error", rel, "empty", "Context file is empty; agents will skip or learn nothing."))
    if size > max_bytes:
        findings.append(Finding("warn", rel, "too_large", f"File is {size} bytes; keep below {max_bytes} bytes to avoid truncation/context rot."))
    if not ACTION_HEADINGS.search(text):
        findings.append(Finding("warn", rel, "missing_action_sections", "Add actionable sections such as Build, Test, Constraints, Style, or Verification."))
    if not COMMAND_HINT.search(text):
        findings.append(Finding("warn", rel, "missing_commands", "No concrete shell commands detected; include copy-pasteable build/test commands."))
    if rel not in tracked and tracked:
        findings.append(Finding("info", rel, "untracked", "File is not tracked by git yet."))

    for pat in SECRET_PATTERNS:
        for m in pat.finditer(text):
            findings.append(Finding("error", rel, "possible_secret", "Possible hard-coded token/secret in agent instructions.", line_for(text, m.start())))

    TODO_RE = re.compile(r"\b(TODO|TBD|fixme|later)\b", re.I)
    for m in TODO_RE.finditer(text):
        findings.append(Finding("info", rel, "placeholder", "Placeholder language can reduce agent reliability.", line_for(text, m.start())))

    score = 100
    for f in findings:
        score -= {"error": 35, "warn": 15, "info": 5}.get(f.level, 0)
    score = max(0, score)
    return FileScore(rel, size, max(1, size // 4), score, findings)


def render_markdown(scores: list[FileScore], root: Path) -> str:
    total_findings = sum(len(s.findings) for s in scores)
    avg = round(sum(s.score for s in scores) / len(scores), 1) if scores else 0
    lines = [
        "# Agent Context Lint Report",
        "",
        f"Root: `{root}`",
        f"Files scanned: **{len(scores)}**",
        f"Average score: **{avg}/100**",
        f"Findings: **{total_findings}**",
        "",
    ]
    if not scores:
        lines += [
            "## No context files found",
            "",
            "Create an `AGENTS.md` with build, test, style, constraints, and verification instructions.",
        ]
        return "\n".join(lines) + "\n"

    lines.append("## Files")
    for s in scores:
        lines += ["", f"### `{s.file}` — {s.score}/100", f"- Size: {s.bytes} bytes (~{s.approx_tokens} tokens)"]
        if not s.findings:
            lines.append("- ✅ No findings")
        else:
            for f in s.findings:
                where = f":{f.line}" if f.line else ""
                icon = {"error": "❌", "warn": "⚠️", "info": "ℹ️"}.get(f.level, "-")
                lines.append(f"- {icon} `{f.code}`{where}: {f.message}")

    lines += [
        "",
        "## Suggested AGENTS.md skeleton",
        "",
        "```md",
        "# Agent Instructions",
        "",
        "## Build / Run",
        "- Install: `<command>`",
        "- Run locally: `<command>`",
        "",
        "## Test / Verification",
        "- Unit tests: `<command>`",
        "- Lint/typecheck: `<command>`",
        "",
        "## Coding constraints",
        "- Keep changes minimal and covered by tests.",
        "- Do not commit secrets, generated artifacts, or unrelated refactors.",
        "",
        "## Project conventions",
        "- Describe non-obvious architecture, naming, and style rules here.",
        "```",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint AI coding-agent context files for actionability, size, and secret leaks.")
    parser.add_argument("path", nargs="?", default=".", help="Repository/project path to scan")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--max-bytes", type=int, default=32000, help="Warn when a context file exceeds this byte budget")
    parser.add_argument("--pattern", action="append", help="Additional glob pattern to scan")
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()
    patterns = DEFAULT_FILES + (args.pattern or [])
    files = discover(root, patterns)
    tracked = git_tracked(root)
    scores = [lint_file(p, root, tracked, args.max_bytes) for p in files]

    if args.json:
        print(json.dumps({"root": str(root), "files": [asdict(s) for s in scores]}, indent=2))
    else:
        print(render_markdown(scores, root))

    return 1 if any(f.level == "error" for s in scores for f in s.findings) else 0

if __name__ == "__main__":
    raise SystemExit(main())
