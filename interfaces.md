## Quiz Maze Game — Module Interfaces

This document defines the *stable contracts* between the 3 modules:
- `maze.py` (domain / world model)
- `db.py` (persistence boundary; SQLite via SQLModel)
- `main.py` (game engine + UI wiring; CLI now, PyQt later)

The goal is to allow each module to be developed and tested independently.

---

## 1) Dependency Rules (keeps modules separable)

- `maze.py` imports **nothing** from `db.py` or `main.py`.
- `db.py` imports **nothing** from `maze.py` or `main.py`.
- `main.py` is the **only** module that imports `maze` and `db` and wires them together.

Persistence stores **only JSON-serializable primitives**. Any `maze.Position` objects must be converted to/from `{"row": int, "col": int}` at the boundary.

---

## 2) Shared Serialization Rules (DB boundary)

All persisted state must be JSON-safe:
- `str | int | float | bool | None`
- `list[...]` of JSON-safe values
- `dict[str, ...]` of JSON-safe values

Definition used in this doc:
- `AnyJSON` is a JSON-safe value:
  - `str | int | float | bool | None`
  - `list[AnyJSON]`
  - `dict[str, AnyJSON]`

Timestamps: store as ISO-8601 UTC strings (e.g., `"2026-02-13T10:15:30Z"`).

---

## 3) `maze.py` — Domain Contract

### 3.1 Public Types

- `Direction` (Enum)
  - Values: `N`, `S`, `E`, `W`
  - Each direction has a delta `(dr, dc)`

- `Position` (dataclass)
  - Fields: `row: int`, `col: int`

- `CellKind` (Enum)
  - Values: `START`, `EXIT`, `NORMAL`

- `CellSpec` (dataclass or simple class; immutable preferred)
  - `pos: Position`
  - `kind: CellKind`
  - `title: str` (hacker/Tron flavor)
  - `description: str`
  - `blocked: set[Direction]`
    - Directions that cannot be traversed from this cell
  - `puzzle_id: str | None`
    - Puzzle encountered in this cell (if any)
  - `edge_gates: dict[Direction, str]`
    - Optional movement gates per direction.
    - Value is a `gate_id` (often the same as a `puzzle_id`) that must be satisfied before moving.

### 3.2 `Maze` Interface (what `main.py` relies on)

A concrete `Maze` class should expose at least:

- Identity / sizing
  - `maze_id: str` (stable identifier, e.g. `"maze-3x3-v1"`)
  - `maze_version: str` (semantic-ish, e.g. `"1.0"`)
  - `width: int`, `height: int`
  - `start: Position`, `exit: Position`

- Topology / queries
  - `in_bounds(pos: Position) -> bool`
  - `cell(pos: Position) -> CellSpec`
  - `available_moves(pos: Position) -> set[Direction]`
    - Must account for bounds + `blocked`
  - `next_pos(pos: Position, direction: Direction) -> Position | None`
    - Returns the destination position if the move is physically possible, else `None`

- Puzzle/gate hooks (no puzzle logic inside `maze.py`)
  - `puzzle_id_at(pos: Position) -> str | None`
  - `gate_id_for(pos: Position, direction: Direction) -> str | None`
    - Returns a `gate_id` required to move along that edge, else `None`

### 3.3 Factories

- `build_minimal_3x3_maze() -> Maze`
  - Deterministic hand-authored 3x3 layout
  - Must define `start`, `exit`, walls (`blocked`), and at least 1-2 puzzle placements/gates

- `build_square_maze(size: int, seed: int, num_gates: int = 1) -> Maze`
  - Procedurally generates an N×N maze using seeded randomness
  - Uses `random.Random(seed)` for deterministic generation (e.g., recursive backtracker)
  - Start at `Position(0, 0)`, exit at `Position(size-1, size-1)`
  - Places `num_gates` gates on distinct edges along the BFS shortest path from start to exit
  - Returns a `Maze` with `maze_id` and `maze_version` appropriate for the size

### 3.4 Fog of War (renderer responsibility)

Fog of war is the **default gameplay mode**. The maze stays purely topological — visibility is handled entirely by the engine and renderer. The engine tracks a `visited` set in persisted state. The renderer hides unvisited cells (e.g., as `###`) and the exit until discovered. A `reveal_all` flag exists for debug/testing only.

---

## 4) `db.py` — Persistence Contract (SQLite via SQLModel)

### 4.1 Records (DTOs) returned to `main.py`

Repository methods return plain `dict[str, Any]`. Dataclass definitions below document the expected dict shape; they serve as living documentation of the contract.

- `PlayerRecord`
  - `id: str`
  - `handle: str`
  - `created_at: str`

- `GameRecord`
  - `id: str`
  - `player_id: str`
  - `maze_id: str`
  - `maze_version: str`
  - `state: dict[str, AnyJSON]`  (opaque to the DB layer)
  - `status: str`  (`"in_progress"` or `"completed"`)
  - `created_at: str`
  - `updated_at: str`

- `ScoreRecord`
  - `id: str`
  - `player_id: str`
  - `game_id: str`
  - `maze_id: str`
  - `maze_version: str`
  - `metrics: dict[str, AnyJSON]`
  - `created_at: str`

- `QuestionRecord`
  - `id: str`
  - `question_text: str`
  - `correct_answer: str`
  - `category: str` (optional grouping)
  - `has_been_asked: bool`

### 4.2 Repository Interface

`main.py` depends on an object (a **GameRepository**) providing these methods. The default implementation is `SqliteGameRepository`. All methods return `dict[str, Any]` matching the record shapes above. The SQLModel ORM is an internal implementation detail of `db.py` and does not leak into the return types.

- Player ops
  - `get_player(player_id: str) -> dict | None`
  - `get_or_create_player(handle: str) -> dict`

- Game ops
  - `create_game(player_id: str, maze_id: str, maze_version: str, initial_state: dict) -> dict`
  - `get_game(game_id: str) -> dict | None`
  - `save_game(game_id: str, state: dict, status: str = "in_progress") -> dict`

- Score ops
  - `record_score(player_id: str, game_id: str, maze_id: str, maze_version: str, metrics: dict) -> dict`
  - `top_scores(maze_id: str | None = None, limit: int = 10) -> list[dict]`

- Question bank ops
  - `get_random_question(category: str | None = None) -> dict | None` — returns a random unasked question; `None` if all exhausted
  - `mark_question_asked(question_id: str) -> None` — marks a question so it is not reused
  - `seed_questions(questions: list[dict]) -> None` — bulk-insert questions (idempotent via merge)
  - `reset_questions() -> None` — resets all `has_been_asked` to `False`

- Optional lifecycle
  - `close() -> None` — release DB resources (if applicable)

Notes:
- `state` is treated as an opaque JSON dict by the DB layer (no imports from `maze.py`).
- IDs are strings (uuid recommended).
- SQLModel table classes (`PlayerModel`, `GameModel`, `ScoreModel`, `QuestionModel`) back the SQLite tables. JSON-typed fields (`state`, `metrics`) are stored as JSON strings internally and parsed/serialized at the repository boundary.

### 4.3 Factory

- `open_repo(path: str | Path) -> SqliteGameRepository`
  - Returns a `SqliteGameRepository` connected to the given path.
  - Creates the database and tables if they do not exist.

---

## 5) `main.py` — Engine + UI Wiring (CLI now, PyQt later)

### 5.1 Game State (engine-owned; persisted via DB as JSON dict)

The engine maintains a state object; when persisting, it must be converted to JSON-safe dict.

Persisted keys:
- `pos: {"row": int, "col": int}`
- `move_count: int`
- `solved_gates: list[str]` (or `solved_puzzles: list[str]`)
- `started_at: str`
- `ended_at: str | None`
- `visited: list[{"row": int, "col": int}]` — cells the player has been to; used for fog-of-war rendering
- `hints_used: int` — total hint cost consumed (each hint type has a cost; affects scoring)
- `maze_size: int` — side length of the generated maze (needed to reconstruct on load)
- `num_gates: int` — number of gates placed (needed to reconstruct on load)
- `maze_seed: int` — seed used to generate the maze (needed to reconstruct on load)

Backwards-compatible load defaults (if a key is missing on load):
- `visited`: `[maze.start]`
- `hints_used`: `0`
- `maze_size`: `3`
- `num_gates`: `1`
- `maze_seed`: `0`

Note on `hints_used` and scoring: `hints_used` is the sum of `cost` values from each hint
used. It is recorded in score metrics so the leaderboard can apply a penalty or secondary
sort. The engine records the raw total; the scoring formula is determined by the leaderboard
layer.

### 5.2 Puzzle Contract (no UI assumptions)

- `Puzzle`
  - `id: str`
  - `title: str`
  - `prompt: str`
  - `category: str` — content grouping; values: `"python"`, `"security"`, `"output"`, `"debugging"`. Defaults to `"python"`.
  - `difficulty: int` — 1 = easy, 2 = medium, 3 = hard. Defaults to `1`.
  - `hint_answer: str` (optional property) — primary accepted answer exposed for hint generation. Not required by the contract; engines use `getattr(puzzle, "hint_answer", None)`.
  - `check(answer: str, state: dict[str, AnyJSON]) -> bool`
    - Engine passes a JSON-safe view of state (or a lightweight state object internally)

- `PuzzleRegistry`
  - `get(puzzle_id: str) -> Puzzle`
  - Must return a valid `Puzzle` for any `puzzle_id`, including unknown IDs (via a themed fallback).

### 5.3 Engine Contract (UI-agnostic)

The engine should not print or read input directly. It should accept intents/commands and return a result.

- `GameEngine`
  - Constructor inputs:
    - `maze: Maze` (from `maze.py`)
    - `repo: GameRepository` (from `db.py`) — used for persistence and as the question bank
    - `puzzles: PuzzleRegistry`
    - `player_id: str`
    - `game_id: str`
  - Methods:
    - `view() -> GameView`
    - `handle(command: Command) -> GameOutput`
  - When a player hits a gated door, the engine requests an unused question from the repo via `get_random_question()`. Falls back to `PuzzleRegistry` if none available. On correct answer, calls `mark_question_asked(question_id)`.

- `Command` (parsed from UI)
  - `verb: str`
  - `args: list[str]`

- `GameView` (what UI renders)
  - `pos: {"row": int, "col": int}`
  - `cell_title: str`
  - `cell_description: str`
  - `available_moves: list[str]` (e.g. `["N","E"]`)
  - `pending_puzzle: {"puzzle_id": str, "title": str, "prompt": str} | None`
    - Note: `pending_puzzle["puzzle_id"]` is an opaque identifier. When sourced from the DB question bank it is a question `id`; when sourced from `PuzzleRegistry` it is the puzzle/gate id.
  - `is_complete: bool`
  - `move_count: int`
  - `map_text: str` — pre-rendered fog-of-war ASCII map (always populated, never None)
  - `visited_count: int` — number of distinct cells the player has entered

- `GameOutput`
  - `view: GameView`
  - `messages: list[str]` (UI can display however it wants)
  - `did_persist: bool`
  - `hint_options: list[dict] | None` — populated only when `verb="hint"` with no args and
    a puzzle is pending; `None` in all other cases.
    Each dict: `{"type": str, "label": str, "cost": int}`
    - `type`: one of `"letter"`, `"count"`, `"category"`, `"reveal"`
    - `label`: human-readable description for display (e.g. `"First letter (-1pt)"`)
    - `cost`: increment to `hints_used` if this type is chosen

### 5.4 CLI rendering (fog of war)

- `_render_map(maze, pos, visited: set[Position], reveal_all: bool = False) -> str`
  - Default is `reveal_all=False` (fog of war). Pass `reveal_all=True` for debug only.
  - Renders ASCII map with player at `pos`
  - Default (`reveal_all=False`): unvisited cells show as `###`; exit hidden until discovered
  - `reveal_all=True`: full map visible (debug/testing only)
  - Engine tracks `visited` in state and persists as `list[{"row": int, "col": int}]`

### 5.5 CLI command grammar

Verbs (CLI now; PyQt will trigger equivalent commands):
- Movement: `n|s|e|w` or `go <n|s|e|w>`
- `look` (re-describe current cell)
- `map` (show the fog-of-war map)
- `answer <text>` (submit answer to pending puzzle)
- `hint` — two-step flow:
  - Step 1 — bare `hint` (no args): engine returns `hint_options` in `GameOutput`;
    `hints_used` is NOT incremented yet. CLI renders a numbered menu; PyQt renders buttons.
  - Step 2 — `hint <type>`: engine delivers the clue, increments `hints_used` by the
    type's cost, and persists. Types and costs:
    - `letter`   — first letter of correct answer (cost: 1)
    - `count`    — character count of correct answer (cost: 1)
    - `category` — question category (cost: 1)
    - `reveal`   — progressive character reveal, one more char per use (cost: 2)
  - If no puzzle is pending: returns an info message, no state change, `hint_options=None`.
- `status` (show game progress: position, moves, gates solved, hints used, exploration %)
- `save` (persist explicitly; engine may also autosave)
- `scores` (show leaderboard / top scores)
- `help` (show command help)
- `quit`

---

## 6) Versioning & Compatibility

- Maze compatibility keys stored in DB:
  - `maze_id`, `maze_version`
- DB compatibility:
  - `schema_version: int` (repository-internal; recommended storage: SQLite `PRAGMA user_version`)
- Rule: if `schema_version` changes, provide a migration path (later). For now, keep it at `1` and preserve backward compatibility within the prototype.

---

## 7) PyQt GUI Contract

This section defines the contracts for the PyQt6 graphical user interface, structured for three parallel development teams.

### 7.1 Module Layout

| File | Owner | Purpose |
|---|---|---|
| `gui_main.py` | Team 3 (Controller) | Entry point: builds QApplication, wires components |
| `gui/forms_panel.py` | Team 1 (UI/UX) | Room info, movement buttons, answer input, hint buttons |
| `gui/puzzle_dialog.py` | Team 1 (UI/UX) | Modal/inline puzzle display with answer + hints |
| `gui/status_bar.py` | Team 1 (UI/UX) | Position, moves, gates, hints, exploration % |
| `gui/score_board.py` | Team 1 (UI/UX) | Top scores table |
| `gui/maze_canvas.py` | Team 2 (Canvas) | Graphical maze rendering (toolkit TBD; must be QWidget-embeddable) |
| `gui/controller.py` | Team 3 (Controller) | GameController QObject — wires engine to widgets |
| `gui/engine_worker.py` | Team 3 (Controller) | QThread wrapper around GameEngine |

Dependency rule: `gui/` modules may import `main.py` types (`Command`, `GameView`, `GameOutput`, `CellView`, `MazeSnapshot`) and `maze.py` types (`Maze`, `Position`, `Direction`, `CellSpec`, `CellKind`). They must **not** import `db.py` directly.

### 7.2 Data Contracts for Maze Canvas

The canvas needs structured per-cell data, not just `map_text`. These dataclasses live in `main.py`:

- `CellView` (dataclass)
  - `row: int`
  - `col: int`
  - `kind: str` — one of `"start"`, `"exit"`, `"normal"`
  - `visible: bool` — `False` when hidden by fog of war
  - `is_player: bool` — `True` for the cell the player occupies
  - `has_gate: bool` — `True` when an unsolved gate is present at this cell
  - `solved: bool` — `True` when the gate at this cell has been solved
  - `connections: list[str]` — open movement directions from this cell (e.g. `["N", "E"]`)

- `MazeSnapshot` (dataclass)
  - `width: int`
  - `height: int`
  - `cells: list[CellView]` — row-major order, exactly `width * height` items

`GameView` gains an optional field:
  - `maze_snapshot: MazeSnapshot | None = None`

Backwards compatibility: defaults to `None`; CLI is unaffected. The engine populates it in `_make_view()`. For small mazes (up to ~9x9) the cost is negligible.

### 7.3 Qt Signal/Slot Contract

These are the mandatory signals and slots each widget must expose for the Controller to wire.

**Team 1 — FormsPanel (QWidget)**

| Direction | Name | Signature | Description |
|---|---|---|---|
| Signal (out) | `command_issued` | `Command` | Any user action translated to a Command |
| Slot (in) | `update_view` | `GameView` | Refresh room info, movement buttons, etc. |
| Slot (in) | `show_messages` | `list[str]` | Display engine feedback messages |

**Team 1 — PuzzleDialog (QWidget)**

| Direction | Name | Signature | Description |
|---|---|---|---|
| Signal (out) | `answer_submitted` | `str` | User's answer text |
| Signal (out) | `hint_requested` | `str` | Hint type chosen (or empty for options) |
| Slot (in) | `show_puzzle` | `dict` | `pending_puzzle` dict or `None` to hide |
| Slot (in) | `show_hint_options` | `list[dict]` | `hint_options` list from `GameOutput` |
| Slot (in) | `show_hint_result` | `str` | Clue text from engine's hint response |

**Team 1 — StatusBar (QWidget)**

| Direction | Name | Signature | Description |
|---|---|---|---|
| Slot (in) | `update_status` | `GameView` | Refresh position, moves, gates, visited |

**Team 1 — ScoreBoard (QWidget)**

| Direction | Name | Signature | Description |
|---|---|---|---|
| Slot (in) | `show_scores` | `list[dict]` | List of score records from `top_scores()` |

**Team 2 — MazeCanvas (QWidget)**

| Direction | Name | Signature | Description |
|---|---|---|---|
| Signal (out) | `direction_clicked` | `str` | `"N"`, `"S"`, `"E"`, `"W"` from click on adjacent cell |
| Slot (in) | `update_maze` | `MazeSnapshot` | Redraw changed cells (diff internally) |
| Slot (in) | `highlight_player` | `tuple[int,int]` | `(row, col)` to animate player position |

**Team 3 — GameController (QObject)**

| Direction | Name | Signature | Description |
|---|---|---|---|
| Signal (out) | `view_changed` | `GameView` | Broadcast after every engine response |
| Signal (out) | `messages_ready` | `list[str]` | Engine messages for display |
| Signal (out) | `game_completed` | `dict` | Score metrics when game ends |
| Slot (in) | `on_command` | `Command` | Receives commands from any widget |

**Team 3 — EngineWorker (QThread)**

| Direction | Name | Signature | Description |
|---|---|---|---|
| Signal (out) | `result_ready` | `GameOutput` | Emitted when `engine.handle()` returns |
| Signal (out) | `error_occurred` | `str` | Emitted on unexpected engine error |
| Slot (in) | `submit_command` | `Command` | Queued from main thread |

### 7.4 Startup / Wiring Sequence

1. `gui_main.py` parses CLI flags (`--size`, `--seed`, `--gates`, `--reset-game`)
2. Creates `repo`, `maze`, `puzzles`, `engine` (same as `cli_main`)
3. Creates `EngineWorker(engine)` in a `QThread`
4. Creates `GameController` and connects it to the worker
5. Creates Team 1 widgets and Team 2 canvas
6. Controller calls `engine.view()` to get initial state, emits `view_changed`
7. All widgets render initial state from the signal

### 7.5 Entry Points

- `python gui_main.py [--size N] [--seed N] [--gates N] [--reset-game]` — standalone GUI
- `python main.py --gui [...]` — launches GUI instead of CLI (delegates to `gui_main`)
