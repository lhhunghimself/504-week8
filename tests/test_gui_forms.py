"""E-series: Forms Panel widget contract tests.

Tests validate Team 1's widgets in isolation using hardcoded dummy data.
No engine, DB, or maze imports needed.
Skipped entirely if PyQt6 is not installed.
"""
import importlib

import pytest

# ---------------------------------------------------------------------------
# Skip entire module if PyQt6 is not available
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.skipif(
    not importlib.util.find_spec("PyQt6"),
    reason="PyQt6 not installed — skipping GUI forms tests",
)


# ---------------------------------------------------------------------------
# Dummy data fixtures (no engine needed)
# ---------------------------------------------------------------------------

@pytest.fixture
def dummy_game_view():
    main = importlib.import_module("main")
    return main.GameView(
        pos={"row": 0, "col": 0},
        cell_title="Ingress Port",
        cell_description="You jack into the internal network.",
        available_moves=["N", "E"],
        pending_puzzle=None,
        is_complete=False,
        move_count=3,
        map_text=" @ -- . \n | \n . -- X ",
        visited_count=2,
    )


@pytest.fixture
def dummy_pending_puzzle():
    return {"puzzle_id": "gate-001", "title": "Firewall Lattice", "prompt": "What is 2+2?"}


@pytest.fixture
def dummy_hint_options():
    return [
        {"type": "letter", "label": "First letter of the answer (-1pt)", "cost": 1},
        {"type": "count", "label": "Character count of the answer (-1pt)", "cost": 1},
        {"type": "category", "label": "Question category (-1pt)", "cost": 1},
        {"type": "reveal", "label": "Progressive character reveal (-2pt)", "cost": 2},
    ]


@pytest.fixture
def dummy_complete_view():
    main = importlib.import_module("main")
    return main.GameView(
        pos={"row": 2, "col": 2},
        cell_title="Root Access Gateway",
        cell_description="You reached root.",
        available_moves=[],
        pending_puzzle=None,
        is_complete=True,
        move_count=10,
        map_text=" S -- . \n | \n . -- @ ",
        visited_count=9,
    )


@pytest.fixture
def dummy_score_rows():
    return [
        {"player_handle": "neo", "metrics": {"elapsed_seconds": 42, "moves": 5, "hints_used": 0}},
        {"player_handle": "trinity", "metrics": {"elapsed_seconds": 60, "moves": 8, "hints_used": 2}},
    ]


# ---------------------------------------------------------------------------
# E.1 — Direction buttons emit correct commands
# ---------------------------------------------------------------------------

def test_direction_buttons_emit_correct_commands(qtbot):
    from gui.forms_panel import FormsPanel
    from main import Command

    panel = FormsPanel()
    qtbot.addWidget(panel)

    for direction in ["N", "S", "E", "W"]:
        with qtbot.waitSignal(panel.command_issued, timeout=1000) as sig:
            button = panel.direction_buttons[direction]
            qtbot.mouseClick(button, pytest.importorskip("PyQt6.QtCore").Qt.MouseButton.LeftButton)
        assert sig.args == [Command(verb="go", args=[direction])]


# ---------------------------------------------------------------------------
# E.2 — Answer submit emits command
# ---------------------------------------------------------------------------

def test_answer_submit_emits_command(qtbot):
    from gui.puzzle_dialog import PuzzleDialog

    dialog = PuzzleDialog()
    qtbot.addWidget(dialog)
    dialog.show_puzzle({"puzzle_id": "x", "title": "T", "prompt": "P"})

    dialog.answer_input.setText("len")
    with qtbot.waitSignal(dialog.answer_submitted, timeout=1000) as sig:
        qtbot.mouseClick(dialog.submit_button, pytest.importorskip("PyQt6.QtCore").Qt.MouseButton.LeftButton)
    assert sig.args == ["len"]


# ---------------------------------------------------------------------------
# E.3 — Hint options render as buttons
# ---------------------------------------------------------------------------

def test_hint_options_render_as_buttons(qtbot, dummy_hint_options):
    from gui.puzzle_dialog import PuzzleDialog

    dialog = PuzzleDialog()
    qtbot.addWidget(dialog)
    dialog.show_hint_options(dummy_hint_options)

    assert len(dialog.hint_buttons) == len(dummy_hint_options)


# ---------------------------------------------------------------------------
# E.4 — Hint button emits hint command
# ---------------------------------------------------------------------------

def test_hint_button_emits_hint_command(qtbot, dummy_hint_options):
    from gui.puzzle_dialog import PuzzleDialog

    dialog = PuzzleDialog()
    qtbot.addWidget(dialog)
    dialog.show_hint_options(dummy_hint_options)

    with qtbot.waitSignal(dialog.hint_requested, timeout=1000) as sig:
        qtbot.mouseClick(dialog.hint_buttons[0], pytest.importorskip("PyQt6.QtCore").Qt.MouseButton.LeftButton)
    assert sig.args == ["letter"]


# ---------------------------------------------------------------------------
# E.5 — Movement buttons disabled when unavailable
# ---------------------------------------------------------------------------

def test_movement_buttons_disabled_when_unavailable(qtbot, dummy_game_view):
    from gui.forms_panel import FormsPanel

    panel = FormsPanel()
    qtbot.addWidget(panel)
    panel.update_view(dummy_game_view)

    assert panel.direction_buttons["N"].isEnabled()
    assert panel.direction_buttons["E"].isEnabled()
    assert not panel.direction_buttons["S"].isEnabled()
    assert not panel.direction_buttons["W"].isEnabled()


# ---------------------------------------------------------------------------
# E.6 — Puzzle panel hidden when no puzzle
# ---------------------------------------------------------------------------

def test_puzzle_panel_hidden_when_no_puzzle(qtbot):
    from gui.puzzle_dialog import PuzzleDialog

    dialog = PuzzleDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.show_puzzle(None)

    assert not dialog.puzzle_area.isVisible()


# ---------------------------------------------------------------------------
# E.7 — Puzzle panel shows prompt
# ---------------------------------------------------------------------------

def test_puzzle_panel_shows_prompt(qtbot, dummy_pending_puzzle):
    from gui.puzzle_dialog import PuzzleDialog

    dialog = PuzzleDialog()
    qtbot.addWidget(dialog)
    dialog.show_puzzle(dummy_pending_puzzle)

    assert "Firewall Lattice" in dialog.title_label.text()
    assert "What is 2+2?" in dialog.prompt_label.text()


# ---------------------------------------------------------------------------
# E.8 — Status bar displays all fields
# ---------------------------------------------------------------------------

def test_status_bar_displays_all_fields(qtbot, dummy_game_view):
    from gui.status_bar import StatusBar

    bar = StatusBar()
    qtbot.addWidget(bar)
    bar.update_status(dummy_game_view)

    text = bar.status_text()
    assert "0" in text and "0" in text  # row/col from pos
    assert "3" in text  # move_count
    assert "2" in text  # visited_count


# ---------------------------------------------------------------------------
# E.9 — Score board renders rows
# ---------------------------------------------------------------------------

def test_score_board_renders_rows(qtbot, dummy_score_rows):
    from gui.score_board import ScoreBoard

    board = ScoreBoard()
    qtbot.addWidget(board)
    board.show_scores(dummy_score_rows)

    assert board.table.rowCount() == 2


# ---------------------------------------------------------------------------
# E.10 — Completion screen shown
# ---------------------------------------------------------------------------

def test_completion_screen_shown(qtbot, dummy_complete_view):
    from gui.forms_panel import FormsPanel

    panel = FormsPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.update_view(dummy_complete_view)

    assert panel.completion_overlay.isVisible()
