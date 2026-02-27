# Engine/CLI Team — Design Decisions

Records the "why" behind architectural choices made during the engine/CLI upgrade.
These decisions inform the PyQt migration and any future engine refactors.

---

## ADR-001: Two-step hint command with hint_options

**Status:** Accepted
**Date:** 2026-02-21
**Decision maker:** Engine/CLI team

### Context

The hint feature needs to offer multiple hint types (first letter, character count,
category, progressive reveal). The UI presentation of those options differs fundamentally
between CLI (text menu) and PyQt (button row). We needed a design that:

1. Keeps the engine stateless and UI-agnostic (no sub-menu state in the engine).
2. Works identically with CLI and PyQt without engine changes at Qt migration time.
3. Stays within the existing `Command → GameOutput` contract shape.

### Options considered

**A. Sub-menu in the CLI loop**
- `hint` triggers a blocking `input()` loop for type selection inside `cli_main()`.
- Problem: interactive state lives in the CLI, making it impossible to port to PyQt
  without reimplementing the selection logic entirely. The engine also can't be tested
  without simulating the sub-menu.
- Rejected.

**B. `hint <type>` as a single command (no step 1)**
- User must know the type names upfront (e.g. `hint letter`).
- Bare `hint` defaults to cheapest type.
- Problem: PyQt would need to hard-code the 4 type names as button labels, coupling
  the Qt UI to engine internals. If types change, both engine and Qt need updating.
- Acceptable but not Qt-optimal.

**C. Two-step: bare `hint` returns options, `hint <type>` delivers clue (chosen)**
- Step 1: `Command(verb="hint", args=[])` → engine returns `hint_options` list in
  `GameOutput`. No state change yet.
- Step 2: `Command(verb="hint", args=["letter"])` → engine delivers clue, increments
  `hints_used`, persists.
- CLI reads `hint_options` and renders a numbered menu, then issues step 2.
- PyQt reads `hint_options` and renders buttons, button click issues step 2.
- Engine is identical for both UIs.

### Decision

Option C. The engine returns `hint_options: list[dict] | None` in `GameOutput`.
Each dict: `{"type": str, "label": str, "cost": int}`.

### Consequences

- `GameOutput` gains one optional field (`hint_options`). Fully backwards-compatible
  (defaults to `None`; existing code ignores it).
- CLI sub-menu lives entirely in `cli_main()` — zero engine changes for Qt port.
- PyQt renders `hint_options` as buttons — zero engine changes for Qt port.
- The engine can be tested without simulating any menu interaction.
- If hint types change, only the engine and the `hint_options` list change; both UIs
  automatically show the updated options.

---

## ADR-002: Engine/UI boundary — what Qt must consume

**Status:** Accepted
**Date:** 2026-02-21

### Context

The project roadmap includes a PyQt tile client (Milestone D in customization-design-plan.md).
We need to be explicit about what the Qt adapter needs to implement vs. what the engine
already provides.

### Decision

`GameView` and `GameOutput` are the **complete and stable** boundary between the engine
and any UI. The Qt adapter replaces only `cli_main()`.

**What the Qt adapter consumes from `GameView`:**

| Field | Qt usage |
|---|---|
| `pos` | highlight player tile |
| `cell_title` | room label panel |
| `cell_description` | room description panel |
| `available_moves` | enable/disable directional buttons |
| `pending_puzzle` | show puzzle dialog with `title` and `prompt` |
| `is_complete` | show completion screen |
| `move_count` | status bar |
| `map_text` | optional ASCII overlay or ignored (Qt draws its own tiles) |
| `visited_count` | fog-of-war tile reveal count / progress indicator |

**What the Qt adapter consumes from `GameOutput`:**

| Field | Qt usage |
|---|---|
| `view` | as above |
| `messages` | toast notifications or log panel |
| `did_persist` | optional save indicator |
| `hint_options` | render as button row in puzzle dialog; `None` = hide button row |

**What the Qt adapter sends to the engine:**

All user actions become `Command(verb=..., args=[...])` — identical to CLI.

```python
# Movement button click
Command(verb="go", args=["N"])

# Answer submit
Command(verb="answer", args=[answer_text])

# Hint type button click
Command(verb="hint", args=["letter"])

# Bare hint (show options)
Command(verb="hint", args=[])

# Status, save, scores
Command(verb="status", args=[])
Command(verb="save", args=[])
Command(verb="scores", args=[])
```

### Consequences

- No engine changes are needed for the basic Qt port.
- `map_text` can be ignored by Qt if it renders tiles directly, or shown as a debug overlay.
- The puzzle dialog reads `pending_puzzle` from `GameView` and shows `hint_options` from
  `GameOutput` as buttons — both already populated by the engine.
- Score display reads from `repo.top_scores()` directly (same as CLI `scores` command).

---

## ADR-003: GameView.map_text always populated (never None)

**Status:** Accepted
**Date:** 2026-02-21

### Context

The previous `GameView.map_text: str | None = None` was populated only by the CLI's
explicit `map` command. This meant `view()` returned incomplete data and the CLI had to
call `_render_map` separately.

### Decision

`map_text` is always populated by `_make_view()` using fog-of-war rendering
(`reveal_all=False`). Type changes from `str | None` to `str`.

### Consequences

- PyQt can always read `map_text` for a debug overlay without a separate call.
- Tests can assert `map_text` is non-empty on any view without triggering a `map` command.
- Slight CPU cost: map is rendered on every command, not just `map`. Acceptable for a
  3x3–9x9 maze; revisit if maze sizes grow significantly.
- `_render_map` default changes from `reveal_all=True` to `reveal_all=False` to match
  the fog-of-war-first contract.

---

## ADR-004: hints_used persisted in state and score metrics

**Status:** Accepted
**Date:** 2026-02-21

### Context

The score leaderboard needs `hints_used` to apply a score penalty or secondary sort.
The engine state needs `hints_used` to survive save/load correctly.

### Decision

- `hints_used: int` is persisted in the game state dict (loaded/saved via `db.py`).
- `hints_used` is included in the `metrics` dict passed to `repo.record_score()` on
  game completion.
- Each hint type carries a `cost` (1 or 2) that is the increment to `hints_used`.
  The leaderboard formula is not defined by the engine — it receives the raw count and
  the scoring layer decides the penalty.

### Consequences

- Backwards-compatible: old save files without `hints_used` default to `0` on load.
- Leaderboard can sort by (elapsed_seconds, hints_used, moves) without engine changes.
- The `cost` field in `hint_options` gives the UI enough info to warn the player before
  they commit to an expensive hint type.

---

## ADR-005: Progressive reveal counter is ephemeral (not persisted)

**Status:** Accepted
**Date:** 2026-02-21

### Context

The `hint reveal` command progressively unmasks one more character of the answer on each
use. This requires a counter (`_reveal_progress[gate_id] -> int`) to track how many
characters have been shown so far.

The question is whether this counter should be persisted in the game state dict alongside
`hints_used`, `maze_size`, etc.

### Options considered

**A. Persist `reveal_progress` in the state dict**
- Survives save/quit/reload mid-puzzle.
- Adds a new key to the state schema and `interfaces.md`.
- Marginal UX gain: the only scenario where it matters is if a player uses `hint reveal`
  twice, then saves and quits, then resumes and uses `hint reveal` again on the *same
  unsolved gate*. This is a narrow edge case.

**B. Keep it ephemeral — engine memory only (chosen)**
- Counter resets to 1 on engine instantiation (including save/reload).
- No schema change needed.
- `hints_used` is still persisted and correctly tracks cost even across sessions.
- Reset on solve is already implemented (`_reveal_progress.pop(gate_id)` on correct answer).

### Decision

Option B. The reveal counter is in-memory only. Known limitation: if the player saves
mid-puzzle after several reveals, then reloads, their next `hint reveal` starts from
character 1 again. The `hints_used` cost is still correctly accumulated from the
persisted state, so scoring is unaffected.

### Consequences

- No change to `interfaces.md` §5.1 or the persisted state schema.
- If this proves to be a UX problem in playtesting, promoting the counter to persisted
  state is a backwards-compatible additive change (default to `{}` on load).
- PyQt does not need special handling — the counter resets identically in both UIs.

---

## ADR-006: hint_answer contract extension and hybrid fail policy

**Status:** Accepted
**Date:** 2026-02-21

### Context

The engine needs the correct answer to generate meaningful hints (first letter, character
count, progressive reveal). For DB questions, `correct_answer` is always available. For
registry puzzles, the only *contract-required* method is `check(answer, state) -> bool`,
which does not expose the answer.

Two sub-decisions:

1. How should the engine obtain the answer from registry puzzles?
2. What happens when the answer is unavailable or the registry itself fails?

### Options considered for answer access

**A. Access private `_accept` tuple directly**
- Works today but couples the engine to `Puzzle` internals.
- Breaks if a different puzzle implementation is used (e.g. in tests or plugins).
- Rejected (was the original implementation; caused a test failure with contract-only puzzles).

**B. Add an optional `hint_answer` property to the puzzle contract (chosen)**
- `hint_answer: str` is a `@property` on `Puzzle` and any test fixture that wants specific hints.
- The engine uses `getattr(puzzle, "hint_answer", None)` — purely opt-in.
- If missing, the engine falls back to generic clues (`"?"` placeholders).

### Options considered for failure handling

**A. Broad try/except (swallow all errors)**
- Hides real registry bugs.
- Rejected (was the original implementation).

**B. Hybrid: fail-soft on missing metadata, fail-loud on registry errors (chosen)**
- `getattr(puzzle, "hint_answer", None)` returns `None` gracefully if the property is
  absent → engine produces generic clues. Gameplay continues uninterrupted.
- `self.puzzles.get(gate_id)` is called without a try/except → if the registry itself
  raises an unexpected exception, it propagates to the caller. This surfaces real
  integration bugs in tests and logs.

### Decision

Option B for both: `hint_answer` is an optional contract extension; registry errors propagate.

### Consequences

- `puzzles.py` `Puzzle` class gains a `hint_answer` property (exposes `_accept[0]`).
- Test fixtures (`_TestPuzzle`) also provide `hint_answer` for specific hint testing.
- Contract-only puzzle objects (with only `id/title/prompt/check`) produce generic hints
  without crashing — validated by `test_hint_with_contract_only_puzzle` (C.22).
- Registry bugs are not silently swallowed — they fail tests loudly.
- Future puzzle plugins can opt into richer hints by adding `hint_answer`, or leave it
  out for generic fallback behavior.
