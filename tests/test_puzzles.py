"""
Puzzle contract tests (interfaces.md §5.2).

Validates:
- Puzzle dataclass has all required fields and methods.
- Every puzzle in the catalogue has unique IDs, non-empty content, and hacker-themed text.
- check() correctly accepts and rejects answers.
- hint_answer matches _accept[0].
- PuzzleRegistry returns the right puzzle by ID and falls back for unknown IDs.
- category and difficulty are valid values per the contract.
"""

import pytest


def _import_puzzles():
    try:
        import puzzles
        return puzzles
    except ModuleNotFoundError as e:
        pytest.fail(f"Required module 'puzzles.py' not found. Original error: {e}")


VALID_CATEGORIES = {"python", "security", "output", "debugging"}
VALID_DIFFICULTIES = {1, 2, 3}


@pytest.fixture(scope="module")
def puzzles_module():
    return _import_puzzles()


@pytest.fixture(scope="module")
def catalogue(puzzles_module):
    """All puzzles in the registry catalogue (_PUZZLES)."""
    _puzzles = getattr(puzzles_module, "_PUZZLES", None)
    assert _puzzles is not None, "puzzles._PUZZLES must exist"
    assert len(_puzzles) > 0, "puzzles._PUZZLES must be non-empty"
    return _puzzles


@pytest.fixture(scope="module")
def registry(puzzles_module):
    cls = getattr(puzzles_module, "PuzzleRegistry", None)
    assert cls is not None, "puzzles.PuzzleRegistry must exist"
    return cls()


# ---------------------------------------------------------------------------
# Contract field validation
# ---------------------------------------------------------------------------

def test_puzzle_has_required_contract_fields(catalogue):
    """Every puzzle in _PUZZLES satisfies the full §5.2 contract."""
    for p in catalogue:
        assert hasattr(p, "id"),         f"{p} missing 'id'"
        assert hasattr(p, "title"),      f"{p.id} missing 'title'"
        assert hasattr(p, "prompt"),     f"{p.id} missing 'prompt'"
        assert hasattr(p, "category"),   f"{p.id} missing 'category'"
        assert hasattr(p, "difficulty"), f"{p.id} missing 'difficulty'"
        assert hasattr(p, "hint_answer"), f"{p.id} missing 'hint_answer' property"
        assert callable(getattr(p, "check", None)), f"{p.id}: check() must be callable"


def test_puzzle_ids_are_unique(catalogue):
    """No duplicate IDs in the catalogue."""
    ids = [p.id for p in catalogue]
    assert len(ids) == len(set(ids)), f"Duplicate puzzle IDs: {[x for x in ids if ids.count(x) > 1]}"


def test_all_puzzles_have_non_empty_content(catalogue):
    """id, title, and prompt must all be non-empty strings."""
    for p in catalogue:
        assert isinstance(p.id, str) and p.id.strip(), f"Empty id on puzzle {p!r}"
        assert isinstance(p.title, str) and p.title.strip(), f"{p.id}: title is empty"
        assert isinstance(p.prompt, str) and p.prompt.strip(), f"{p.id}: prompt is empty"


def test_puzzle_category_is_valid(catalogue):
    """Every puzzle category must be one of the four contracted values."""
    for p in catalogue:
        assert p.category in VALID_CATEGORIES, (
            f"{p.id}: category {p.category!r} not in {VALID_CATEGORIES}"
        )


def test_puzzle_difficulty_is_valid(catalogue):
    """Every puzzle difficulty must be 1, 2, or 3."""
    for p in catalogue:
        assert p.difficulty in VALID_DIFFICULTIES, (
            f"{p.id}: difficulty {p.difficulty!r} not in {VALID_DIFFICULTIES}"
        )


def test_puzzle_covers_all_four_categories(catalogue):
    """The catalogue must include at least one puzzle per contracted category."""
    present = {p.category for p in catalogue}
    missing = VALID_CATEGORIES - present
    assert not missing, f"No puzzles found for categories: {missing}"


# ---------------------------------------------------------------------------
# check() correctness
# ---------------------------------------------------------------------------

def test_puzzle_check_accepts_correct_answers(catalogue):
    """Every accepted answer in _accept must pass check()."""
    dummy_state: dict = {}
    for p in catalogue:
        for answer in p._accept:
            assert p.check(answer, dummy_state), (
                f"{p.id}: check({answer!r}) returned False — should be True"
            )


def test_puzzle_check_accepts_with_whitespace(catalogue):
    """check() must strip leading/trailing whitespace and be case-insensitive."""
    dummy_state: dict = {}
    for p in catalogue:
        first = p._accept[0]
        assert p.check(f"  {first.upper()}  ", dummy_state), (
            f"{p.id}: check() failed with whitespace/uppercase variant of {first!r}"
        )


def test_puzzle_check_rejects_wrong_answers(catalogue):
    """A clearly wrong answer must fail check() for every puzzle."""
    dummy_state: dict = {}
    wrong = "xXwrongXx_7392"
    for p in catalogue:
        assert not p.check(wrong, dummy_state), (
            f"{p.id}: check({wrong!r}) returned True — should be False"
        )


# ---------------------------------------------------------------------------
# hint_answer
# ---------------------------------------------------------------------------

def test_hint_answer_matches_first_accept(catalogue):
    """hint_answer must equal _accept[0] for every puzzle."""
    for p in catalogue:
        assert p.hint_answer == p._accept[0], (
            f"{p.id}: hint_answer={p.hint_answer!r} != _accept[0]={p._accept[0]!r}"
        )


# ---------------------------------------------------------------------------
# PuzzleRegistry
# ---------------------------------------------------------------------------

def test_registry_returns_correct_puzzle_by_id(puzzles_module, registry, catalogue):
    """Known IDs must return the corresponding puzzle."""
    for p in catalogue:
        result = registry.get(p.id)
        assert result.id == p.id, (
            f"registry.get({p.id!r}) returned puzzle with id={result.id!r}"
        )


def test_registry_returns_fallback_for_unknown_id(registry):
    """Unknown IDs must return a valid fallback puzzle (not raise, not return None)."""
    result = registry.get("totally-unknown-gate-id-99999")
    assert result is not None, "registry.get(unknown) must not return None"
    assert isinstance(result.id, str) and result.id.strip(), \
        "Fallback puzzle must have a non-empty id"
    assert callable(getattr(result, "check", None)), \
        "Fallback puzzle must have a check() method"


def test_fallback_puzzle_is_thematic(registry):
    """The fallback puzzle prompt should not be the trivial '1+1' placeholder."""
    fallback = registry.get("gate-nonexistent-xyz")
    assert "1 + 1" not in fallback.prompt and "1+1" not in fallback.prompt, (
        "Fallback puzzle should be a thematic hacker challenge, not '1+1'"
    )


def test_registry_fallback_check_works(registry):
    """The fallback puzzle's correct answer must pass check()."""
    fallback = registry.get("gate-nonexistent-xyz")
    correct = fallback._accept[0]
    assert fallback.check(correct, {}), (
        f"Fallback puzzle check({correct!r}) returned False"
    )


# ---------------------------------------------------------------------------
# Hacker theme content check
# ---------------------------------------------------------------------------

def test_minimal_maze_gate_ids_are_in_registry(registry):
    """The minimal 3x3 maze gate IDs must have real (non-fallback) registry puzzles."""
    fallback_id = getattr(registry.get("__fallback__"), "id", None)
    for gate_id in ("gate-python-basics-1", "gate-python-basics-2", "gate-python-basics-3"):
        p = registry.get(gate_id)
        assert p.id == gate_id, (
            f"Expected specific puzzle for {gate_id!r} but got fallback ({p.id!r})"
        )
