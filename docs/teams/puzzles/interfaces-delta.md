# Puzzles Team — interfaces.md Delta

Scope: additions and changes to `interfaces.md` owned by the Puzzles team.
Target merge: after `feat/puzzles-content` lands on `master`.

---

## §5.2 Puzzle — new fields

Add to the `Puzzle` contract:

```
- category: str    — content grouping
                     Valid values: "python" | "security" | "output" | "debugging"
                     Default: "python"
- difficulty: int  — 1 = easy, 2 = medium, 3 = hard
                     Default: 1
```

Both fields have defaults and are backwards-compatible: existing `PuzzleRegistry`
implementations that don't populate them will continue to work.

---

## §5.2 Puzzle — hint_answer optional property

The `hint_answer: str` property is now documented as an optional contract extension:

```
- hint_answer: str  — optional property; first accepted answer exposed for hint
                      generation. Not required by the engine contract. The engine
                      accesses it via getattr(puzzle, "hint_answer", None) and
                      degrades to generic hints if absent.
```

---

## §5.2 PuzzleRegistry — fallback contract

Add to the `PuzzleRegistry` contract:

```
- get(puzzle_id: str) -> Puzzle
  Must return a valid Puzzle for any puzzle_id, including unknown IDs.
  Must not raise. Must not return None.
  For unknown IDs, returns a themed fallback puzzle (not a trivial placeholder).
```

---

## DB question bank — deduplication and expansion

The `HACKER_SEED_QUESTIONS` in `db.py` was updated to:

1. **Remove duplicates**: `hq-python-01`, `hq-python-02`, `hq-python-03` removed — they
   duplicated the gate-specific registry puzzles (`gate-python-basics-1/2/3`).

2. **Add 2 new python questions**: `hq-python-08` (import), `hq-python-09` (if).

3. **Add 2 new security questions**: `hq-security-06` (DNS), `hq-security-07` (CIDR).

4. **Add 5 output questions** (new category): `hq-output-01` through `hq-output-05`.

5. **Add 6 debugging questions** (new category): `hq-debug-01` through `hq-debug-06`.

Total DB questions: 27 (was 15; net +12 after removing 3 duplicates and adding 15 new).

DB questions now cover all four contracted categories: `python`, `security`, `output`, `debugging`.

---

## puzzles.py — registry expansion

The `_PUZZLES` catalogue was expanded from 3 to 16 puzzles:

| Category | Count | IDs |
|---|---|---|
| python | 6 | gate-python-basics-1/2/3, gate-python-struct-1/2, gate-python-control-1 |
| security | 3 | gate-security-port-1/2, gate-security-hash-1 |
| output | 4 | gate-output-1/2/3/4 |
| debugging | 4 | gate-debug-1/2/3/4 |

The `__fallback__` puzzle was updated from the trivial "What is 1+1?" to a themed Python
keyword challenge.

---

## Test coverage

New test file `tests/test_puzzles.py` (17 tests):

| Test | What it validates |
|---|---|
| `test_puzzle_has_required_contract_fields` | id/title/prompt/category/difficulty/hint_answer/check present on every puzzle |
| `test_puzzle_ids_are_unique` | No duplicate IDs in catalogue |
| `test_all_puzzles_have_non_empty_content` | id, title, prompt are non-empty strings |
| `test_puzzle_category_is_valid` | category in {"python","security","output","debugging"} |
| `test_puzzle_difficulty_is_valid` | difficulty in {1,2,3} |
| `test_puzzle_covers_all_four_categories` | at least one puzzle per contracted category |
| `test_puzzle_check_accepts_correct_answers` | all _accept values pass check() |
| `test_puzzle_check_accepts_with_whitespace` | check() strips and lowercases |
| `test_puzzle_check_rejects_wrong_answers` | clearly wrong answers fail |
| `test_hint_answer_matches_first_accept` | hint_answer == _accept[0] |
| `test_registry_returns_correct_puzzle_by_id` | known IDs return correct puzzle |
| `test_registry_returns_fallback_for_unknown_id` | unknown IDs return valid fallback |
| `test_fallback_puzzle_is_thematic` | fallback is not the trivial "1+1" question |
| `test_registry_fallback_check_works` | fallback correct answer passes check() |
| `test_minimal_maze_gate_ids_are_in_registry` | gate-python-basics-1/2/3 have specific puzzles |
| `test_fallback_satisfies_full_contract` | fallback category/difficulty/hint_answer are valid |
| `test_no_prompt_overlap_between_registry_and_seed` | db seed and registry share no exact question text |

New test in `tests/test_repo_contract.py` (1 test):

| Test | What it validates |
|---|---|
| `test_hacker_seed_questions_contract` | HACKER_SEED_QUESTIONS IDs unique, keys present, all 4 categories covered |
