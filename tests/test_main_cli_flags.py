import importlib

import pytest


def _import_main():
    try:
        return importlib.import_module("main")
    except ModuleNotFoundError as e:
        pytest.fail(f"Required module 'main.py' not found. Original error: {e}")


# ---------------------------------------------------------------------------
# _parse_startup_flags
# ---------------------------------------------------------------------------

def test_parse_startup_flags_defaults():
    main = _import_main()
    cfg = main._parse_startup_flags([])
    assert cfg.reset_game is False
    assert cfg.maze_size == 3
    assert cfg.maze_seed == 0
    assert cfg.num_gates == 1


def test_parse_startup_flags_detects_reset_flag():
    main = _import_main()
    cfg = main._parse_startup_flags(["--reset-game"])
    assert cfg.reset_game is True
    assert cfg.maze_size == 3


def test_parse_startup_flags_size():
    main = _import_main()
    cfg = main._parse_startup_flags(["--size", "7"])
    assert cfg.maze_size == 7
    assert cfg.maze_seed == 0
    assert cfg.num_gates == 1


def test_parse_startup_flags_seed():
    main = _import_main()
    cfg = main._parse_startup_flags(["--seed", "42"])
    assert cfg.maze_seed == 42


def test_parse_startup_flags_gates():
    main = _import_main()
    cfg = main._parse_startup_flags(["--gates", "3"])
    assert cfg.num_gates == 3


def test_parse_startup_flags_all_combined():
    main = _import_main()
    cfg = main._parse_startup_flags(["--size", "5", "--seed", "99", "--gates", "2", "--reset-game"])
    assert cfg.maze_size == 5
    assert cfg.maze_seed == 99
    assert cfg.num_gates == 2
    assert cfg.reset_game is True


def test_parse_startup_flags_rejects_unknown_arguments():
    main = _import_main()
    with pytest.raises(ValueError):
        main._parse_startup_flags(["--not-a-real-flag"])


def test_parse_startup_flags_size_minimum():
    main = _import_main()
    with pytest.raises(ValueError, match="at least 3"):
        main._parse_startup_flags(["--size", "2"])


def test_parse_startup_flags_gates_minimum():
    main = _import_main()
    with pytest.raises(ValueError, match="at least 1"):
        main._parse_startup_flags(["--gates", "0"])


def test_parse_startup_flags_missing_value():
    main = _import_main()
    with pytest.raises(ValueError, match="requires a value"):
        main._parse_startup_flags(["--size"])
    with pytest.raises(ValueError, match="requires a value"):
        main._parse_startup_flags(["--seed"])
    with pytest.raises(ValueError, match="requires a value"):
        main._parse_startup_flags(["--gates"])


# ---------------------------------------------------------------------------
# _initialize_question_bank
# ---------------------------------------------------------------------------

class _FakeRepo:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | None]] = []

    def seed_questions(self, questions):
        self.calls.append(("seed", len(questions)))

    def reset_questions(self):
        self.calls.append(("reset", None))


def test_initialize_question_bank_without_reset_only_seeds():
    main = _import_main()
    repo = _FakeRepo()
    main._initialize_question_bank(
        repo,
        [{"id": "q1", "question_text": "q", "correct_answer": "a"}],
        reset_game=False,
    )
    assert repo.calls == [("seed", 1)]


def test_initialize_question_bank_with_reset_seeds_then_resets():
    main = _import_main()
    repo = _FakeRepo()
    main._initialize_question_bank(
        repo,
        [{"id": "q1", "question_text": "q", "correct_answer": "a"}],
        reset_game=True,
    )
    assert repo.calls == [("seed", 1), ("reset", None)]


# ---------------------------------------------------------------------------
# _build_maze
# ---------------------------------------------------------------------------

def test_build_maze_default_returns_minimal():
    main = _import_main()
    cfg = main.StartupConfig()
    maze = main._build_maze(cfg)
    assert maze.width == 3 and maze.height == 3
    assert maze.maze_id == "maze-3x3-v1"


def test_build_maze_custom_size():
    main = _import_main()
    cfg = main.StartupConfig(maze_size=5, maze_seed=42, num_gates=2)
    maze = main._build_maze(cfg)
    assert maze.width == 5 and maze.height == 5
    assert maze.start.row == 0 and maze.start.col == 0
    assert maze.exit.row == 4 and maze.exit.col == 4


def test_build_maze_custom_is_deterministic():
    main = _import_main()
    cfg = main.StartupConfig(maze_size=5, maze_seed=42, num_gates=2)
    m1 = main._build_maze(cfg)
    m2 = main._build_maze(cfg)
    assert m1.maze_id == m2.maze_id
    for pos in m1.cells:
        assert m1.cells[pos].blocked == m2.cells[pos].blocked


def test_build_maze_seed_zero_size_three_uses_minimal():
    """Default config (size=3, seed=0, gates=1) should use the hand-authored minimal maze."""
    main = _import_main()
    cfg = main.StartupConfig(maze_size=3, maze_seed=0, num_gates=1)
    maze = main._build_maze(cfg)
    assert maze.maze_id == "maze-3x3-v1"


def test_build_maze_non_default_seed_uses_procedural():
    """Non-default seed should produce a procedural maze even at size 3."""
    main = _import_main()
    cfg = main.StartupConfig(maze_size=3, maze_seed=99, num_gates=1)
    maze = main._build_maze(cfg)
    assert maze.width == 3
    gate_ids = [
        cell.puzzle_id
        for cell in maze.cells.values()
        if cell.puzzle_id is not None
    ]
    assert any("dynamic" in gid for gid in gate_ids), "procedural maze uses dynamic gate IDs"
