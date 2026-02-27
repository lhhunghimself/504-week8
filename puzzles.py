"""
Puzzle registry for the hacker-themed quiz maze.

Each puzzle has:
- id: str          — matches gate_id values in the maze
- title: str       — short hacker-flavored heading
- prompt: str      — question shown to the player
- check(answer, state) -> bool
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Puzzle:
    id: str
    title: str
    prompt: str
    _accept: tuple[str, ...]  # accepted answers (case-insensitive, stripped)

    @property
    def hint_answer(self) -> str:
        """Primary accepted answer, used by the engine for hint generation."""
        return self._accept[0] if self._accept else ""

    def check(self, answer: str, state: dict[str, Any]) -> bool:
        return answer.strip().lower() in self._accept


# ---------------------------------------------------------------------------
# Puzzle catalogue — add entries here to expand content
# ---------------------------------------------------------------------------

_PUZZLES: list[Puzzle] = [
    Puzzle(
        id="gate-python-basics-1",
        title="Firewall Lattice — Python Basics",
        prompt=(
            "The firewall demands proof you speak Python.\n"
            "\n"
            "  What built-in function returns the number of items in a list?\n"
            "  (one word)"
        ),
        _accept=("len", "len()"),
    ),
    Puzzle(
        id="gate-python-basics-2",
        title="Cipher Node — Data Types",
        prompt=(
            "A cipher panel blinks:\n"
            "\n"
            "  In Python, what keyword creates a function?\n"
            "  (one word)"
        ),
        _accept=("def",),
    ),
    Puzzle(
        id="gate-python-basics-3",
        title="Memory Leak — Loops",
        prompt=(
            "The memory banks are leaking.  Patch the loop:\n"
            "\n"
            "  Which Python keyword exits a loop immediately?\n"
            "  (one word)"
        ),
        _accept=("break",),
    ),
]

_BY_ID: dict[str, Puzzle] = {p.id: p for p in _PUZZLES}

# Fallback puzzle for unknown gate_ids (keeps the game playable if maze
# references a puzzle_id that isn't in the catalogue yet).
_FALLBACK = Puzzle(
    id="__fallback__",
    title="Unknown Gate",
    prompt=(
        "An unrecognized security gate blocks your path.\n"
        "\n"
        "  What is 1 + 1?\n"
        "  (number)"
    ),
    _accept=("2",),
)


class PuzzleRegistry:
    """Look up puzzles by id.  Returns a fallback for unknown ids."""

    def get(self, puzzle_id: str) -> Puzzle:
        return _BY_ID.get(puzzle_id, _FALLBACK)
