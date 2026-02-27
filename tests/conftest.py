import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


def import_required(module_name: str):
    """
    Import a project module with a clearer failure message than ModuleNotFoundError.
    These tests are intended to drive development; missing modules should fail loudly.
    """
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        pytest.fail(
            f"Required module '{module_name}.py' not found yet. "
            f"Create {module_name}.py to satisfy the integration test contract. "
            f"Original error: {e}"
        )


@pytest.fixture
def maze_module():
    return import_required("maze")


@pytest.fixture
def db_module():
    return import_required("db")


@pytest.fixture
def repo(tmp_path, db_module):
    """SQLite repository at tmp_path / game.db via open_repo."""
    fn = getattr(db_module, "open_repo", None)
    if callable(fn):
        return fn(tmp_path / "game.db")
    pytest.fail(
        "db module must provide open_repo(path). "
        "See interfaces.md Section 4.3."
    )


@pytest.fixture
def repo_path(tmp_path):
    return tmp_path / "game.db"


@pytest.fixture
def procedural_maze(maze_module):
    """Seeded 5x5 maze with 2 gates for multi-gate tests."""
    build = getattr(maze_module, "build_square_maze", None)
    assert build is not None, "maze.build_square_maze must exist per interfaces.md"
    return build(size=5, seed=42, num_gates=2)


@dataclass(frozen=True)
class _TestPuzzle:
    id: str
    title: str
    prompt: str
    correct: str = "solve"
    category: str = "python"
    difficulty: int = 1

    @property
    def hint_answer(self) -> str:
        return self.correct

    @property
    def hint_answer(self) -> str:
        return self.correct

    def check(self, answer: str, state: dict[str, Any]) -> bool:
        return answer.strip() == self.correct


class _TestPuzzleRegistry:
    """
    Registry that can satisfy any puzzle_id by returning a deterministic test puzzle.
    This avoids coupling engine tests to specific content IDs in the minimal maze.
    """

    def get(self, puzzle_id: str):
        return _TestPuzzle(
            id=puzzle_id,
            title=f"TestPuzzle({puzzle_id})",
            prompt="Type 'solve' to bypass this gate.",
        )


@pytest.fixture
def puzzle_registry():
    return _TestPuzzleRegistry()

