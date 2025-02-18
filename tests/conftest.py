import pytest
from typer.testing import CliRunner, Result # type: ignore

from communex.cli.root import app

from typing import Protocol, Optional


class InvokeCli(Protocol):
    def __call__(self, command: list[str], input: Optional[str] = None) -> Result: ...


@pytest.fixture()
def invoke_cli() -> InvokeCli:
    runner = CliRunner()
    
    def invoke(command: list[str], input: str | None = None) -> Result:
        return runner.invoke(app, command, input, env={"COLUMNS": "200"})
    
    return invoke
