"""Resuming a results file: which episode ids are done, and the status counts of a run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aebench import cli
from aebench.run import experiment as experiment_module
from aebench.run.experiment import _done_ids, status_counts


def _write(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def _rows() -> list[dict[str, Any]]:
    return [
        {"episode_id": "a", "status": "scored"},
        {"episode_id": "b", "status": "error"},  # error, left as is
        {"episode_id": "c", "status": "error"},  # error, then scored on a retry
        {"episode_id": "c", "status": "scored"},
        {"episode_id": "d", "status": "not_run"},
        {"episode_id": "e", "status": "scored", "freeze_ok": False},
    ]


def test_done_ids_keep_error_rows_by_default(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.jsonl", _rows())
    assert _done_ids(path) == {"a", "b", "c", "d"}


def test_done_ids_with_retry_errors_leave_the_last_error_rows_to_do(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.jsonl", _rows())
    # b's last row is an error: to do again. c's last row is scored: done.
    assert _done_ids(path, retry_errors=True) == {"a", "c", "d"}


def test_done_ids_follow_the_last_row_of_an_id(tmp_path: Path) -> None:
    path = _write(tmp_path / "r.jsonl", [
        {"episode_id": "e", "status": "scored", "freeze_ok": False},
        {"episode_id": "e", "status": "scored", "freeze_ok": True},
        {"episode_id": "f", "status": "scored"},
        {"episode_id": "f", "status": "error"},
    ])
    assert _done_ids(path) == {"e", "f"}
    assert _done_ids(path, retry_errors=True) == {"e"}


def test_status_counts_count_the_last_row_of_each_episode(tmp_path: Path) -> None:
    # A retried error that then scored no longer makes the run exit 1.
    path = _write(tmp_path / "r.jsonl", _rows())
    counts = status_counts(path)
    assert (counts["scored"], counts["error"], counts["not_run"]) == (3, 1, 1)


def test_cli_run_passes_retry_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: dict[str, Any] = {}
    out = _write(tmp_path / "x.jsonl", [{"episode_id": "a", "status": "scored"}])

    class _Exp:
        paper = False

    def fake_run(path: Path, **kwargs: Any) -> Path:
        seen.update(kwargs)
        return out

    monkeypatch.setattr(experiment_module, "load_experiment", lambda p: _Exp())
    monkeypatch.setattr(experiment_module, "run_experiment", fake_run)
    assert cli.main(["run", "x.json", "--retry-errors"]) == 0
    assert seen["retry_errors"] is True
    seen.clear()
    assert cli.main(["run", "x.json"]) == 0
    assert seen["retry_errors"] is False
