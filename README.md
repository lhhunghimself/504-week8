# Hack the Maze — A Python Puzzle Adventure

A hacker-themed terminal quiz maze game. Navigate a network of cybersecurity nodes, answer Python and security questions to unlock gates, and race to reach root access.

---

## Requirements

- Python 3.10+
- Install dependencies:

```bash
pip install -r requirements.txt
```

`requirements.txt` installs `sqlmodel` (SQLite ORM) and `pytest`.

---

## Running the Game

```bash
python main.py
```

On first launch you will be prompted for a hacker handle. Progress is saved automatically to `game_save.db` in the current directory. Each subsequent launch resumes where you left off — including which questions you have already been asked.

### Custom Maze Size

Generate larger mazes with more gates using CLI flags:

```bash
python main.py --size 7 --seed 42 --gates 3
```

| Flag | Default | Description |
|---|---|---|
| `--size N` | `3` | Width/height of the square maze (minimum 3) |
| `--seed N` | `0` | Random seed for procedural generation (0 = default) |
| `--gates N` | `1` | Number of puzzle gates placed along the path (minimum 1) |

When `--size 3 --seed 0 --gates 1` (all defaults), the hand-authored 3x3 maze is used. Any non-default value triggers procedural generation via `build_square_maze`. The same seed always produces the same maze layout.

Flags can be combined freely:

```bash
python main.py --size 5 --gates 2 --reset-game
```

### Graphical UI (PyQt6)

Launch the PyQt6 GUI instead of the terminal interface:

```bash
python main.py --gui
python main.py --gui --size 5 --gates 2
```

Requires `PyQt6` to be installed. Falls back to CLI mode if unavailable.

### 3D Maze Renderer (Godot 4)

When Godot 4 is installed, the GUI launches a separate first-person 3D window (Doom/Duke Nukem style) alongside the PyQt forms. The two processes communicate via WebSocket.

**Setup:**

1. Install [Godot 4.2+](https://godotengine.org/download) and ensure `godot` is on your PATH
2. The Godot project lives in `godot_maze/` — no manual setup needed

**Usage:**

```bash
python main.py --gui                    # 3D maze + PyQt forms
python main.py --gui --no-godot         # PyQt only (2D grid fallback)
```

If Godot is not installed, the canvas automatically falls back to the 2D QPainter grid.

**Controls in the 3D window:**

| Key | Action |
|---|---|
| W / Up | Move forward |
| S / Down | Move backward |
| A | Strafe left |
| D | Strafe right |
| Q / Left | Turn left 90 degrees |
| E / Right | Turn right 90 degrees |

Movement is grid-locked (one cell at a time) with smooth tween interpolation.

### Reset the question bank

To mark all questions as unasked again (e.g. start a fresh challenge with the same player record):

```bash
python main.py --reset-game
```

---

## How to Play

### Objective

You start at the **Ingress Port** (top-left of the network grid). Reach the **Root Access Gateway** (bottom-right) to win. The default maze is 3x3, but you can generate larger grids with `--size`. Your score is based on elapsed time, number of moves, and hints used.

### The Map

The maze uses **fog of war** by default. Cells you have not yet visited are hidden (`###`). Move into a cell to reveal it.

```
 @ --###  ###      ← @ = you, ### = unexplored, S = start, X = exit
 |
###  ###  ###
```

### Movement

| Command | Effect |
|---|---|
| `n` / `s` / `e` / `w` | Move north / south / east / west |
| `go north` (or `go n`) | Same as above |

Some edges are **gated** — moving into them triggers a puzzle challenge. You cannot pass until you answer correctly.

### Puzzles and Gates

When you hit a gate, a challenge appears:

```
>> PUZZLE: Firewall Lattice — Intrusion Counter
The firewall's intrusion counter scans each packet in a list
before deciding whether to trigger the alarm.

  What built-in function returns the number of items in a list?
  (one word)
  Use: answer <your answer>  |  hint (for hint options)
```

Answer with:

```
answer len
```

Questions are drawn from a 27-question hacker-themed bank covering four categories:

| Category | Topics |
|---|---|
| `python` | keywords, data structures, control flow, builtins |
| `security` | ports, protocols, hashing, network recon |
| `output` | "what does this print?" Python snippets |
| `debugging` | tracebacks and error types |

Once you have answered a question it will not be repeated in the same session (or across restarts unless `--reset-game` is used).

### Hints

When a puzzle is pending, type `hint` to see your options:

```
> hint

  1. First letter of the answer (-1pt)
  2. Character count of the answer (-1pt)
  3. Question category (-1pt)
  4. Progressive character reveal (-2pt)

  Choose hint type (number or name, Enter to cancel):
```

Then enter a number or type name (e.g. `1` or `letter`). Each hint type has a cost that is added to your `hints_used` metric and recorded in your score.

| Hint type | What you get | Cost |
|---|---|---|
| `letter` | First letter of the answer | 1 pt |
| `count` | Character count of the answer | 1 pt |
| `category` | Question category | 1 pt |
| `reveal` | Progressive character-by-character reveal (one more char per use) | 2 pt |

Press Enter at the hint menu to cancel without using a hint.

### Other Commands

| Command | Effect |
|---|---|
| `look` | Re-describe the current cell |
| `map` | Redraw the fog-of-war map |
| `status` | Show position, moves, gates solved, hints used, exploration % |
| `save` | Explicitly save progress (also auto-saved on movement and puzzle solve) |
| `scores` | Show top 5 scores for this maze |
| `help` | Show command reference |
| `quit` | Save and exit |

### Scoring

When you reach the exit a score is recorded with:

- `elapsed_seconds` — wall-clock time from game start
- `moves` — total movement commands
- `puzzles_solved` — gates cleared
- `hints_used` — total hint cost consumed

Scores are sorted by lowest `elapsed_seconds` then lowest `moves`. Use `scores` to view the leaderboard.

---

## Project Structure

| File | Purpose |
|---|---|
| `main.py` | Game engine + CLI adapter |
| `maze.py` | Maze domain model and factories |
| `db.py` | SQLite persistence via SQLModel |
| `puzzles.py` | Puzzle registry (16 gate-specific puzzles + fallback) |
| `gui/` | PyQt6 GUI (forms, canvas, controller) — in development |
| `gui_main.py` | GUI entry point |
| `godot_maze/` | Godot 4 first-person 3D maze renderer project |
| `interfaces.md` | Module contracts (stable API between all modules) |
| `tests/` | 110+ unit and integration tests (26 GUI tests skip without PyQt6) |

---

## Running Tests

```bash
python -m pytest -q
```

Core tests (105) should pass. GUI widget tests (26) are skipped when PyQt6 is not installed.

---

## Architecture Notes

- `maze.py` and `db.py` have **no cross-imports** — `main.py` is the only integration point.
- The engine is **UI-agnostic**: `GameEngine.handle(Command)` returns a `GameOutput` dataclass. The CLI is one adapter; the PyQt GUI (launched with `--gui`) is another. The optional Godot 3D renderer runs as a separate process communicating via WebSocket — it receives `MazeSnapshot` JSON and sends direction commands back.
- Persistence uses **SQLite via SQLModel**. Game state, scores, and the question bank are all stored in `game_save.db`.
- Fog of war is tracked via a `visited` set in persisted game state — no maze logic changes required.
- Maze generation is deterministic given a seed. `build_square_maze(size, seed, num_gates)` uses a seeded RNG to carve a spanning tree and place gates on the solution path.
- The question bank deduplicates on restart: reseeding refreshes question text but preserves `has_been_asked` flags. Pass `--reset-game` to clear them.
