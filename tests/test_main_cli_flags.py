import importlib

import pytest


def _import_main():
    try:
        return importlib.import_module("main")
    except ModuleNotFoundError as e:
        pytest.fail(f"Required module 'main.py' not found. Original error: {e}")


def test_parse_startup_flags_defaults_to_no_reset():
    main = _import_main()
    assert main._parse_startup_flags([]) is False


def test_parse_startup_flags_detects_reset_flag():
    main = _import_main()
    assert main._parse_startup_flags(["--reset-game"]) is True


def test_parse_startup_flags_rejects_unknown_arguments():
    main = _import_main()
    with pytest.raises(ValueError):
        main._parse_startup_flags(["--not-a-real-flag"])


class _FakeRepo:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | None]] = []

    def seed_questions(self, questions):
        self.calls.append(("seed", len(questions)))

    def reset_questions(self):
        self.calls.append(("reset", None))


def test_initialize_question_bank_without_reset_only_seeds():
    main = _import_main()
    repo = _FakeRepo()
    main._initialize_question_bank(
        repo,
        [{"id": "q1", "question_text": "q", "correct_answer": "a"}],
        reset_game=False,
    )
    assert repo.calls == [("seed", 1)]


def test_initialize_question_bank_with_reset_seeds_then_resets():
    main = _import_main()
    repo = _FakeRepo()
    main._initialize_question_bank(
        repo,
        [{"id": "q1", "question_text": "q", "correct_answer": "a"}],
        reset_game=True,
    )
    assert repo.calls == [("seed", 1), ("reset", None)]
