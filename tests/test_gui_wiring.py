"""G-series: End-to-end GUI wiring tests.

Validates the Controller/EngineWorker integration with widget stubs.
Requires PyQt6 — skipped if not installed.
"""
import importlib
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(
    not importlib.util.find_spec("PyQt6"),
    reason="PyQt6 not installed — skipping GUI wiring tests",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_engine(maze_module, repo, puzzle_registry):
    main = importlib.import_module("main")
    maze = maze_module.build_minimal_3x3_maze()

    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {
        "pos": {"row": maze.start.row, "col": maze.start.col},
        "move_count": 0,
        "solved_gates": [],
        "started_at": "2026-02-13T00:00:00Z",
        "visited": [{"row": maze.start.row, "col": maze.start.col}],
        "hints_used": 0,
        "maze_size": 3,
        "num_gates": 1,
        "maze_seed": 0,
    }
    game = repo.create_game(
        player_id=player_id,
        maze_id=maze.maze_id,
        maze_version=maze.maze_version,
        initial_state=initial_state,
    )
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = main.GameEngine(
        maze=maze, repo=repo, puzzles=puzzle_registry,
        player_id=player_id, game_id=game_id,
    )
    return engine, main.Command, maze


# ---------------------------------------------------------------------------
# G.1 — GUI startup shows initial view
# ---------------------------------------------------------------------------

def test_gui_startup_shows_initial_view(qtbot, maze_module, repo, puzzle_registry):
    from gui.controller import GameController

    engine, cmd_cls, maze = _make_test_engine(maze_module, repo, puzzle_registry)
    controller = GameController(engine)

    mock_forms = MagicMock()
    mock_canvas = MagicMock()
    controller.view_changed.connect(mock_forms.update_view)
    controller.view_changed.connect(mock_canvas.update_maze)

    controller.initialize()

    assert mock_forms.update_view.called, "FormsPanel should receive initial view"
    assert mock_canvas.update_maze.called, "MazeCanvas should receive initial view"

    view = mock_forms.update_view.call_args[0][0]
    assert view.pos["row"] == maze.start.row
    assert view.pos["col"] == maze.start.col


# ---------------------------------------------------------------------------
# G.2 — Direction click updates both panels
# ---------------------------------------------------------------------------

def test_direction_click_updates_both_panels(qtbot, maze_module, repo, puzzle_registry):
    from gui.controller import GameController

    engine, cmd_cls, maze = _make_test_engine(maze_module, repo, puzzle_registry)
    controller = GameController(engine)

    mock_forms = MagicMock()
    mock_canvas = MagicMock()
    controller.view_changed.connect(mock_forms.update_view)
    controller.view_changed.connect(mock_canvas.update_maze)

    controller.initialize()
    mock_forms.reset_mock()
    mock_canvas.reset_mock()

    # Prefer a non-gated move so movement persists immediately.
    start = maze.start
    direction = None
    for d in maze.available_moves(start):
        if maze.gate_id_for(start, d) is None:
            direction = d.name
            break

    if direction is None:
        # Minimal maze may gate the only move from start; solve first, then move.
        d = maze.available_moves(start)[0]
        controller.on_command(cmd_cls(verb="go", args=[d.name]))
        qtbot.waitUntil(lambda: engine.view().pending_puzzle is not None, timeout=2000)
        controller.on_command(cmd_cls(verb="answer", args=["solve"]))
        qtbot.waitUntil(lambda: engine.view().pending_puzzle is None, timeout=2000)
        direction = d.name

    controller.on_command(cmd_cls(verb="go", args=[direction]))
    qtbot.waitUntil(lambda: mock_forms.update_view.called, timeout=2000)

    assert mock_forms.update_view.called, "FormsPanel should update after direction click"
    assert mock_canvas.update_maze.called, "MazeCanvas should update after direction click"


# ---------------------------------------------------------------------------
# G.3 — Puzzle flow through GUI
# ---------------------------------------------------------------------------

def test_puzzle_flow_through_gui(qtbot, maze_module, repo, puzzle_registry):
    from gui.controller import GameController

    engine, cmd_cls, maze = _make_test_engine(maze_module, repo, puzzle_registry)
    controller = GameController(engine)

    mock_puzzle_dialog = MagicMock()
    controller.view_changed.connect(mock_puzzle_dialog.handle_view)

    controller.initialize()

    for d in maze.available_moves(maze.start):
        gate_id = maze.gate_id_for(maze.start, d)
        if gate_id is not None:
            controller.on_command(cmd_cls(verb="go", args=[d.name]))
            qtbot.waitUntil(lambda: mock_puzzle_dialog.handle_view.call_count >= 2, timeout=2000)

            last_view = mock_puzzle_dialog.handle_view.call_args[0][0]
            if last_view.pending_puzzle is not None:
                controller.on_command(cmd_cls(verb="answer", args=["solve"]))
                qtbot.waitUntil(
                    lambda: mock_puzzle_dialog.handle_view.call_count >= 3,
                    timeout=2000,
                )
                after_view = mock_puzzle_dialog.handle_view.call_args[0][0]
                assert after_view.pending_puzzle is None, "puzzle should be cleared after answer"
                return

    pytest.skip("No gate found from start to test puzzle flow")


# ---------------------------------------------------------------------------
# G.4 — Hint flow through GUI
# ---------------------------------------------------------------------------

def test_hint_flow_through_gui(qtbot, maze_module, repo, puzzle_registry):
    from gui.controller import GameController

    engine, cmd_cls, maze = _make_test_engine(maze_module, repo, puzzle_registry)
    controller = GameController(engine)

    hint_options = []
    hint_clues = []
    controller.hint_options_ready.connect(lambda opts: hint_options.append(opts))
    controller.hint_result_ready.connect(lambda clue: hint_clues.append(clue))

    controller.initialize()

    for d in maze.available_moves(maze.start):
        gate_id = maze.gate_id_for(maze.start, d)
        if gate_id is not None:
            controller.on_command(cmd_cls(verb="go", args=[d.name]))
            qtbot.waitUntil(lambda: engine.view().pending_puzzle is not None, timeout=2000)

            controller.on_command(cmd_cls(verb="hint", args=[]))
            qtbot.waitUntil(lambda: len(hint_options) >= 1, timeout=2000)
            assert len(hint_options[-1]) >= 1, "bare hint should emit available hint options"

            controller.on_command(cmd_cls(verb="hint", args=["letter"]))
            qtbot.waitUntil(lambda: len(hint_clues) >= 1, timeout=2000)
            assert hint_clues[-1].startswith("Clue:"), "typed hint should emit a clue string"
            return

    pytest.skip("No gate found from start to test hint flow")


# ---------------------------------------------------------------------------
# G.5 — Game completion shows score
# ---------------------------------------------------------------------------

def test_game_completion_shows_score(qtbot, maze_module, repo, puzzle_registry):
    from gui.controller import GameController

    engine, cmd_cls, maze = _make_test_engine(maze_module, repo, puzzle_registry)
    controller = GameController(engine)

    completed = []
    controller.game_completed.connect(lambda m: completed.append(m))
    controller.initialize()

    # BFS to find path from start to exit
    from collections import deque
    visited = set()
    queue = deque([(maze.start, [])])
    visited.add(maze.start)
    path = []

    while queue:
        pos, moves = queue.popleft()
        if pos == maze.exit:
            path = moves
            break
        for d in maze.available_moves(pos):
            nxt = maze.next_pos(pos, d)
            if nxt and nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, moves + [d]))

    for d in path:
        controller.on_command(cmd_cls(verb="go", args=[d.name]))
        qtbot.waitUntil(lambda: True, timeout=100)

        view = engine.view()
        if view.pending_puzzle is not None:
            controller.on_command(cmd_cls(verb="answer", args=["solve"]))
            qtbot.waitUntil(lambda: True, timeout=100)
            controller.on_command(cmd_cls(verb="go", args=[d.name]))
            qtbot.waitUntil(lambda: True, timeout=100)

    assert len(completed) >= 1, "game_completed signal should fire when exit is reached"
    metrics = completed[-1]
    assert isinstance(metrics, dict), "game_completed payload must be a metrics dict"
    for key in ("elapsed_seconds", "moves", "hints_used"):
        assert key in metrics, f"missing key in completion metrics: {key}"
    assert metrics["moves"] >= 1


# ---------------------------------------------------------------------------
# G.6 — Save indicator on persist
# ---------------------------------------------------------------------------

def test_save_indicator_on_persist(qtbot, maze_module, repo, puzzle_registry):
    from gui.controller import GameController

    engine, cmd_cls, maze = _make_test_engine(maze_module, repo, puzzle_registry)
    controller = GameController(engine)

    outputs = []
    messages = []
    controller.view_changed.connect(lambda v: outputs.append(v))
    controller.messages_ready.connect(lambda m: messages.extend(m))

    controller.initialize()
    outputs.clear()
    messages.clear()

    # Prefer a non-gated move so movement persists immediately.
    start = maze.start
    direction = None
    for d in maze.available_moves(start):
        if maze.gate_id_for(start, d) is None:
            direction = d.name
            break

    if direction is None:
        # Minimal maze may gate the only move from start; solve first, then move.
        d = maze.available_moves(start)[0]
        controller.on_command(cmd_cls(verb="go", args=[d.name]))
        qtbot.waitUntil(lambda: engine.view().pending_puzzle is not None, timeout=2000)
        controller.on_command(cmd_cls(verb="answer", args=["solve"]))
        qtbot.waitUntil(lambda: engine.view().pending_puzzle is None, timeout=2000)
        direction = d.name

    controller.on_command(cmd_cls(verb="go", args=[direction]))
    qtbot.waitUntil(lambda: len(outputs) >= 1, timeout=2000)
    qtbot.waitUntil(lambda: any("saved" in msg.lower() for msg in messages), timeout=2000)
    assert any("saved" in msg.lower() for msg in messages), \
        "controller should emit a save indication when did_persist=True"
