import json
from pathlib import Path

from agent_context_lint.cli import main


def test_markdown_scan_warns_for_missing_commands(capsys):
    code = main(["examples/demo-repo"])
    out = capsys.readouterr().out
    assert code == 0
    assert "AGENTS.md" in out
    assert "missing_commands" in out
    assert "placeholder" in out


def test_json_output(capsys):
    code = main(["examples/demo-repo", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["files"][0]["file"] == "AGENTS.md"


def test_secret_is_error(tmp_path: Path, capsys):
    (tmp_path / "AGENTS.md").write_text("# Build\nRun `pytest`.\nTOKEN=ghp_abcdefghijklmnopqrstuvwxyzABCDE\n", encoding="utf-8")
    code = main([str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 1
    assert "possible_secret" in out
