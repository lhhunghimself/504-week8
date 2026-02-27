# Engine/CLI Team — RUNBOOK Delta

Additions and updates to `RUNBOOK.md` owned by the Engine/CLI team.
Target merge: after `feat/engine-upgrades` lands on `master`.

---

## Updates to "Module Ownership and Boundaries"

Update the `main.py` responsibilities line to:

> **`main.py` (Engine/CLI Owner)**: UI-agnostic game engine + CLI adapter.
> Engine returns `GameView` and `GameOutput` — the stable boundary for both CLI and PyQt.
> CLI adapter (`cli_main()`) is the only thing that changes during a PyQt migration.

---

## Updates to "DB Owner Checklist"

Replace the JSON-specific checklist items with:

- [x] Implement `SqliteGameRepository` via SQLModel (tables: players, games, scores, questions).
- [x] `open_repo(path)` always returns `SqliteGameRepository`; creates DB if not exists.
- [x] `seed_questions` is idempotent (merge, not insert).
- [x] Question bank: `get_random_question`, `mark_question_asked`, `reset_questions`.
- [x] All B.1–B.9 repo contract tests pass.

---

## Updates to "Engine/CLI Owner Checklist"

Replace existing checklist with:

### P0 — Core game loop (must pass before merge)

- [x] `GameEngine` returns stable `GameView` on every `view()` and `handle()` call.
  - Verify: `test_new_game_view_has_valid_position_and_moves`
- [x] Puzzle gating: pending puzzle appears on gated move, `answer` resolves it.
  - Verify: `test_player_can_progress_after_solving_required_puzzle`
- [x] Completion: reaching exit marks game completed and records score.
  - Verify: `test_reaching_exit_completes_game_and_records_score`
- [x] `save` command persists mid-run progress.
  - Verify: `test_save_command_persists_progress_mid_run`
- [x] Invalid commands do not corrupt state.
  - Verify: `test_invalid_command_does_not_corrupt_state`

### P1 — Engine upgrades (this branch: feat/engine-upgrades)

- [x] `GameView.map_text` always populated (fog-of-war, never None).
  - Verify: `test_view_always_includes_map_text_and_visited_count`
  - Verify: `test_fog_of_war_is_default_in_engine_map`
- [x] `GameView.visited_count` always populated.
  - Verify: `test_view_always_includes_map_text_and_visited_count`
- [x] `hint` command (two-step: bare returns `hint_options`; `hint <type>` delivers clue).
  - Verify: `test_hint_command_provides_clue_and_increments_count`
  - Verify: `test_hint_without_pending_puzzle_is_safe`
- [x] `status` command returns position, moves, gates, hints, exploration info.
  - Verify: `test_status_command_returns_progress_info`
- [x] `hints_used` persisted in state dict.
  - Verify: `test_new_state_keys_persisted_on_save`
  - Verify: `test_backwards_compatible_state_load`
- [x] `hints_used` included in score metrics.
  - Verify: `test_hints_included_in_score_metrics`
  - Verify: `test_completed_score_contains_elapsed_seconds_and_moves`
- [x] Fog-of-war map reveals cells after movement.
  - Verify: `test_fog_of_war_map_reveals_cells_after_movement`
- [x] New state keys (`maze_size`, `num_gates`, `maze_seed`) persisted and loaded with defaults.
  - Verify: `test_new_state_keys_persisted_on_save`
  - Verify: `test_backwards_compatible_state_load`
- [x] CLI `cli_main()` uses `HACKER_SEED_QUESTIONS` from `db.py` (not inline questions).

### P2 — Robustness and coverage (review fixes)

- [x] `maze_size` legacy default hardcoded to `3` per contract (not `maze.width`).
  - Verify: `test_legacy_maze_size_defaults_to_contract_value` (C.21)
- [x] Hint generation uses `hint_answer` contract extension (no private attr access).
  - Verify: `test_hint_with_contract_only_puzzle` (C.22)
- [x] Hybrid fail policy: fail-soft on missing `hint_answer`, fail-loud on registry errors.
  - See ADR-006 in `decisions.md`.
- [x] `hint_options` shape validated (type/label/cost keys and types).
  - Verify: `test_hint_options_contain_required_keys` (C.17)
- [x] Invalid hint type does not change state.
  - Verify: `test_hint_invalid_type_returns_error_no_state_change` (C.18)
- [x] Hint without pending puzzle does not change `hints_used`.
  - Verify: `test_hint_no_puzzle_does_not_change_hints_used` (C.19)
- [x] Different hint types apply correct cumulative costs.
  - Verify: `test_hint_types_apply_correct_costs` (C.20)
- [x] Bare hint does not persist; typed hint does persist.
  - Verify: `test_hint_persist_semantics` (C.23)
- [x] Progressive reveal depth increases and resets on new gate (deterministic 2-gate maze).
  - Verify: `test_progressive_reveal_and_reset` (C.24)

---

## New section: "PyQt Migration Boundary"

When Milestone D (PyQt tile client) begins, the engine requires **zero changes** for a
basic port. The migration scope is:

1. **Replace `cli_main()`** with a PyQt `QMainWindow` that:
   - Calls `engine.view()` on startup to get initial `GameView`.
   - Renders `GameView` fields as tiles/widgets (see ADR-002 in `decisions.md`).
   - Connects directional buttons to `Command(verb="go", args=[dir])`.
   - Connects answer input to `Command(verb="answer", args=[text])`.
   - Reads `GameOutput.hint_options` and renders as buttons in the puzzle dialog.
   - On button click issues `Command(verb="hint", args=[chosen_type])`.

2. **Keep `GameEngine`, `GameView`, `GameOutput`, `Command`** unchanged.

3. **Keep `db.py`** unchanged — `open_repo()` and repository methods are already Qt-compatible.

4. **Keep `maze.py`** unchanged.

Migration test gate:
- All existing engine integration tests must still pass with the Qt adapter (they test
  the engine directly, not the CLI, so they are UI-agnostic by design).
- Add Qt-specific tests only for the rendering layer (`QMainWindow` widget state).

Refer to `docs/teams/engine-cli/decisions.md` ADR-002 for the full field mapping
between `GameView`/`GameOutput` and Qt widgets.

---

## Updates to "P0 test list"

Replace old P0 list with:

**Maze contract** (`tests/test_maze_contract.py`):
- `test_minimal_maze_start_exit_in_bounds`
- `test_available_moves_match_next_pos`
- `test_exit_reachable_from_start_via_public_api`
- `test_gate_and_puzzle_hooks_are_stable`

**Repository contract** (`tests/test_repo_contract.py`):
- `test_get_or_create_player_is_idempotent`
- `test_create_and_get_game_round_trip`
- `test_save_game_updates_state_and_status`
- `test_record_score_and_top_scores_ordering`
- `test_open_repo_creates_database`
- `test_question_bank_lifecycle`
- `test_seed_questions_is_idempotent`
- `test_get_player_returns_none_for_unknown_id`
- `test_get_game_returns_none_for_unknown_id`

**Engine end-to-end** (`tests/test_engine_integration.py`):
- C.1–C.16: core engine flow (see `integration-tests-spec.md` for descriptions).
- C.17–C.24: hint robustness and coverage (see `interfaces-delta.md` for test table).
