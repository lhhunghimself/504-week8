# Engine/CLI Team — interfaces.md Delta

Scope: additions and changes to `interfaces.md` owned by the Engine/CLI team.
Target merge: after `feat/engine-upgrades` lands on `master`.

---

## §5.1 Game State — new persisted keys

Add to the persisted keys list:

```
- hints_used: int     — number of hints consumed (affects scoring)
- maze_size: int      — side length of the generated maze (needed to reconstruct on load)
- num_gates: int      — number of gates placed (needed to reconstruct on load)
- maze_seed: int      — seed used to generate the maze (needed to reconstruct on load)
```

Add to backwards-compatible load defaults:

```
- hints_used:  0
- maze_size:   3  (matches build_minimal_3x3_maze)
- num_gates:   1
- maze_seed:   0
```

Note on `hints_used` and scoring: each hint type carries a cost (see §5.5). The total
`hints_used` count is recorded in score metrics and can be used by leaderboard logic to
apply a penalty or secondary sort.

---

## §5.3 GameView — new fields

Add to `GameView`:

```
- map_text: str          — pre-rendered fog-of-war ASCII map; always populated (never None)
- visited_count: int     — number of distinct cells the player has entered
```

Remove the old definition `map_text: str | None = None`.

The engine populates both fields on every `view()` call and every `handle()` return.
`map_text` is produced by `_render_map(maze, pos, visited, reveal_all=False)`.
`visited_count` is `len(self._visited)`.

---

## §5.3 GameOutput — new field

Add to `GameOutput`:

```
- hint_options: list[dict] | None = None
```

Each dict in `hint_options` has the shape:

```python
{
    "type": str,    # one of: "letter", "count", "category", "reveal"
    "label": str,   # human-readable description shown by the UI
    "cost": int,    # hints_used increment if this type is chosen
}
```

`hint_options` is only non-None when:
- `verb == "hint"` AND
- `args` is empty (no type chosen yet) AND
- a puzzle is currently pending

In all other cases `hint_options` is `None`.

---

## §5.4 CLI rendering — default parameter change

Change `_render_map` signature from:

```python
_render_map(maze, pos, visited, reveal_all: bool = True) -> str
```

to:

```python
_render_map(maze, pos, visited: set[Position], reveal_all: bool = False) -> str
```

`reveal_all=True` is for debug/testing only. All production call sites use the default.

---

## §5.5 CLI command grammar — hint verb

Replace the single `hint` line with:

```
- hint
    Step 1 (no args): engine returns hint_options in GameOutput; hints_used NOT incremented.
    Step 2 (hint <type>): engine delivers the clue, increments hints_used by the type's cost, persists.

    Types and costs:
      hint letter    — reveals first letter of correct answer              (cost: 1)
      hint count     — reveals character count of correct answer           (cost: 1)
      hint category  — reveals the question category                       (cost: 1)
      hint reveal    — progressive character reveal (one more char each use)(cost: 2)

    If no puzzle is pending: returns an info message, no state change, hint_options=None.
```

UI contract:
- CLI: when `hint_options` is non-None, prints numbered menu and reads one more input line,
  then issues `Command(verb="hint", args=[chosen_type])`.
- PyQt: renders `hint_options` as a row of buttons; button click issues the same Command.
- Neither UI needs any engine changes to implement this — the boundary is `hint_options`.

---

## §5.5 CLI command grammar — hint error handling

Invalid hint type: returns error message, `hints_used` is not incremented, `did_persist=False`.
Hint without pending puzzle (bare or typed): returns info message, no state change.

---

## §5.5 Hint generation — `hint_answer` contract extension

The engine uses the correct answer to produce meaningful hints (first letter, count, reveal).
Answer resolution follows a hybrid policy (see ADR-006 in `decisions.md`):

**For DB questions:** `correct_answer` is always available from the question dict.

**For registry puzzles:** The engine calls `getattr(puzzle, "hint_answer", None)`:
- If the puzzle provides `hint_answer: str` (a `@property` or field), the engine uses it
  for specific hints.
- If `hint_answer` is absent, the engine produces generic clues with `"?"` placeholders.
  Gameplay continues — hints degrade gracefully.

`hint_answer` is an **optional** extension to the puzzle contract. The only *required*
puzzle interface remains: `id`, `title`, `prompt`, `check(answer, state) -> bool`.

Registry errors (e.g. `puzzles.get(gate_id)` raises) propagate as-is — they are not
suppressed. This ensures integration bugs surface in tests and logs.

---

## §5.5 Hint reveal — progressive counter is ephemeral

The `hint reveal` counter tracks how many characters have been unmasked for the current
gate. This counter is **not persisted** — it lives only in engine memory and resets on:
- Engine instantiation (including save/reload)
- Puzzle solve (counter is cleared for the solved gate)

`hints_used` cost is still correctly accumulated from persisted state, so scoring is
unaffected by counter resets. See ADR-005 in `decisions.md` for rationale.

---

## Test coverage — C.17 through C.24

New integration tests added to `tests/test_engine_integration.py`:

| ID | Test name | What it validates |
|---|---|---|
| C.17 | `test_hint_options_contain_required_keys` | `hint_options` dicts have `type`, `label`, `cost` with correct types |
| C.18 | `test_hint_invalid_type_returns_error_no_state_change` | Invalid hint type → error message, `hints_used` unchanged |
| C.19 | `test_hint_no_puzzle_does_not_change_hints_used` | Hint (bare and typed) without pending puzzle → no state change |
| C.20 | `test_hint_types_apply_correct_costs` | letter=1, reveal=2, count=1 cumulative cost tracking |
| C.21 | `test_legacy_maze_size_defaults_to_contract_value` | Legacy state without `maze_size` defaults to `3` (not maze.width) |
| C.22 | `test_hint_with_contract_only_puzzle` | Contract-only puzzle (no `hint_answer`) → generic hints, no crash |
| C.23 | `test_hint_persist_semantics` | Bare hint: `did_persist=False`; hint type: `did_persist=True` |
| C.24 | `test_progressive_reveal_and_reset` | Reveal depth increases on same gate; resets to level 1 on new gate |

C.24 uses a deterministic 2-gate 5×5 maze and validates reset via reveal-depth parsing,
not hardcoded gate IDs or exact clue text.
