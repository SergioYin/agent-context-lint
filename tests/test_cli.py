import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from agent_context_lint.cli import main


def write_secret_fixture(path: Path) -> None:
    fake_token = "ghp_" + "abcdefghijklmnopqrstuvwxyz" + "ABCDE"
    path.write_text(f"# Build\nRun `pytest`.\nTOKEN={fake_token}\n", encoding="utf-8")


def run_json_scan(path: Path, *extra_args: str) -> tuple[int, dict[str, object]]:
    output = StringIO()
    with redirect_stdout(output):
        code = main([str(path), "--format", "json", *extra_args])
    return code, json.loads(output.getvalue())


class CommandDriftTests(unittest.TestCase):
    def test_readme_supported_command_does_not_warn(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("Run checks with `python -m pytest -q`.\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("# Test\nRun `python -m pytest -q`.\n", encoding="utf-8")

            code, data = run_json_scan(root)

            self.assertEqual(code, 0)
            self.assertNotIn("command_drift", {issue["code"] for issue in data["issues"]})

    def test_package_json_supported_command_does_not_warn(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text('{"scripts": {"lint": "eslint ."}}\n', encoding="utf-8")
            (root / "AGENTS.md").write_text("# Lint\nRun `npm run lint`.\n", encoding="utf-8")

            code, data = run_json_scan(root)

            self.assertEqual(code, 0)
            self.assertNotIn("command_drift", {issue["code"] for issue in data["issues"]})

    def test_unsupported_stale_command_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("Run checks with `python -m pytest -q`.\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("# Lint\nRun `npm run lint` before handoff.\n", encoding="utf-8")

            code, data = run_json_scan(root)
            drift = [issue for issue in data["issues"] if issue["code"] == "command_drift"]

            self.assertEqual(code, 0)
            self.assertEqual(len(drift), 1)
            self.assertIn("npm run lint", drift[0]["message"])

    def test_json_suggest_fixes_includes_command_drift_suggestion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("Run checks with `python -m pytest -q`.\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("# Lint\nRun `npm run lint` before handoff.\n", encoding="utf-8")

            code, data = run_json_scan(root, "--suggest-fixes")
            drift = [issue for issue in data["issues"] if issue["code"] == "command_drift"]

            self.assertEqual(code, 0)
            self.assertEqual(len(drift), 1)
            self.assertIn("suggestion", drift[0])
            self.assertIn("README.md", drift[0]["suggestion"])
            self.assertIn("package metadata script", drift[0]["suggestion"])

    def test_default_json_does_not_include_suggestions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("Run checks with `python -m pytest -q`.\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("# Lint\nRun `npm run lint` before handoff.\n", encoding="utf-8")

            code, data = run_json_scan(root)
            drift = [issue for issue in data["issues"] if issue["code"] == "command_drift"]

            self.assertEqual(code, 0)
            self.assertEqual(len(drift), 1)
            self.assertNotIn("suggestion", drift[0])

    def test_text_suggest_fixes_renders_command_drift_suggestion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("Run checks with `python -m pytest -q`.\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("# Lint\nRun `npm run lint` before handoff.\n", encoding="utf-8")
            output = StringIO()

            with redirect_stdout(output):
                code = main([str(root), "--suggest-fixes"])

            self.assertEqual(code, 0)
            self.assertIn("Suggestion: Document `npm run lint` in README.md", output.getvalue())

    def test_default_text_does_not_render_suggestions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("Run checks with `python -m pytest -q`.\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("# Lint\nRun `npm run lint` before handoff.\n", encoding="utf-8")
            output = StringIO()

            with redirect_stdout(output):
                code = main([str(root)])

            self.assertEqual(code, 0)
            self.assertIn("command_drift", output.getvalue())
            self.assertNotIn("Suggestion:", output.getvalue())


def test_markdown_scan_warns_for_missing_commands(capsys):
    code = main(["examples/demo-repo"])
    out = capsys.readouterr().out
    assert code == 0
    assert "AGENTS.md" in out
    assert "missing_commands" in out
    assert "placeholder" in out


def test_json_format_includes_machine_readable_report(capsys):
    code = main(["examples/demo-repo", "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["scanned_files"] == ["AGENTS.md"]
    assert data["files"][0]["path"] == "AGENTS.md"
    assert data["issues"][0]["severity"] in {"error", "warn", "info"}
    assert data["issues"][0]["message"]
    assert data["issues"][0]["path"] == "AGENTS.md"
    assert data["summary"]["files_scanned"] == 1
    assert data["summary"]["issues"] == len(data["issues"])
    assert data["exit_code"] == 0


def test_json_alias_still_outputs_json(capsys):
    code = main(["examples/demo-repo", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["files"][0]["file"] == "AGENTS.md"


def test_secret_is_error(tmp_path: Path, capsys):
    write_secret_fixture(tmp_path / "AGENTS.md")
    code = main([str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 1
    assert "possible_secret" in out


def test_json_reports_error_exit_code_and_line(tmp_path: Path, capsys):
    write_secret_fixture(tmp_path / "AGENTS.md")
    code = main([str(tmp_path), "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    secret_issues = [issue for issue in data["issues"] if issue["code"] == "possible_secret"]
    assert code == 1
    assert data["exit_code"] == 1
    assert data["summary"]["error"] == len(secret_issues)
    assert secret_issues[0]["severity"] == "error"
    assert secret_issues[0]["path"] == "AGENTS.md"
    assert secret_issues[0]["line"] == 3


def test_init_writes_agents_file(tmp_path: Path, capsys):
    code = main(["init", str(tmp_path)])
    out = capsys.readouterr().out
    agents = tmp_path / "AGENTS.md"
    assert code == 0
    assert agents.exists()
    assert "Created" in out
    assert "## Commands" in agents.read_text(encoding="utf-8")


def test_init_refuses_existing_agents_file(tmp_path: Path, capsys):
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# Existing\n", encoding="utf-8")
    code = main(["init", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 1
    assert "Refusing to overwrite" in out
    assert agents.read_text(encoding="utf-8") == "# Existing\n"


def test_init_force_overwrites_agents_file(tmp_path: Path, capsys):
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# Existing\n", encoding="utf-8")
    code = main(["init", str(tmp_path), "--force"])
    capsys.readouterr()
    assert code == 0
    assert agents.read_text(encoding="utf-8").startswith("# Agent Instructions")


def test_init_dry_run_prints_without_writing(tmp_path: Path, capsys):
    code = main(["init", str(tmp_path), "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0
    assert "# Agent Instructions" in out
    assert "## Handoff / Verification" in out
    assert not (tmp_path / "AGENTS.md").exists()


def test_init_skeleton_lints_cleanly(tmp_path: Path, capsys):
    assert main(["init", str(tmp_path)]) == 0
    capsys.readouterr()
    code = main([str(tmp_path), "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    unacceptable = [issue for issue in data["issues"] if issue["severity"] in {"error", "warn"}]
    assert code == 0
    assert unacceptable == []


def test_fix_dry_run_reports_without_writing(tmp_path: Path, capsys):
    agents = tmp_path / "AGENTS.md"
    original = "# Build  \n\n\n\nTODO\nRun `pytest`.\n"
    agents.write_text(original, encoding="utf-8")

    code = main(["fix", str(tmp_path), "--dry-run"])
    out = capsys.readouterr().out

    assert code == 0
    assert "Would change: AGENTS.md" in out
    assert "Would change 1 file(s)." in out
    assert agents.read_text(encoding="utf-8") == original


def test_fix_writes_safe_hygiene_changes(tmp_path: Path, capsys):
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# Build  \n\n\n\nTBD\nRun `pytest`.  \n", encoding="utf-8")

    code = main(["fix", str(tmp_path), "--add-verification"])
    out = capsys.readouterr().out

    assert code == 0
    assert "Changed: AGENTS.md" in out
    assert agents.read_text(encoding="utf-8") == (
        "# Build\n\n\nRun `pytest`.\n\n"
        "## Verification\n\n"
        "- Run the repository's documented checks after changes.\n"
    )


def test_fix_does_not_touch_unrelated_files(tmp_path: Path, capsys):
    agents = tmp_path / "AGENTS.md"
    readme = tmp_path / "README.md"
    agents.write_text("# Build  \nRun `pytest`.  \n", encoding="utf-8")
    readme.write_text("# Project  \n\n\n\nTODO\n", encoding="utf-8")

    code = main(["fix", str(tmp_path)])
    capsys.readouterr()

    assert code == 0
    assert agents.read_text(encoding="utf-8") == "# Build\nRun `pytest`.\n"
    assert readme.read_text(encoding="utf-8") == "# Project  \n\n\n\nTODO\n"
