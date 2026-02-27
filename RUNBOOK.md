# RUNBOOK — Quiz Maze Walking Skeleton

This runbook is the day-to-day operational guide for developing the quiz maze walking skeleton in parallel, while keeping a playable mini-game and preserving clean module boundaries.

Source-of-truth docs:
- `interfaces.md` (module contracts)
- `integration-tests-spec.md` (detailed test descriptions)
- `planning.md` (ownership + merge order)
- `customization-design-plan.md` (theme + growth roadmap)
- `AGENTS.md` (agent-focused contribution rules)

## Purpose (and Non-Goals)

**Purpose**: enable multiple developers/agents to implement `maze.py`, `db.py`, `main.py`, and the PyQt GUI layer independently, with shared integration tests acting as the executable contract.
**Non-goals for this phase**: performance/load testing, multiplayer/networking.

## Module Ownership and Boundaries

Hard dependency rule (do not violate):
- `maze.py` imports nothing from `db.py` or `main.py`
- `db.py` imports nothing from `maze.py` or `main.py`
- `main.py` is the only integration point

Responsibilities:
- **`maze.py` (Maze Owner)**: deterministic maze factory + topology/movement API + gate/puzzle hooks (no puzzle logic).
- **`db.py` (DB Owner)**: SQLite-backed repository via SQLModel, storing JSON-safe primitives only.
- **`main.py` (Engine/CLI Owner)**: UI-agnostic engine + CLI adapter; uses `Maze` + repository + puzzle registry.
- **`gui/` (GUI Teams 1-3)**: PyQt6 graphical interface; see `interfaces.md` §7 for contracts.
  - **Team 1 (UI/UX)**: `gui/forms_panel.py`, `gui/puzzle_dialog.py`, `gui/status_bar.py`, `gui/score_board.py`
  - **Team 2 (Canvas)**: `gui/maze_canvas.py`
  - **Team 3 (Controller)**: `gui/controller.py`, `gui/engine_worker.py`, `gui_main.py`

## Workflow and Branching

Baseline branch:
- `planning` is the baseline for contracts and planning docs.

Feature branches (recommended standard):
- `feat/<area>-<short-description>` (new behavior)
- `fix/<area>-<short-description>` (bug fixes)
- `docs/<short-description>` (docs-only changes)
- `test/<short-description>` (tests-only changes)
- `refactor/<area>-<short-description>` (refactors without behavior change)

Areas (pick one):
- `maze`, `db`, `engine`, `cli`, `puzzles`, `gui-forms`, `gui-canvas`, `gui-controller`, `docs`, `tests`

Examples:
- `feat/maze-minimal-3x3`
- `feat/db-json-repo`
- `feat/engine-command-parser`
- `docs/runbook-updates`

Merge order:
1. Maze contract work can merge once Maze P0 tests pass.
2. DB contract work can merge once Repo P0 tests pass.
3. Engine/CLI merges once Maze+DB contracts are stable and Engine P0 tests pass.
4. GUI Team 3 (Controller) merges first among GUI branches (adds `MazeSnapshot` to `main.py`, `--gui` flag).
5. GUI Teams 1 (Forms) and 2 (Canvas) merge after Team 3 (they only add files in `gui/`).
6. Integration branch runs G-series wiring tests to validate full GUI.

## Merge Gate (Must Pass)

Every PR must pass:
- **Module unit tests** for the changed component(s)
- **Shared integration tests** (see backlog below)
- **Interface compatibility**: no contract drift vs `interfaces.md` unless explicitly updated (and reviewed)

No CI runner is configured yet. This means the PR author is responsible for running tests locally and reporting results in the PR description.
This manual test gate is part of the current `master` baseline and should not be removed by feature branches.

Recommended local commands (to include in PR):
- `python -m pytest -q`
- (optional during development) `python -m pytest -q tests/test_maze_contract.py`

Required PR evidence (until CI exists):
- Paste command(s) run and the final pass/fail summary.
- Confirm whether all P0 tests passed.
- If any test was skipped, explain why and link follow-up work.

## Shared Integration Test Backlog (Priority Ordered)

Test file targets:
- `tests/test_maze_contract.py`
- `tests/test_repo_contract.py`
- `tests/test_engine_integration.py`

### P0 — Critical Path (must pass before any feature merges)

Maze contract (`tests/test_maze_contract.py`):
- `test_minimal_maze_start_exit_in_bounds`
- `test_available_moves_match_next_pos`
- `test_exit_reachable_from_start_via_public_api`
- `test_gate_and_puzzle_hooks_are_stable`

Repository contract (`tests/test_repo_contract.py`):
- `test_json_schema_root_keys_exist`
- `test_get_or_create_player_is_idempotent`
- `test_create_and_get_game_round_trip`
- `test_save_game_updates_state_and_status`
- `test_record_score_and_top_scores_ordering`

Engine end-to-end (`tests/test_engine_integration.py`):
- `test_new_game_view_has_valid_position_and_moves`
- `test_player_can_progress_after_solving_required_puzzle`
- `test_reaching_exit_completes_game_and_records_score`

Definition of “P0 done”:
- P0 tests pass on every branch, without test-only shortcuts that violate `interfaces.md`.
- Running `main.py` provides a playable 3x3 mini-game (move, solve at least one gate puzzle, reach exit, persist score).

### P1 — Contract Hardening (merge when ready; required before expanding scope)

Engine robustness (`tests/test_engine_integration.py`):
- `test_save_command_persists_progress_mid_run`
- `test_invalid_command_does_not_corrupt_state`

Repository semantics (extend `tests/test_repo_contract.py` as needed):
- Confirm `updated_at` monotonicity for repeated `save_game` calls
- Validate score ordering ties (secondary key: lowest `moves`)

### P2 — Expansion-Ready (protect future SQLite + PyQt work)

DB portability:
- Re-run the same repo contract suite against a future `SqliteGameRepository` implementation (no behavior drift).

Engine UI-agnostic guarantees:
- Ensure the engine returns a stable `GameView` that can render in both CLI and PyQt without accessing internal engine state.

### P3 — PyQt GUI (parallel team development)

GUI contract tests (`tests/test_gui_integration.py`) — no PyQt dependency:
- D.1 `test_maze_snapshot_matches_game_view`
- D.2 `test_maze_snapshot_updates_after_movement`
- D.3 `test_maze_snapshot_gate_status_reflects_solved`
- D.4 `test_cell_view_kind_matches_maze_cell_kind`
- D.5 `test_cell_view_connections_only_on_visible_cells`

Forms panel tests (`tests/test_gui_forms.py`) — requires `pytest-qt`:
- E.1–E.10: direction buttons, answer submit, hint options, movement enable/disable,
  puzzle show/hide, status bar, score board, completion screen

Canvas tests (`tests/test_gui_canvas.py`) — requires `pytest-qt`:
- F.1–F.8: cell count, fog styling, player highlight, gate markers,
  connections, click-to-move, partial redraw, variable sizes

Wiring tests (`tests/test_gui_wiring.py`) — requires `pytest-qt`:
- G.1–G.6: startup view, direction click propagation, puzzle flow,
  hint flow, game completion signal, save indicator

## Per-Module Implementation Checklists (Tied to Shared Tests)

Each checklist item must be satisfied *and* the referenced tests must pass.

### Maze Owner Checklist (`maze.py`)

- [ ] Implement `build_minimal_3x3_maze()` deterministic factory.
  - **Verify**: `tests/test_maze_contract.py::test_minimal_maze_start_exit_in_bounds`
- [ ] Implement movement topology methods: `in_bounds`, `available_moves`, `next_pos`.
  - **Verify**: `tests/test_maze_contract.py::test_available_moves_match_next_pos`
- [ ] Ensure exit is reachable via public API (no hidden shortcuts).
  - **Verify**: `tests/test_maze_contract.py::test_exit_reachable_from_start_via_public_api`
- [ ] Provide stable hooks: `puzzle_id_at(pos)` and `gate_id_for(pos, dir)`.
  - **Verify**: `tests/test_maze_contract.py::test_gate_and_puzzle_hooks_are_stable`

Done when:
- All Maze P0 tests pass and the module has no imports of `db.py`/`main.py`.

### DB Owner Checklist (`db.py`)

- [ ] Implement JSON schema bootstrap (`schema_version`, `players`, `games`, `scores`).
  - **Verify**: `tests/test_repo_contract.py::test_json_schema_root_keys_exist`
- [ ] Implement `get_or_create_player(handle)` idempotently.
  - **Verify**: `tests/test_repo_contract.py::test_get_or_create_player_is_idempotent`
- [ ] Implement game lifecycle: `create_game`, `get_game`, `save_game`.
  - **Verify**: `tests/test_repo_contract.py::test_create_and_get_game_round_trip`, `tests/test_repo_contract.py::test_save_game_updates_state_and_status`
- [ ] Implement scoring: `record_score`, `top_scores` ordered by lowest `elapsed_seconds`, then lowest `moves`.
  - **Verify**: `tests/test_repo_contract.py::test_record_score_and_top_scores_ordering`

Done when:
- All Repo P0 tests pass using only JSON-safe primitives, and `db.py` does not import `maze.py`/`main.py`.

### Engine/CLI Owner Checklist (`main.py`)

- [ ] Create an engine that is UI-agnostic (no direct I/O in core logic) and returns `GameView`.
  - **Verify**: `tests/test_engine_integration.py::test_new_game_view_has_valid_position_and_moves`
- [ ] Implement puzzle gating flow: pending puzzle appears, `answer` resolves, movement retries succeed.
  - **Verify**: `tests/test_engine_integration.py::test_player_can_progress_after_solving_required_puzzle`
- [ ] Implement completion flow: reaching exit marks game completed and records score.
  - **Verify**: `tests/test_engine_integration.py::test_reaching_exit_completes_game_and_records_score`
- [ ] Add `save` command persistence and invalid command safety.
  - **Verify**: P1 engine tests (`test_save_command_persists_progress_mid_run`, `test_invalid_command_does_not_corrupt_state`)

Done when:
- All Engine P0 tests pass and `main.py` runs a playable mini-game via CLI.

### GUI Team 1 (UI/UX Forms) Checklist (`gui/forms_panel.py`, `gui/puzzle_dialog.py`, `gui/status_bar.py`, `gui/score_board.py`)

- [ ] `FormsPanel` with N/S/E/W buttons emitting `command_issued(Command)`.
  - **Verify**: `tests/test_gui_forms.py::test_direction_buttons_emit_correct_commands`
- [ ] Movement buttons disable when direction unavailable.
  - **Verify**: `tests/test_gui_forms.py::test_movement_buttons_disabled_when_unavailable`
- [ ] `PuzzleDialog` with answer input and submit button emitting `answer_submitted(str)`.
  - **Verify**: `tests/test_gui_forms.py::test_answer_submit_emits_command`
- [ ] Hint options render as buttons, emit `hint_requested(str)`.
  - **Verify**: `tests/test_gui_forms.py::test_hint_options_render_as_buttons`, `test_hint_button_emits_hint_command`
- [ ] Puzzle panel show/hide via `show_puzzle(dict | None)`.
  - **Verify**: `tests/test_gui_forms.py::test_puzzle_panel_hidden_when_no_puzzle`, `test_puzzle_panel_shows_prompt`
- [ ] `StatusBar` displays position, moves, visited count.
  - **Verify**: `tests/test_gui_forms.py::test_status_bar_displays_all_fields`
- [ ] `ScoreBoard` renders score rows.
  - **Verify**: `tests/test_gui_forms.py::test_score_board_renders_rows`
- [ ] Completion overlay when `is_complete=True`.
  - **Verify**: `tests/test_gui_forms.py::test_completion_screen_shown`

Done when:
- All E-series tests pass with dummy data (no engine required).

### GUI Team 2 (Canvas) Checklist (`gui/maze_canvas.py`)

- [ ] Canvas renders correct cell count from `MazeSnapshot`.
  - **Verify**: `tests/test_gui_canvas.py::test_canvas_renders_correct_cell_count`
- [ ] Fog cells visually distinct from visible cells.
  - **Verify**: `tests/test_gui_canvas.py::test_fog_cells_rendered_differently`
- [ ] Player cell has visual indicator.
  - **Verify**: `tests/test_gui_canvas.py::test_player_cell_highlighted`
- [ ] Gate cells marked visually.
  - **Verify**: `tests/test_gui_canvas.py::test_gate_cell_marked`
- [ ] Connections/corridors drawn between cells.
  - **Verify**: `tests/test_gui_canvas.py::test_connections_drawn`
- [ ] Click on adjacent cell emits `direction_clicked(str)`.
  - **Verify**: `tests/test_gui_canvas.py::test_click_adjacent_cell_emits_direction`
- [ ] Partial redraw on incremental updates.
  - **Verify**: `tests/test_gui_canvas.py::test_update_redraws_only_changed_cells`
- [ ] Handles 3x3, 5x5, 7x7 snapshots.
  - **Verify**: `tests/test_gui_canvas.py::test_canvas_handles_variable_sizes`

Done when:
- All F-series tests pass with hardcoded `MazeSnapshot` data (no engine required).

### GUI Team 3 (Controller) Checklist (`gui/controller.py`, `gui/engine_worker.py`, `gui_main.py`)

- [ ] `GameController` broadcasts `view_changed` on startup.
  - **Verify**: `tests/test_gui_wiring.py::test_gui_startup_shows_initial_view`
- [ ] Direction commands propagate through Controller to engine and back to widgets.
  - **Verify**: `tests/test_gui_wiring.py::test_direction_click_updates_both_panels`
- [ ] Puzzle flow: gate -> puzzle dialog -> answer -> clear.
  - **Verify**: `tests/test_gui_wiring.py::test_puzzle_flow_through_gui`
- [ ] Hint flow: bare hint -> options -> typed hint -> clue.
  - **Verify**: `tests/test_gui_wiring.py::test_hint_flow_through_gui`
- [ ] Game completion emits `game_completed` signal.
  - **Verify**: `tests/test_gui_wiring.py::test_game_completion_shows_score`
- [ ] `MazeSnapshot` populated in every `GameView`.
  - **Verify**: `tests/test_gui_integration.py::test_maze_snapshot_matches_game_view`
- [ ] `--gui` flag in `_parse_startup_flags`.
  - **Verify**: `tests/test_main_cli_flags.py::test_parse_startup_flags_gui_flag`

Done when:
- All D-series and G-series tests pass.
- `python main.py --gui` launches the PyQt window.

## Execution Sequence (Recommended)

1) **Maze Owner** implements Maze P0 until `tests/test_maze_contract.py` passes.
2) **DB Owner** implements Repo P0 until `tests/test_repo_contract.py` passes.
3) **Engine/CLI Owner** implements Engine P0 end-to-end until `tests/test_engine_integration.py` passes.
4) Implement P1 hardening (save + invalid command), then start content expansion (more puzzles/mazes).

