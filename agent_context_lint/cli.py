from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    tomllib = None

AGENTS_SKELETON = """# Agent Instructions

## Project Overview

- Purpose: Describe what this repository builds and who it serves.
- Main entry points: Note the primary packages, services, apps, or docs.
- Architecture notes: Capture constraints an agent should preserve when editing.

## Commands

- Install: `python -m pip install -e .`
- Test: `python -m pytest -q`
- Lint: `python -m agent_context_lint .`

## Coding Standards

- Keep changes focused, deterministic, and covered by tests when behavior changes.
- Prefer standard library and existing local patterns before adding new tools.
- Keep examples copy-paste runnable and update docs with user-visible changes.

## Boundaries / Safety

- Do not commit secrets, private data, build outputs, caches, or virtualenvs.
- Avoid unrelated refactors, formatting churn, and generated files unless requested.
- Preserve public APIs and existing lint behavior unless the task explicitly changes them.

## Handoff / Verification

- Summarize changed files, behavior, and any compatibility notes.
- Run the commands above or explain why a command could not be run.
- Call out remaining risks, assumptions, and follow-up work.
"""

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
VERIFICATION_HEADING = re.compile(r"^#{1,6}\s*(handoff\s*/\s*)?verification\b", re.I | re.M)
PLACEHOLDER_ONLY = re.compile(r"^(?:[-*+]\s*)?(?:TODO|TBD|FIXME|replace me)\.?:?$", re.I)
COMMAND_SNIPPET = re.compile(r"`{1,3}([^`\n]+)`{1,3}")
COMMAND_START = re.compile(r"^(?:python|pytest|unittest|npm|pnpm|yarn|uv|make|cargo|go|docker)\b")
VALIDATION_COMMAND = re.compile(r"\b(test|pytest|unittest|lint|ruff|flake8|mypy|build|serve|start|dev|run)\b", re.I)
MAX_COMMAND_DRIFT_FINDINGS = 3

@dataclass
class Finding:
    level: str
    file: str
    code: str
    message: str
    line: int | None = None
    suggestion: str | None = None

@dataclass
class FileScore:
    file: str
    bytes: int
    approx_tokens: int
    score: int
    findings: list[Finding]

@dataclass
class RepoContext:
    readme_text: str
    supported_commands: set[str]
    has_command_sources: bool
    metadata_diagnostics: list["MetadataDiagnostic"]

@dataclass
class MetadataDiagnostic:
    source: str
    status: str
    detail: str
    values: list[str]


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


def normalize_command(command: str) -> str:
    return " ".join(command.strip().split())


def command_in_readme(command: str, readme_text: str) -> bool:
    if not readme_text:
        return False
    return normalize_command(command).lower() in normalize_command(readme_text).lower()


def metadata_diagnostic(source: str, status: str, detail: str, values: Iterable[str] = ()) -> MetadataDiagnostic:
    return MetadataDiagnostic(source, status, detail, sorted({str(value) for value in values}))


def package_json_scripts(root: Path) -> tuple[dict[str, str], MetadataDiagnostic]:
    path = root / "package.json"
    if not path.is_file():
        return {}, metadata_diagnostic("package.json", "missing", "No package.json found.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}, metadata_diagnostic("package.json", "unreadable", "package.json could not be parsed as JSON.")
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        return {}, metadata_diagnostic("package.json", "no_scripts", "package.json does not define a scripts object.")
    parsed = {str(name): str(command) for name, command in scripts.items()}
    return parsed, metadata_diagnostic("package.json", "loaded", f"Found {len(parsed)} npm script(s).", parsed)


def fallback_pyproject_script_names(text: str) -> set[str]:
    names: set[str] = set()
    in_project_scripts = False
    assignment = re.compile(r"^(?:['\"]([^'\"]+)['\"]|([A-Za-z0-9_.-]+))\s*=")

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_project_scripts = line in {"[project.scripts]", "[project.gui-scripts]"}
            continue
        if in_project_scripts:
            match = assignment.match(line)
            if match:
                names.add((match.group(1) or match.group(2)).strip())

    return names


def pyproject_script_names(root: Path) -> tuple[set[str], MetadataDiagnostic]:
    path = root / "pyproject.toml"
    if not path.is_file():
        return set(), metadata_diagnostic("pyproject.toml", "missing", "No pyproject.toml found.")

    if tomllib is not None:
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            text = path.read_text(encoding="utf-8", errors="replace")
            names = fallback_pyproject_script_names(text)
            return names, metadata_diagnostic(
                "pyproject.toml",
                "fallback",
                f"tomllib could not parse pyproject.toml; used conservative fallback ({exc.__class__.__name__}).",
                names,
            )
        project = data.get("project", {})
        scripts = project.get("scripts", {}) if isinstance(project, dict) else {}
        gui_scripts = project.get("gui-scripts", {}) if isinstance(project, dict) else {}
        names = set()
        if isinstance(scripts, dict):
            names.update(str(name) for name in scripts)
        if isinstance(gui_scripts, dict):
            names.update(str(name) for name in gui_scripts)
        return names, metadata_diagnostic("pyproject.toml", "loaded_tomllib", f"Found {len(names)} project script(s) with tomllib.", names)

    text = path.read_text(encoding="utf-8", errors="replace")
    names = fallback_pyproject_script_names(text)
    return names, metadata_diagnostic("pyproject.toml", "loaded_fallback", f"Found {len(names)} project script(s) with fallback parser.", names)


def known_python_modules(root: Path) -> tuple[set[str], MetadataDiagnostic]:
    modules: set[str] = set()
    search_roots = [root]
    src = root / "src"
    if src.is_dir():
        search_roots.append(src)
    for search_root in search_roots:
        for path in search_root.iterdir() if search_root.is_dir() else []:
            if path.name.startswith("."):
                continue
            if path.is_dir() and (path / "__init__.py").is_file():
                modules.add(path.name)
            elif search_root == root and path.is_file() and path.suffix == ".py":
                modules.add(path.stem)
    scripts = root / "scripts"
    if scripts.is_dir():
        for script in scripts.glob("*.py"):
            modules.add(f"scripts/{script.name}")
            modules.add(script.stem)
    return modules, metadata_diagnostic("python", "loaded", f"Found {len(modules)} local Python module/script target(s).", modules)


def load_repo_context(root: Path) -> RepoContext:
    readme = root / "README.md"
    readme_text = readme.read_text(encoding="utf-8", errors="replace") if readme.is_file() else ""
    supported: set[str] = set()
    diagnostics = [
        metadata_diagnostic(
            "README.md",
            "loaded" if readme_text else "missing",
            "README.md is available for command matching." if readme_text else "No README.md found.",
        )
    ]

    package_scripts, package_diagnostic = package_json_scripts(root)
    diagnostics.append(package_diagnostic)
    for name, command in package_scripts.items():
        supported.update({
            command,
            f"npm run {name}",
            f"pnpm run {name}",
            f"pnpm {name}",
            f"yarn {name}",
        })
        if name in {"test", "start"}:
            supported.update({f"npm {name}", f"pnpm {name}", f"yarn {name}"})

    pyproject_scripts, pyproject_diagnostic = pyproject_script_names(root)
    diagnostics.append(pyproject_diagnostic)
    for name in pyproject_scripts:
        supported.add(name)

    python_modules, python_diagnostic = known_python_modules(root)
    diagnostics.append(python_diagnostic)
    for name in python_modules:
        supported.add(f"python -m {name}")
        supported.add(f"python {name}")

    diagnostics.append(metadata_diagnostic("commands", "loaded", f"Derived {len(supported)} supported command pattern(s).", supported))
    return RepoContext(readme_text, supported, bool(readme_text or supported), diagnostics)


def is_supported_command(command: str, context: RepoContext) -> bool:
    normalized = normalize_command(command).lower()
    if command_in_readme(command, context.readme_text):
        return True
    for supported in context.supported_commands:
        supported_normalized = normalize_command(supported).lower()
        if normalized == supported_normalized or normalized.startswith(supported_normalized + " "):
            return True
    return False


def likely_validation_commands(text: str) -> list[tuple[str, int]]:
    commands: list[tuple[str, int]] = []
    seen: set[str] = set()
    for match in COMMAND_SNIPPET.finditer(text):
        command = normalize_command(match.group(1))
        if not COMMAND_START.search(command) or not VALIDATION_COMMAND.search(command):
            continue
        lowered = command.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        commands.append((command, match.start(1)))
    return commands


def lint_command_drift(text: str, rel: str, context: RepoContext) -> list[Finding]:
    if not context.has_command_sources:
        return []

    findings: list[Finding] = []
    for command, start in likely_validation_commands(text):
        if is_supported_command(command, context):
            continue
        findings.append(Finding(
            "warn",
            rel,
            "command_drift",
            f"Command `{command}` is not documented in README.md and is not supported by package metadata scripts.",
            line_for(text, start),
            (
                f"Document `{command}` in README.md, add a package metadata script for it, "
                f"or update {rel} to use an existing documented validation command."
            ),
        ))
        if len(findings) >= MAX_COMMAND_DRIFT_FINDINGS:
            break
    return findings


def lint_file(path: Path, root: Path, tracked: set[str], max_bytes: int, context: RepoContext | None = None) -> FileScore:
    rel = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    findings: list[Finding] = []
    size = len(text.encode("utf-8"))
    context = context or load_repo_context(root)

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

    findings.extend(lint_command_drift(text, rel, context))

    score = 100
    for f in findings:
        score -= {"error": 35, "warn": 15, "info": 5}.get(f.level, 0)
    score = max(0, score)
    return FileScore(rel, size, max(1, size // 4), score, findings)


def render_markdown(scores: list[FileScore], root: Path, context: RepoContext, suggest_fixes: bool = False) -> str:
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
        lines += ["", "## Metadata Diagnostics"]
        for diagnostic in context.metadata_diagnostics:
            lines.append(f"- `{diagnostic.source}`: {diagnostic.status} - {diagnostic.detail}")
            if diagnostic.values:
                lines.append(f"  - Values: {', '.join(diagnostic.values)}")
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
                if suggest_fixes and f.suggestion:
                    lines.append(f"  - Suggestion: {f.suggestion}")

    lines += ["", "## Metadata Diagnostics"]
    for diagnostic in context.metadata_diagnostics:
        lines.append(f"- `{diagnostic.source}`: {diagnostic.status} - {diagnostic.detail}")
        if diagnostic.values:
            lines.append(f"  - Values: {', '.join(diagnostic.values)}")

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


def issue_to_dict(finding: Finding, suggest_fixes: bool = False) -> dict[str, object]:
    issue: dict[str, object] = {
        "severity": finding.level,
        "code": finding.code,
        "message": finding.message,
        "path": finding.file,
    }
    if finding.line is not None:
        issue["line"] = finding.line
    if suggest_fixes and finding.suggestion:
        issue["suggestion"] = finding.suggestion
    return issue


def metadata_to_dict(diagnostic: MetadataDiagnostic) -> dict[str, object]:
    return {
        "source": diagnostic.source,
        "status": diagnostic.status,
        "detail": diagnostic.detail,
        "values": diagnostic.values,
    }


def json_report(scores: list[FileScore], root: Path, context: RepoContext, exit_code: int, suggest_fixes: bool = False) -> dict[str, object]:
    issues = [issue_to_dict(f, suggest_fixes) for s in scores for f in s.findings]
    counts = {
        "error": sum(1 for issue in issues if issue["severity"] == "error"),
        "warn": sum(1 for issue in issues if issue["severity"] == "warn"),
        "info": sum(1 for issue in issues if issue["severity"] == "info"),
    }
    files = [
        {
            "path": s.file,
            "file": s.file,
            "bytes": s.bytes,
            "approx_tokens": s.approx_tokens,
            "score": s.score,
            "issues": [issue_to_dict(f, suggest_fixes) for f in s.findings],
        }
        for s in scores
    ]
    return {
        "root": str(root),
        "scanned_files": [s.file for s in scores],
        "files": files,
        "issues": issues,
        "metadata": [metadata_to_dict(diagnostic) for diagnostic in context.metadata_diagnostics],
        "summary": {
            "files_scanned": len(scores),
            "issues": len(issues),
            "error": counts["error"],
            "warn": counts["warn"],
            "info": counts["info"],
            "average_score": round(sum(s.score for s in scores) / len(scores), 1) if scores else 0,
        },
        "exit_code": exit_code,
    }


def init_agents_file(target: Path, force: bool, dry_run: bool) -> int:
    path = target.resolve() / "AGENTS.md"
    if dry_run:
        print(AGENTS_SKELETON)
        return 0
    if path.exists() and not force:
        print(f"Refusing to overwrite existing {path}. Use --force to replace it.")
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(AGENTS_SKELETON, encoding="utf-8")
    print(f"Created {path}")
    return 0


def autofix_text(text: str, add_verification: bool) -> str:
    lines = text.splitlines()
    fixed_lines: list[str] = []
    blank_count = 0

    for line in lines:
        cleaned = line.rstrip()
        if PLACEHOLDER_ONLY.fullmatch(cleaned.strip()):
            continue
        if cleaned == "":
            blank_count += 1
            if blank_count > 2:
                continue
        else:
            blank_count = 0
        fixed_lines.append(cleaned)

    fixed = "\n".join(fixed_lines).rstrip() + "\n"
    if add_verification and fixed.strip() and not VERIFICATION_HEADING.search(fixed):
        fixed = fixed.rstrip() + "\n\n## Verification\n\n- Run the repository's documented checks after changes.\n"
    return fixed


def fix_files(root: Path, patterns: Iterable[str], dry_run: bool, add_verification: bool) -> int:
    files = discover(root, patterns)
    changed: list[str] = []

    for path in files:
        original = path.read_text(encoding="utf-8", errors="replace")
        fixed = autofix_text(original, add_verification)
        if fixed == original:
            continue
        changed.append(path.relative_to(root).as_posix())
        if not dry_run:
            path.write_text(fixed, encoding="utf-8")

    action = "Would change" if dry_run else "Changed"
    for rel in changed:
        print(f"{action}: {rel}")
    print(f"{action} {len(changed)} file(s).")
    return 0


def init_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Create a minimal AGENTS.md skeleton.")
    parser.add_argument("path", nargs="?", default=".", help="Directory where AGENTS.md should be created")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing AGENTS.md")
    parser.add_argument("--dry-run", action="store_true", help="Print the skeleton without writing a file")
    args = parser.parse_args(argv)
    return init_agents_file(Path(args.path), args.force, args.dry_run)


def fix_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Safely autofix low-risk agent instruction hygiene issues.")
    parser.add_argument("path", nargs="?", default=".", help="Repository/project path to fix")
    parser.add_argument("--dry-run", action="store_true", help="Preview changed files without writing")
    parser.add_argument("--pattern", action="append", help="Additional glob pattern to scan and fix")
    parser.add_argument(
        "--add-verification",
        action="store_true",
        help="Append a minimal Verification section when one is missing",
    )
    args = parser.parse_args(argv)
    root = Path(args.path).resolve()
    patterns = DEFAULT_FILES + (args.pattern or [])
    return fix_files(root, patterns, args.dry_run, args.add_verification)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "init":
        return init_main(argv[1:])
    if argv and argv[0] == "fix":
        return fix_main(argv[1:])

    parser = argparse.ArgumentParser(
        description="Lint AI coding-agent context files for actionability, size, and secret leaks.",
        epilog="Subcommands: init [path] [--dry-run] [--force], fix [path] [--dry-run] [--add-verification]",
    )
    parser.add_argument("path", nargs="?", default=".", help="Repository/project path to scan")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON (alias for --format json)")
    parser.add_argument("--suggest-fixes", action="store_true", help="Include non-mutating fix suggestions for supported findings")
    parser.add_argument("--max-bytes", type=int, default=32000, help="Warn when a context file exceeds this byte budget")
    parser.add_argument("--pattern", action="append", help="Additional glob pattern to scan")
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()
    patterns = DEFAULT_FILES + (args.pattern or [])
    files = discover(root, patterns)
    tracked = git_tracked(root)
    context = load_repo_context(root)
    scores = [lint_file(p, root, tracked, args.max_bytes, context) for p in files]
    exit_code = 1 if any(f.level == "error" for s in scores for f in s.findings) else 0
    output_format = "json" if args.json else args.format

    if output_format == "json":
        print(json.dumps(json_report(scores, root, context, exit_code, args.suggest_fixes), indent=2))
    else:
        print(render_markdown(scores, root, context, args.suggest_fixes))

    return exit_code

if __name__ == "__main__":
    raise SystemExit(main())
