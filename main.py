from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from maze import Direction, Position


@dataclass(frozen=True)
class Command:
    """Normalized command object consumed by the engine."""

    verb: str
    args: list[str] = field(default_factory=list)


@dataclass
class CellView:
    """Per-cell data for graphical maze rendering."""

    row: int
    col: int
    kind: str  # "start" | "exit" | "normal"
    visible: bool
    is_player: bool
    has_gate: bool
    solved: bool
    connections: list[str] = field(default_factory=list)


@dataclass
class MazeSnapshot:
    """Structured maze state consumed by graphical renderers."""

    width: int
    height: int
    cells: list[CellView] = field(default_factory=list)


@dataclass
class GameView:
    """UI-agnostic state projection returned by the engine."""

    pos: dict[str, int]
    cell_title: str
    cell_description: str
    available_moves: list[str]
    pending_puzzle: dict[str, str] | None
    is_complete: bool
    move_count: int = 0
    map_text: str = ""
    visited_count: int = 0
    maze_snapshot: MazeSnapshot | None = None


@dataclass
class GameOutput:
    """Wrapper for state + user-facing messages from engine commands."""

    view: GameView
    messages: list[str] = field(default_factory=list)
    did_persist: bool = False
    hint_options: list[dict] | None = None


# ---------------------------------------------------------------------------
# Hint type definitions
# ---------------------------------------------------------------------------

_HINT_TYPES: list[dict] = [
    {"type": "letter",   "label": "First letter of the answer (-1pt)",       "cost": 1},
    {"type": "count",    "label": "Character count of the answer (-1pt)",     "cost": 1},
    {"type": "category", "label": "Question category (-1pt)",                 "cost": 1},
    {"type": "reveal",   "label": "Progressive character reveal (-2pt)",      "cost": 2},
]

_HINT_TYPE_MAP = {h["type"]: h for h in _HINT_TYPES}


class GameEngine:
    def __init__(
        self,
        *,
        maze: Any,
        repo: Any,
        puzzles: Any,
        player_id: str,
        game_id: str,
    ):
        self.maze = maze
        self.repo = repo
        self.puzzles = puzzles
        self.player_id = player_id
        self.game_id = game_id
        self._score_recorded = False
        self._reveal_progress: dict[str, int] = {}  # gate_id -> chars revealed so far
        self._load_state()

    def _load_state(self) -> None:
        game = self.repo.get_game(self.game_id)
        if game is None:
            raise KeyError(f"Unknown game_id: {self.game_id}")
        game_state = game["state"] if isinstance(game, dict) else game.state
        status = game["status"] if isinstance(game, dict) else game.status

        pos = game_state.get("pos", {"row": self.maze.start.row, "col": self.maze.start.col})
        self._pos = Position(row=pos["row"], col=pos["col"])
        self._move_count = int(game_state.get("move_count", 0))
        self._solved_gates = set(game_state.get("solved_gates", []))
        self._started_at = game_state.get("started_at")
        self._pending_gate_id: str | None = None
        self._pending_db_question: dict[str, str] | None = None
        self._is_complete = status == "completed"

        visited_raw = game_state.get("visited", [])
        self._visited: set[Position] = (
            {Position(p["row"], p["col"]) for p in visited_raw} if visited_raw
            else {self.maze.start}
        )
        self._visited.add(self._pos)

        # New keys with backwards-compatible defaults
        self._hints_used: int = int(game_state.get("hints_used", 0))
        self._maze_size: int = int(game_state.get("maze_size", 3))
        self._num_gates: int = int(game_state.get("num_gates", 1))
        self._maze_seed: int = int(game_state.get("maze_seed", 0))

    def _serialize_state(self) -> dict[str, Any]:
        return {
            "pos": {"row": self._pos.row, "col": self._pos.col},
            "move_count": self._move_count,
            "solved_gates": sorted(self._solved_gates),
            "started_at": self._started_at,
            "ended_at": _utc_now_iso() if self._is_complete else None,
            "visited": [{"row": p.row, "col": p.col} for p in sorted(self._visited, key=lambda p: (p.row, p.col))],
            "hints_used": self._hints_used,
            "maze_size": self._maze_size,
            "num_gates": self._num_gates,
            "maze_seed": self._maze_seed,
        }

    def _persist(self, status: str = "in_progress") -> None:
        self.repo.save_game(game_id=self.game_id, state=self._serialize_state(), status=status)

    def _direction_from_token(self, token: str | None) -> Direction | None:
        if token is None:
            return None
        t = token.strip().upper()
        if t == "NORTH":
            t = "N"
        elif t == "SOUTH":
            t = "S"
        elif t == "EAST":
            t = "E"
        elif t == "WEST":
            t = "W"
        return Direction.__members__.get(t)

    def _pending_puzzle_payload(self) -> dict[str, str] | None:
        if self._pending_gate_id is None:
            return None
        if self._pending_db_question is not None:
            q = self._pending_db_question
            return {
                "puzzle_id": q["id"],
                "title": "Gate Challenge",
                "prompt": q["question_text"],
            }
        puzzle = self.puzzles.get(self._pending_gate_id)
        return {"puzzle_id": puzzle.id, "title": puzzle.title, "prompt": puzzle.prompt}

    def _available_move_tokens(self) -> list[str]:
        return sorted(d.name for d in self.maze.available_moves(self._pos))

    def _maybe_finish(self) -> bool:
        if self._pos != self.maze.exit:
            return False
        self._is_complete = True
        self._persist(status="completed")

        if not self._score_recorded:
            metrics = {
                "elapsed_seconds": _elapsed_seconds(self._started_at),
                "moves": self._move_count,
                "puzzles_solved": len(self._solved_gates),
                "hints_used": self._hints_used,
            }
            self.repo.record_score(
                player_id=self.player_id,
                game_id=self.game_id,
                maze_id=self.maze.maze_id,
                maze_version=self.maze.maze_version,
                metrics=metrics,
            )
            self._score_recorded = True
        return True

    def _build_maze_snapshot(self) -> MazeSnapshot:
        cells: list[CellView] = []
        for r in range(self.maze.height):
            for c in range(self.maze.width):
                p = Position(row=r, col=c)
                cell = self.maze.cell(p)
                visible = p in self._visited
                gate_id = cell.puzzle_id
                has_gate = gate_id is not None and gate_id not in self._solved_gates
                solved = gate_id is not None and gate_id in self._solved_gates
                connections = sorted(
                    d.name for d in self.maze.available_moves(p)
                ) if visible else []
                cells.append(CellView(
                    row=r,
                    col=c,
                    kind=cell.kind.value,
                    visible=visible,
                    is_player=(p == self._pos),
                    has_gate=has_gate,
                    solved=solved,
                    connections=connections,
                ))
        return MazeSnapshot(width=self.maze.width, height=self.maze.height, cells=cells)

    def _make_view(self) -> GameView:
        cell = self.maze.cell(self._pos)
        map_text = _render_map(self.maze, self._pos, visited=self._visited, reveal_all=False)
        return GameView(
            pos={"row": self._pos.row, "col": self._pos.col},
            cell_title=cell.title,
            cell_description=cell.description,
            available_moves=self._available_move_tokens(),
            pending_puzzle=self._pending_puzzle_payload(),
            is_complete=self._is_complete,
            move_count=self._move_count,
            map_text=map_text,
            visited_count=len(self._visited),
            maze_snapshot=self._build_maze_snapshot(),
        )

    def view(self) -> GameView:
        return self._make_view()

    def _resolve_answer(self) -> str:
        """Best-effort extraction of the correct answer for hint generation.

        Policy (hybrid):
        - Missing optional metadata (no ``hint_answer`` attr): fail-soft → return ""
          which produces generic "?" clues. Hints are non-critical UX; gameplay continues.
        - Unexpected exception from the registry itself: fail-loud → re-raise so the
          bug is visible in tests and logs rather than silently swallowed.

        For DB questions, ``correct_answer`` is always available (no fallback needed).
        For registry puzzles, ``hint_answer`` is an optional contract extension.
        """
        if self._pending_db_question is not None:
            return self._pending_db_question.get("correct_answer", "")

        # Registry path: let registry errors propagate (fail-loud);
        # only suppress AttributeError for missing hint_answer (fail-soft).
        puzzle = self.puzzles.get(self._pending_gate_id)
        hint_answer = getattr(puzzle, "hint_answer", None)
        if hint_answer:
            return str(hint_answer)
        return ""

    def _build_hint_clue(self, hint_type: str) -> str:
        """Generate a clue string for the current pending puzzle."""
        answer = self._resolve_answer()

        if hint_type == "letter":
            first = answer[0] if answer else "?"
            return f"Clue: the answer starts with '{first}'"

        if hint_type == "count":
            return f"Clue: the answer is {len(answer)} character(s) long"

        if hint_type == "category":
            if self._pending_db_question is not None:
                cat = self._pending_db_question.get("category", "unknown")
            else:
                puzzle = self.puzzles.get(self._pending_gate_id)
                cat = getattr(puzzle, "category", "python")
            return f"Clue: category is '{cat}'"

        if hint_type == "reveal":
            key = self._pending_gate_id or "unknown"
            revealed = self._reveal_progress.get(key, 1)
            self._reveal_progress[key] = revealed + 1
            masked = " ".join(
                c if i < revealed else "_"
                for i, c in enumerate(answer)
            ) if answer else "?"
            return f"Clue: {masked}"

        return "No clue available."

    def handle(self, command: Command) -> GameOutput:
        verb = (command.verb or "").strip().lower()
        args = command.args or []
        messages: list[str] = []
        did_persist = False

        if verb in {"look", "map"}:
            return GameOutput(view=self._make_view(), messages=[], did_persist=False)

        if verb == "save":
            self._persist(status="completed" if self._is_complete else "in_progress")
            return GameOutput(view=self._make_view(), messages=["Progress saved."], did_persist=True)

        if verb == "status":
            total_cells = self.maze.width * self.maze.height
            explored_pct = int(100 * len(self._visited) / total_cells) if total_cells else 0
            messages = [
                f"Position: row={self._pos.row}, col={self._pos.col}",
                f"Moves: {self._move_count}",
                f"Gates/puzzles solved: {len(self._solved_gates)}",
                f"Hints used: {self._hints_used}",
                f"Visited/explored: {len(self._visited)}/{total_cells} cells ({explored_pct}%)",
            ]
            return GameOutput(view=self._make_view(), messages=messages, did_persist=False)

        if verb == "hint":
            if self._pending_gate_id is None:
                return GameOutput(
                    view=self._make_view(),
                    messages=["No puzzle active. Hints are only available when a gate puzzle is pending."],
                    did_persist=False,
                    hint_options=None,
                )

            hint_type = args[0].strip().lower() if args else None

            # Step 1: no type given — return available options for the UI to display
            if hint_type is None:
                return GameOutput(
                    view=self._make_view(),
                    messages=["Choose a hint type:"],
                    did_persist=False,
                    hint_options=list(_HINT_TYPES),
                )

            # Step 2: type given — deliver clue
            hint_def = _HINT_TYPE_MAP.get(hint_type)
            if hint_def is None:
                valid = ", ".join(_HINT_TYPE_MAP.keys())
                return GameOutput(
                    view=self._make_view(),
                    messages=[f"Unknown hint type '{hint_type}'. Valid types: {valid}"],
                    did_persist=False,
                )

            clue = self._build_hint_clue(hint_type)
            self._hints_used += hint_def["cost"]
            self._persist()
            did_persist = True
            return GameOutput(
                view=self._make_view(),
                messages=[clue],
                did_persist=did_persist,
                hint_options=None,
            )

        if verb == "answer":
            if self._pending_gate_id is None:
                return GameOutput(view=self._make_view(), messages=["No pending puzzle."], did_persist=False)
            answer = " ".join(args).strip()
            correct = False
            if self._pending_db_question is not None:
                correct = answer.strip().lower() == self._pending_db_question["correct_answer"].strip().lower()
            else:
                puzzle = self.puzzles.get(self._pending_gate_id)
                correct = puzzle.check(answer, self._serialize_state())
            if correct:
                self._solved_gates.add(self._pending_gate_id)
                if self._pending_db_question is not None and hasattr(self.repo, "mark_question_asked"):
                    self.repo.mark_question_asked(self._pending_db_question["id"])
                self._reveal_progress.pop(self._pending_gate_id, None)
                self._pending_gate_id = None
                self._pending_db_question = None
                self._persist(status="in_progress")
                did_persist = True
                messages.append("Correct.")
            else:
                messages.append("Incorrect answer.")
            return GameOutput(view=self._make_view(), messages=messages, did_persist=did_persist)

        if verb in {"n", "s", "e", "w"}:
            direction = self._direction_from_token(verb)
        elif verb == "go":
            direction = self._direction_from_token(args[0] if args else None)
        else:
            return GameOutput(view=self._make_view(), messages=["Unknown command."], did_persist=False)

        if direction is None:
            return GameOutput(view=self._make_view(), messages=["Invalid direction."], did_persist=False)

        if self._pending_gate_id is not None:
            return GameOutput(view=self._make_view(), messages=["Solve the pending puzzle first."], did_persist=False)

        gate_id = self.maze.gate_id_for(self._pos, direction)
        if gate_id is not None and gate_id not in self._solved_gates:
            self._pending_gate_id = gate_id
            if hasattr(self.repo, "get_random_question"):
                q = self.repo.get_random_question()
                if q is not None:
                    self._pending_db_question = q
            return GameOutput(view=self._make_view(), messages=["Puzzle required."], did_persist=False)

        nxt = self.maze.next_pos(self._pos, direction)
        if nxt is None:
            return GameOutput(view=self._make_view(), messages=["Blocked path."], did_persist=False)

        self._pos = nxt
        self._visited.add(self._pos)
        self._move_count += 1
        completed = self._maybe_finish()
        if not completed:
            self._persist(status="in_progress")
        return GameOutput(view=self._make_view(), messages=[], did_persist=True)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _elapsed_seconds(started_at: str | None) -> int:
    if not started_at:
        return 0
    try:
        dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    now = datetime.now(timezone.utc)
    return max(0, int((now - dt).total_seconds()))


# ---------------------------------------------------------------------------
# CLI adapter
# ---------------------------------------------------------------------------

_HELP_TEXT = """\
Commands:
  n / s / e / w      — move in that direction
  go <dir>           — move (north, south, east, west, or N/S/E/W)
  look               — re-describe current cell
  map                — show the fog-of-war map
  answer <text>      — answer a pending puzzle
  hint               — show available hint types (when puzzle is pending)
  hint <type>        — get a hint: letter | count | category | reveal
  status             — show game progress summary
  save               — save progress
  scores             — show top scores
  help               — show this help
  quit               — exit the game
"""


def _render_map(
    maze: Any,
    pos: Position,
    visited: set[Position] | None = None,
    reveal_all: bool = False,
) -> str:
    """Render a text map of the maze with the player marked. Fog of war when reveal_all=False."""
    vis = visited if visited is not None else set()
    lines: list[str] = []
    for r in range(maze.height):
        row_cells: list[str] = []
        for c in range(maze.width):
            p = Position(row=r, col=c)
            if not reveal_all and p not in vis:
                row_cells.append("###")
                continue
            cell = maze.cell(p)
            if p == pos:
                icon = " @ "
            elif p == maze.start:
                icon = " S "
            elif p == maze.exit:
                icon = " X "
            elif cell.puzzle_id is not None:
                icon = " ? "
            else:
                icon = " . "
            row_cells.append(icon)

        connected: list[str] = []
        for c, token in enumerate(row_cells):
            connected.append(token)
            if c < len(row_cells) - 1:
                p = Position(row=r, col=c)
                if not reveal_all and p not in vis:
                    connected.append("  ")
                elif Direction.E in maze.available_moves(p):
                    connected.append("--")
                else:
                    connected.append("  ")
        lines.append("".join(connected))

        if r < maze.height - 1:
            vert: list[str] = []
            for c in range(maze.width):
                p = Position(row=r, col=c)
                if not reveal_all and p not in vis:
                    vert.append("   ")
                elif Direction.S in maze.available_moves(p):
                    vert.append(" | ")
                else:
                    vert.append("   ")
                if c < maze.width - 1:
                    vert.append("  ")
            lines.append("".join(vert))
    return "\n".join(lines)


def _render_view(view: GameView, maze: Any, pos: Position, messages: list[str]) -> str:
    """Format engine output for terminal display."""
    parts: list[str] = []

    parts.append(f"\n--- {view.cell_title} ---")
    parts.append(view.cell_description)
    parts.append(f"Position: ({view.pos['row']}, {view.pos['col']})  |  Moves: {view.move_count}")
    parts.append(f"Exits: {', '.join(view.available_moves)}")

    if view.pending_puzzle:
        parts.append("")
        parts.append(f">> PUZZLE: {view.pending_puzzle['title']}")
        parts.append(view.pending_puzzle["prompt"])
        parts.append("  Use: answer <your answer>  |  hint (for hint options)")

    if view.is_complete:
        parts.append("")
        parts.append("*** ACCESS GRANTED — You have reached root. Game complete! ***")

    for msg in messages:
        parts.append(f"  [{msg}]")

    return "\n".join(parts)


def _parse_input(raw: str) -> Command:
    """Parse raw CLI input into a Command."""
    tokens = raw.strip().split()
    if not tokens:
        return Command(verb="", args=[])
    return Command(verb=tokens[0], args=tokens[1:])


@dataclass
class StartupConfig:
    """Parsed CLI startup flags."""
    reset_game: bool = False
    maze_size: int = 3
    maze_seed: int = 0
    num_gates: int = 1
    gui: bool = False


def _parse_startup_flags(argv: list[str]) -> StartupConfig:
    """Parse CLI startup flags into a StartupConfig."""
    config = StartupConfig()
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--reset-game":
            config.reset_game = True
        elif arg == "--gui":
            config.gui = True
        elif arg == "--size":
            i += 1
            if i >= len(argv):
                raise ValueError("--size requires a value")
            val = int(argv[i])
            if val < 3:
                raise ValueError("--size must be at least 3")
            config.maze_size = val
        elif arg == "--seed":
            i += 1
            if i >= len(argv):
                raise ValueError("--seed requires a value")
            config.maze_seed = int(argv[i])
        elif arg == "--gates":
            i += 1
            if i >= len(argv):
                raise ValueError("--gates requires a value")
            val = int(argv[i])
            if val < 1:
                raise ValueError("--gates must be at least 1")
            config.num_gates = val
        else:
            raise ValueError(f"Unknown argument(s): {arg}")
        i += 1
    return config


def _initialize_question_bank(
    repo: Any,
    questions: list[dict[str, Any]],
    *,
    reset_game: bool,
) -> None:
    """Seed questions and optionally reset asked flags."""
    repo.seed_questions(questions)
    if reset_game:
        repo.reset_questions()


def _build_maze(config: StartupConfig) -> Any:
    """Build a maze based on startup configuration."""
    from maze import build_minimal_3x3_maze, build_square_maze

    if config.maze_size == 3 and config.maze_seed == 0 and config.num_gates == 1:
        return build_minimal_3x3_maze()
    return build_square_maze(
        size=config.maze_size,
        seed=config.maze_seed,
        num_gates=config.num_gates,
    )


def cli_main(argv: list[str] | None = None) -> None:
    """Interactive CLI entry point for the quiz maze game."""
    from pathlib import Path
    import sys

    from db import HACKER_SEED_QUESTIONS, open_repo
    from puzzles import PuzzleRegistry

    if argv is None:
        argv = sys.argv[1:]
    try:
        config = _parse_startup_flags(argv)
    except ValueError as e:
        print(e)
        print("Usage: python main.py [--gui] [--size N] [--seed N] [--gates N] [--reset-game]")
        return

    if config.gui:
        try:
            from gui_main import gui_main as _gui_main
        except ImportError:
            print("GUI not available. Install PyQt6 and ensure gui_main.py exists.")
            print("Falling back to CLI mode.")
        else:
            _gui_main(config)
            return

    print("=" * 50)
    print("  HACK THE MAZE  —  A Python Puzzle Adventure")
    print("=" * 50)
    print()

    save_path = Path("game_save.db")
    repo = open_repo(save_path)
    _initialize_question_bank(repo, HACKER_SEED_QUESTIONS, reset_game=config.reset_game)
    if config.reset_game:
        print("Question bank reset: all questions marked unasked.")

    maze = _build_maze(config)
    puzzles = PuzzleRegistry()

    if config.maze_size != 3 or config.maze_seed != 0 or config.num_gates != 1:
        print(f"Maze: {maze.width}x{maze.height}, seed={config.maze_seed}, gates={config.num_gates}")

    handle = input("Enter your hacker handle: ").strip() or "anonymous"
    player = repo.get_or_create_player(handle)
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
        maze=maze,
        repo=repo,
        puzzles=puzzles,
        player_id=player_id,
        game_id=game_id,
    )

    view = engine.view()
    print(_render_view(view, maze, engine._pos, []))
    print()
    print(_render_map(maze, engine._pos, visited=engine._visited, reveal_all=False))
    print()
    print("Type 'help' for commands.")
    print()

    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSession terminated. Progress auto-saved.")
            engine.handle(Command(verb="save", args=[]))
            break

        if not raw:
            continue

        cmd = _parse_input(raw)
        verb = cmd.verb.lower()

        if verb == "quit":
            engine.handle(Command(verb="save", args=[]))
            print("Progress saved. Until next time, hacker.")
            break

        if verb == "help":
            print(_HELP_TEXT)
            continue

        if verb == "scores":
            scores = repo.top_scores(maze_id=maze.maze_id, limit=5)
            if not scores:
                print("  No scores recorded yet.")
            else:
                print("  -- Top Scores --")
                for i, s in enumerate(scores, 1):
                    m = s.get("metrics", {}) if isinstance(s, dict) else s.metrics
                    hints = m.get("hints_used", 0)
                    print(f"  {i}. {m.get('moves', '?')} moves, {m.get('elapsed_seconds', '?')}s, hints: {hints}")
            print()
            continue

        if verb == "map":
            print()
            print(_render_map(maze, engine._pos, visited=engine._visited, reveal_all=False))
            print()
            continue

        out = engine.handle(cmd)

        # Handle hint step-1: engine returned hint_options — show menu and get type
        if out.hint_options is not None:
            print()
            for i, opt in enumerate(out.hint_options, 1):
                print(f"  {i}. {opt['label']}")
            print()
            try:
                choice = input("  Choose hint type (number or name, Enter to cancel): ").strip()
            except (EOFError, KeyboardInterrupt):
                choice = ""
            if choice:
                # Accept number or type name
                if choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(out.hint_options):
                        chosen_type = out.hint_options[idx]["type"]
                    else:
                        print("  Invalid choice.")
                        continue
                else:
                    chosen_type = choice.lower()
                out = engine.handle(Command(verb="hint", args=[chosen_type]))
            else:
                print("  Hint cancelled.")
                continue

        print(_render_view(out.view, maze, engine._pos, out.messages))
        print()

        if out.view.is_complete:
            print("Final score recorded. Type 'scores' to see the leaderboard, or 'quit' to exit.")
            print()


if __name__ == "__main__":
    cli_main()
