"""
Puzzle registry for the hacker-themed quiz maze.

Contract (interfaces.md §5.2):
- id: str          — matches gate_id values in the maze
- title: str       — short hacker-flavored heading
- prompt: str      — question shown to the player
- category: str    — "python" | "security" | "output" | "debugging" (default: "python")
- difficulty: int  — 1=easy, 2=medium, 3=hard (default: 1)
- hint_answer: str — optional property; first accepted answer for hint generation
- check(answer, state) -> bool

Role in the game:
  The DB question bank (HACKER_SEED_QUESTIONS in db.py) is the primary source of
  gate challenges and covers all four categories. The registry holds gate-specific,
  room-themed puzzles that are tied to named gate IDs in the minimal maze, giving
  those rooms narrative flavor. It also serves as a fallback when the DB is exhausted.
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
    category: str = "python"
    difficulty: int = 1       # 1=easy, 2=medium, 3=hard

    @property
    def hint_answer(self) -> str:
        """Primary accepted answer, used by the engine for hint generation."""
        return self._accept[0] if self._accept else ""

    def check(self, answer: str, state: dict[str, Any]) -> bool:
        return answer.strip().lower() in self._accept


# ---------------------------------------------------------------------------
# Puzzle catalogue
#
# IDs here are gate-specific and match gate_ids in build_minimal_3x3_maze().
# The DB question bank covers general questions; these give specific rooms
# distinct narrative flavour and serve as the registry fallback.
# ---------------------------------------------------------------------------

_PUZZLES: list[Puzzle] = [

    # ------------------------------------------------------------------
    # Minimal maze gates — room-specific, tied to gate IDs in maze.py
    # ------------------------------------------------------------------

    Puzzle(
        id="gate-python-basics-1",
        title="Firewall Lattice — Intrusion Counter",
        prompt=(
            "The firewall's intrusion counter scans each packet in a list\n"
            "before deciding whether to trigger the alarm.\n"
            "\n"
            "  What built-in function returns the number of items in a list?\n"
            "  (one word)"
        ),
        _accept=("len", "len()"),
        category="python",
        difficulty=1,
    ),
    Puzzle(
        id="gate-python-basics-2",
        title="Cipher Node — Function Injector",
        prompt=(
            "An agent planted a subroutine inside the target's runtime.\n"
            "The cipher node demands you name the Python keyword that\n"
            "defines a function before it lets you pass.\n"
            "\n"
            "  What Python keyword is used to define a function?\n"
            "  (one word)"
        ),
        _accept=("def",),
        category="python",
        difficulty=1,
    ),
    Puzzle(
        id="gate-python-basics-3",
        title="Memory Leak — Loop Escape",
        prompt=(
            "The memory banks are leaking. A sentry daemon loops forever\n"
            "unless you inject the correct escape sequence.\n"
            "\n"
            "  What Python keyword exits a loop immediately?\n"
            "  (one word)"
        ),
        _accept=("break",),
        category="python",
        difficulty=1,
    ),

    # ------------------------------------------------------------------
    # Python — medium difficulty (data structures, control flow)
    # ------------------------------------------------------------------

    Puzzle(
        id="gate-python-struct-1",
        title="Lookup Table — Key-Value Cache",
        prompt=(
            "The exploit script maps session tokens to user IDs for O(1)\n"
            "retrieval. The firewall recognises the data structure by name.\n"
            "\n"
            "  What Python data structure maps keys to values?\n"
            "  (one word)"
        ),
        _accept=("dict", "dictionary"),
        category="python",
        difficulty=1,
    ),
    Puzzle(
        id="gate-python-struct-2",
        title="Visited Nodes — Dedup Filter",
        prompt=(
            "The traversal algorithm must not revisit any node. It stores\n"
            "visited addresses in a structure that rejects duplicates silently.\n"
            "\n"
            "  What Python data structure stores only unique values?\n"
            "  (one word)"
        ),
        _accept=("set",),
        category="python",
        difficulty=1,
    ),
    Puzzle(
        id="gate-python-control-1",
        title="Skip Node — Iteration Control",
        prompt=(
            "The scan loop must skip flagged packets without breaking out\n"
            "of the loop entirely. Supply the correct control keyword.\n"
            "\n"
            "  What Python keyword skips the current iteration and continues the loop?\n"
            "  (one word)"
        ),
        _accept=("continue",),
        category="python",
        difficulty=1,
    ),

    # ------------------------------------------------------------------
    # Security — easy/medium
    # ------------------------------------------------------------------

    Puzzle(
        id="gate-security-port-1",
        title="Port Scanner — HTTP Probe",
        prompt=(
            "Your probe sweeps for unencrypted web services. The scanner\n"
            "expects you to know the standard port before it grants access.\n"
            "\n"
            "  What is the default port for HTTP (unencrypted web traffic)?\n"
            "  (number)"
        ),
        _accept=("80",),
        category="security",
        difficulty=1,
    ),
    Puzzle(
        id="gate-security-port-2",
        title="Encrypted Channel — TLS Gate",
        prompt=(
            "Your C2 server communicates over an encrypted channel. The\n"
            "TLS gate demands you prove you know the standard HTTPS port.\n"
            "\n"
            "  What is the default port for HTTPS?\n"
            "  (number)"
        ),
        _accept=("443",),
        category="security",
        difficulty=1,
    ),
    Puzzle(
        id="gate-security-hash-1",
        title="Hash Probe — Digest Gate",
        prompt=(
            "The access log stores passwords as one-way digests so they\n"
            "cannot be reversed. Name the process to get past this gate.\n"
            "\n"
            "  What do we call the process of converting a password to a one-way digest?\n"
            "  (one word)"
        ),
        _accept=("hashing",),
        category="security",
        difficulty=2,
    ),

    # ------------------------------------------------------------------
    # Output reasoning — medium difficulty
    # "What does this print?" style challenges
    # ------------------------------------------------------------------

    Puzzle(
        id="gate-output-1",
        title="Trace Log — Output Analyser",
        prompt=(
            "The log analyser intercepts the following Python snippet:\n"
            "\n"
            "    x = [1, 2, 3]\n"
            "    print(len(x))\n"
            "\n"
            "  What does this print?\n"
            "  (one number)"
        ),
        _accept=("3",),
        category="output",
        difficulty=1,
    ),
    Puzzle(
        id="gate-output-2",
        title="Packet Sniffer — String Slice",
        prompt=(
            "The sniffer extracts a substring from an intercepted token:\n"
            "\n"
            "    token = 'EXPLOIT'\n"
            "    print(token[1:4])\n"
            "\n"
            "  What does this print?\n"
            "  (three letters, lowercase)"
        ),
        _accept=("xpl",),
        category="output",
        difficulty=2,
    ),
    Puzzle(
        id="gate-output-3",
        title="Boolean Trap — Type Check",
        prompt=(
            "A logic gate evaluates this expression before granting access:\n"
            "\n"
            "    print(type(42) == int)\n"
            "\n"
            "  What does this print?\n"
            "  (one word)"
        ),
        _accept=("true",),
        category="output",
        difficulty=1,
    ),
    Puzzle(
        id="gate-output-4",
        title="Range Probe — Loop Counter",
        prompt=(
            "The intrusion counter runs a loop and the analyser captures\n"
            "the final value printed:\n"
            "\n"
            "    for i in range(3):\n"
            "        pass\n"
            "    print(i)\n"
            "\n"
            "  What does this print?\n"
            "  (one number)"
        ),
        _accept=("2",),
        category="output",
        difficulty=2,
    ),

    # ------------------------------------------------------------------
    # Debugging — medium/hard
    # "What's wrong?" style challenges
    # ------------------------------------------------------------------

    Puzzle(
        id="gate-debug-1",
        title="Crash Dump — NameError",
        prompt=(
            "The agent's script crashed with:\n"
            "\n"
            "    NameError: name 'x' is not defined\n"
            "\n"
            "  What kind of error is this?\n"
            "  (one word, no 'Error' suffix)"
        ),
        _accept=("name",),
        category="debugging",
        difficulty=1,
    ),
    Puzzle(
        id="gate-debug-2",
        title="Type Mismatch — Exploit Aborted",
        prompt=(
            "The exploit chain failed with:\n"
            "\n"
            "    TypeError: can only concatenate str (not 'int') to str\n"
            "\n"
            "  What built-in function would fix this by converting the integer?\n"
            "  (one word)"
        ),
        _accept=("str",),
        category="debugging",
        difficulty=2,
    ),
    Puzzle(
        id="gate-debug-3",
        title="Index Overflow — Buffer Probe",
        prompt=(
            "The buffer scanner raised:\n"
            "\n"
            "    IndexError: list index out of range\n"
            "\n"
            "  What kind of error is this?\n"
            "  (one word, no 'Error' suffix)"
        ),
        _accept=("index",),
        category="debugging",
        difficulty=1,
    ),
    Puzzle(
        id="gate-debug-4",
        title="Import Intercept — Module Not Found",
        prompt=(
            "The loader raised:\n"
            "\n"
            "    ModuleNotFoundError: No module named 'cryptex'\n"
            "\n"
            "  What Python command installs missing packages?\n"
            "  (two words, e.g. 'pip install')"
        ),
        _accept=("pip install",),
        category="debugging",
        difficulty=2,
    ),
]

_BY_ID: dict[str, Puzzle] = {p.id: p for p in _PUZZLES}

# Fallback for unknown gate IDs (e.g. procedural maze gate-dynamic-* IDs when DB
# is exhausted). Thematic rather than trivial.
_FALLBACK = Puzzle(
    id="__fallback__",
    title="Uncharted Gate — Access Challenge",
    prompt=(
        "An uncharted security gate bars your path. Its challenge panel reads:\n"
        "\n"
        "  What Python keyword is used to define a class?\n"
        "  (one word)"
    ),
    _accept=("class",),
    category="python",
    difficulty=1,
)


class PuzzleRegistry:
    """Look up puzzles by id. Returns a themed fallback for unknown ids."""

    def get(self, puzzle_id: str) -> Puzzle:
        return _BY_ID.get(puzzle_id, _FALLBACK)
