# HANDOFF — Hack the Maze (504-week7)

Last updated: 2026-02-21  
Branch: `feat/gui-canvas` (3 commits ahead of `master`)

---

## Project Overview

A hacker-themed terminal quiz maze game built in Python. Players navigate a network of cybersecurity nodes, answer questions to unlock gates, and race to the exit. The codebase supports both a CLI interface and a PyQt6 graphical interface with an optional Godot 4 first-person 3D renderer.

---

## Architecture

```
main.py  (engine + CLI adapter — the only integration point)
  ├── maze.py      (topology, movement, gate hooks — no IO)
  ├── db.py        (SQLite via SQLModel — no maze/main imports)
  └── puzzles.py   (puzzle catalogue + registry)

gui/                     (PyQt6 graphical layer)
  └── maze_canvas.py     (2D QPainter grid + optional Godot 3D bridge)

godot_maze/              (Godot 4 project — first-person 3D renderer)
```

Hard dependency rule: `maze.py` and `db.py` never import each other or `main.py`. `main.py` wires everything together. The GUI modules only import from `main.py` types.

---

## Branch Topology

| Branch | Status | Contains |
|---|---|---|
| `master` | Stable | Engine, CLI, maze, db, puzzles, all tests through P2 |
| `feat/gui-canvas` | **Current** | `gui/maze_canvas.py`, `godot_maze/`, README updates (3 commits ahead of master) |
| `feat/gui-forms` | Remote | Team 1 widgets: `FormsPanel`, `PuzzleDialog`, `StatusBar`, `ScoreBoard` |
| `feat/gui-controller` | Remote | Team 3: `GameController`, `EngineWorker`, `gui_main.py` |

Per RUNBOOK merge order: Team 3 (controller) merges first, then Teams 1 (forms) and 2 (canvas).

---

## Test Status on `feat/gui-canvas`

```
116 passed, 16 failed
```

All 16 failures are **expected missing-module errors** — the forms and controller code lives on other branches:

| Failing tests | Reason |
|---|---|
| `test_gui_forms.py` (10 tests) | `gui.forms_panel`, `gui.puzzle_dialog`, `gui.status_bar`, `gui.score_board` not on this branch |
| `test_gui_wiring.py` (6 tests) | `gui.controller` not on this branch |

All core tests pass: maze contract, repo contract, engine integration, CLI flags, puzzles, question bank, canvas (F-series), and GUI integration (D-series).

Run tests with:
```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

---

## Key Files

### Source

| File | Purpose |
|---|---|
| `main.py` | `GameEngine` (UI-agnostic), `Command`/`GameView`/`GameOutput`/`CellView`/`MazeSnapshot` types, CLI adapter, startup flags |
| `maze.py` | `Maze`, `Position`, `Direction`, `CellSpec`; `build_minimal_3x3_maze()`, `build_square_maze(size, seed, num_gates)` |
| `db.py` | `SqliteGameRepository`, `open_repo()`, `HACKER_SEED_QUESTIONS`; SQLModel-backed persistence |
| `puzzles.py` | `Puzzle`, `PuzzleRegistry`; 20+ question catalogue with categories and difficulty |
| `gui/maze_canvas.py` | `MazeCanvas` QWidget — QPainter 2D grid + Godot 4 WebSocket 3D bridge; fallback banner |
| `godot_maze/` | Godot 4 project: `ws_client.gd`, `maze_builder.gd`, `player.gd`, `texture_gen.gd`, CRT shader |

### Tests

| File | Series | Requires PyQt6 |
|---|---|---|
| `test_maze_contract.py` | P0 maze | No |
| `test_maze_dynamic.py` | Procedural maze | No |
| `test_repo_contract.py` | P0 repo | No |
| `test_repo_sqlite.py` | SQLite specifics | No |
| `test_question_bank.py` | Seed/fetch/reset | No |
| `test_engine_integration.py` | P0 engine E2E | No |
| `test_engine_unit.py` | Engine unit | No |
| `test_main_cli_flags.py` | CLI flags | No |
| `test_cli_map_visibility.py` | Fog of war | No |
| `test_puzzles.py` | Puzzle contract | No |
| `test_gui_integration.py` | D-series (no Qt) | No |
| `test_gui_canvas.py` | F-series | Yes |
| `test_gui_forms.py` | E-series | Yes |
| `test_gui_wiring.py` | G-series | Yes |

### Documentation

| File | Purpose |
|---|---|
| `interfaces.md` | Module contracts (source of truth) |
| `RUNBOOK.md` | Workflow, merge gates, test backlog, per-module checklists |
| `AGENTS.md` | Contribution rules for humans and AI agents |
| `integration-tests-spec.md` | Detailed test descriptions |
| `planning.md` | Ownership and merge order |
| `README.md` | User-facing setup and gameplay instructions |

---

## What Has Been Completed

### Core (on `master`)
- Deterministic 3x3 maze and procedural `build_square_maze(size, seed, num_gates)`
- SQLite persistence via SQLModel (players, games, scores, question bank)
- UI-agnostic `GameEngine` with movement, puzzle gating, hints, fog of war, status, save
- CLI adapter with `--size`, `--seed`, `--gates`, `--reset-game`, `--gui` flags
- 20+ puzzle questions with categories and difficulty
- Full P0/P1/P2 test coverage

### GUI Canvas (this branch — `feat/gui-canvas`)
- `MazeCanvas` widget with QPainter 2D grid rendering (F-series tests pass)
- Godot 4 WebSocket bridge for first-person 3D rendering
- Godot project skeleton: GridMap maze builder, FPS camera, CRT shader, procedural textures
- Fallback banner showing *why* 3D mode is unavailable
- README with platform-specific Godot install instructions (Linux/macOS/Windows)

### GUI Forms (on `feat/gui-forms`, not merged)
- `FormsPanel`, `PuzzleDialog`, `StatusBar`, `ScoreBoard`

### GUI Controller (on `feat/gui-controller`, not merged)
- `GameController`, `EngineWorker`, `gui_main.py`

---

## What Remains

### Immediate (to get `--gui` working end-to-end)

1. **Merge GUI branches in order** (per RUNBOOK §Merge Order):
   - `feat/gui-controller` → master (adds `gui_main.py`, `gui/controller.py`, `gui/engine_worker.py`)
   - `feat/gui-forms` → master (adds form widgets)
   - `feat/gui-canvas` → master (adds `gui/maze_canvas.py` + Godot project)
   - Run G-series wiring tests after all three are merged

2. **Resolve 16 failing tests** — these will auto-resolve once all GUI branches are merged

3. **Godot testing** — the Godot 3D renderer has not been tested live (Godot is not installed on the dev server). Needs manual validation on a machine with Godot 4.2+ and a display.

### Short-term

4. **Add CI** — tests are currently run manually with evidence pasted into PRs. RUNBOOK notes this gap.
5. **DB migration path** — `schema_version` is fixed at 1; no migration strategy exists yet.
6. **Untracked screenshot files** — `gui_preview_*.png` and `gui_real_*.png` should be committed or `.gitignore`'d.

### Medium-term

7. **Multiplayer/networking** — explicitly a non-goal for this phase (per RUNBOOK).
8. **Performance/load testing** — also a non-goal for this phase.
9. **Content expansion** — more puzzles, larger default mazes, additional themes.

---

## How to Run

### CLI
```bash
pip install -r requirements.txt
python main.py                              # default 3x3 maze
python main.py --size 7 --seed 42 --gates 3 # custom maze
```

### GUI (requires all GUI branches merged)
```bash
python main.py --gui
python main.py --gui --no-godot             # force 2D fallback
```

### Tests
```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

---

## Dependencies

```
sqlmodel>=0.0.22    # SQLite ORM
pytest>=8.0         # test runner
PyQt6>=6.6          # GUI framework
pytest-qt>=4.4      # Qt test fixtures
websockets>=12.0    # Godot bridge (only needed for 3D mode)
```

Optional: Godot 4.2+ on PATH for 3D first-person view.

---

## Key Design Decisions

1. **Engine is UI-agnostic** — `GameEngine` never calls `print()` or `input()`. CLI and GUI are adapters.
2. **DB stores JSON-safe primitives only** — positions are `{"row": int, "col": int}`, timestamps are ISO-8601 UTC strings.
3. **No cross-imports** — enforced by tests and code review; `main.py` is the sole integration point.
4. **Shared integration tests are the contract** — if it's not tested, it's not promised.
5. **Godot is optional** — the GUI degrades gracefully to a 2D QPainter grid with a visible explanation.

---

## Governing Documents (in priority order)

1. `interfaces.md` — module contracts (wins on conflict)
2. `RUNBOOK.md` — workflow, merge gates, test backlog
3. `AGENTS.md` — contribution rules for developers and AI agents
