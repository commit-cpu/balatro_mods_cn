from typer.testing import CliRunner

from app.cli.main import app


def test_cli_has_rag_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "migrate" in result.output
    assert "import-local-tm" in result.output
    assert "sync-vectors" in result.output
    assert "search" in result.output
