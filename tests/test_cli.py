import json
from pathlib import Path

from agent_context_lint.cli import main


def write_secret_fixture(path: Path) -> None:
    fake_token = "ghp_" + "abcdefghijklmnopqrstuvwxyz" + "ABCDE"
    path.write_text(f"# Build\nRun `pytest`.\nTOKEN={fake_token}\n", encoding="utf-8")


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
