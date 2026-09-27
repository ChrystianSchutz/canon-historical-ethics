from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from canon import cli


def test_eval_command_targets_task_file() -> None:
    command = cli.build_eval_command(["--model", "mockllm/model"])
    assert command[1:4] == ["-m", "inspect_ai", "eval"]
    assert command[4] == "canon/inspect_adapter/task.py@canon_eval"
    assert command[-2:] == ["--model", "mockllm/model"]


def test_probe_command_targets_probe_task() -> None:
    command = cli.build_eval_command(["--model", "mockllm/model"], cli.PROBE_TASK)
    assert command[4] == "canon/inspect_adapter/task.py@canon_probe"


def test_task_file_exists_relative_to_repo_root() -> None:
    assert (cli.REPO_ROOT / cli.TASK_FILE).is_file()


def test_eval_passes_arguments_through(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Sequence[str], dict[str, Any]]] = []

    def fake_call(cmd: Sequence[str], **kwargs: Any) -> int:
        calls.append((cmd, kwargs))
        return 0

    monkeypatch.setattr(cli.subprocess, "call", fake_call)
    assert cli.main(["eval", "--model", "mockllm/model", "-T", "samples_per_cell=1"]) == 0
    cmd, kwargs = calls[0]
    assert list(cmd[-6:-2]) == ["--model", "mockllm/model", "-T", "samples_per_cell=1"]
    assert list(cmd[-2:]) == ["--timeout", cli.DEFAULT_TIMEOUT_SECONDS]
    assert kwargs["cwd"] == cli.REPO_ROOT


def test_eval_refuses_openrouter_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "load_env", lambda: None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def must_not_run(cmd: Sequence[str], **kwargs: Any) -> int:
        pytest.fail("must not run")

    monkeypatch.setattr(cli.subprocess, "call", must_not_run)
    assert cli.main(["eval", "--model", "openrouter/x/y"]) == 1
