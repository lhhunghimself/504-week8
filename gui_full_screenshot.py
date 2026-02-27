#!/usr/bin/env python3
"""Capture screenshots of the real GUI (all widgets except canvas) with the real engine."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import sys
from pathlib import Path

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication

from main import (
    Command,
    GameEngine,
    _build_maze,
    _initialize_question_bank,
    _parse_startup_flags,
    _utc_now_iso,
)
from db import HACKER_SEED_QUESTIONS, open_repo
from puzzles import PuzzleRegistry

from gui.controller import GameController
from gui_main import MainWindow, _STYLESHEET

app = QApplication(sys.argv)

save_path = Path("/tmp/gui_preview_game.db")
save_path.unlink(missing_ok=True)
repo = open_repo(save_path)
_initialize_question_bank(repo, HACKER_SEED_QUESTIONS, reset_game=True)

config = _parse_startup_flags([])
maze = _build_maze(config)
puzzles = PuzzleRegistry()

player = repo.get_or_create_player("neo")
player_id = player["id"] if isinstance(player, dict) else player.id

initial_state = {
    "pos": {"row": maze.start.row, "col": maze.start.col},
    "move_count": 0,
    "solved_gates": [],
    "started_at": _utc_now_iso(),
    "visited": [{"row": maze.start.row, "col": maze.start.col}],
    "hints_used": 0,
    "maze_size": config.maze_size,
    "num_gates": config.num_gates,
    "maze_seed": config.maze_seed,
}
game = repo.create_game(
    player_id=player_id,
    maze_id=maze.maze_id,
    maze_version=maze.maze_version,
    initial_state=initial_state,
)
game_id = game["id"] if isinstance(game, dict) else game.id

engine = GameEngine(
    maze=maze, repo=repo, puzzles=puzzles,
    player_id=player_id, game_id=game_id,
)

controller = GameController(engine)
window = MainWindow(controller, repo)
window.setStyleSheet(_STYLESHEET)
window.resize(QSize(960, 700))
window.show()
controller.initialize()
app.processEvents()

# Screenshot 1: initial state
window.grab().save("gui_real_initial.png")
print("1. Initial state captured")

# Screenshot 2: move to trigger a gate/puzzle
moves = engine.view().available_moves
if moves:
    controller.on_command(Command(verb="go", args=[moves[0]]))
    app.processEvents()
    window.grab().save("gui_real_after_move.png")
    print(f"2. After move {moves[0]} captured")

# Screenshot 3: if we hit a puzzle, request a hint
view = engine.view()
if view.pending_puzzle:
    controller.on_command(Command(verb="hint", args=[]))
    app.processEvents()
    window.grab().save("gui_real_hint_options.png")
    print("3. Hint options captured")

    controller.on_command(Command(verb="hint", args=["letter"]))
    app.processEvents()
    window.grab().save("gui_real_hint_clue.png")
    print("4. Hint clue captured")

print("\nDone. Screenshots saved as gui_real_*.png")
