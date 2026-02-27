import pytest


def test_get_or_create_player_is_idempotent(repo):
    p1 = repo.get_or_create_player("neo")
    p2 = repo.get_or_create_player("neo")

    assert p1["id"] == p2["id"] if isinstance(p1, dict) else p1.id == p2.id


def test_create_and_get_game_round_trip(repo):
    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {"pos": {"row": 0, "col": 0}, "move_count": 0, "solved_gates": [], "started_at": "2026-02-13T00:00:00Z"}
    game = repo.create_game(player_id=player_id, maze_id="maze-3x3-v1", maze_version="1.0", initial_state=initial_state)
    game_id = game["id"] if isinstance(game, dict) else game.id

    loaded = repo.get_game(game_id)
    assert loaded is not None

    if isinstance(loaded, dict):
        assert loaded["player_id"] == player_id
        assert loaded["maze_id"] == "maze-3x3-v1"
        assert loaded["maze_version"] == "1.0"
        assert loaded["state"] == initial_state
        assert loaded["status"] in ("in_progress", "completed")
    else:
        assert loaded.player_id == player_id
        assert loaded.maze_id == "maze-3x3-v1"
        assert loaded.maze_version == "1.0"
        assert loaded.state == initial_state
        assert loaded.status in ("in_progress", "completed")


def test_save_game_updates_state_and_status(repo):
    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {"pos": {"row": 0, "col": 0}, "move_count": 0, "solved_gates": [], "started_at": "2026-02-13T00:00:00Z"}
    game = repo.create_game(player_id=player_id, maze_id="maze-3x3-v1", maze_version="1.0", initial_state=initial_state)
    game_id = game["id"] if isinstance(game, dict) else game.id

    new_state = {**initial_state, "move_count": 3, "pos": {"row": 1, "col": 1}}
    updated = repo.save_game(game_id=game_id, state=new_state, status="completed")

    if isinstance(updated, dict):
        assert updated["state"] == new_state
        assert updated["status"] == "completed"
        assert updated["updated_at"] >= updated["created_at"]
    else:
        assert updated.state == new_state
        assert updated.status == "completed"
        assert updated.updated_at >= updated.created_at


def test_record_score_and_top_scores_ordering(repo):
    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {"pos": {"row": 0, "col": 0}, "move_count": 0, "solved_gates": [], "started_at": "2026-02-13T00:00:00Z"}
    game = repo.create_game(player_id=player_id, maze_id="maze-3x3-v1", maze_version="1.0", initial_state=initial_state)
    game_id = game["id"] if isinstance(game, dict) else game.id

    repo.record_score(
        player_id=player_id,
        game_id=game_id,
        maze_id="maze-3x3-v1",
        maze_version="1.0",
        metrics={"elapsed_seconds": 12, "moves": 20},
    )
    repo.record_score(
        player_id=player_id,
        game_id=game_id,
        maze_id="maze-3x3-v1",
        maze_version="1.0",
        metrics={"elapsed_seconds": 9, "moves": 40},
    )
    repo.record_score(
        player_id=player_id,
        game_id=game_id,
        maze_id="maze-3x3-v1",
        maze_version="1.0",
        metrics={"elapsed_seconds": 9, "moves": 10},
    )

    top2 = repo.top_scores(maze_id="maze-3x3-v1", limit=2)
    assert len(top2) == 2

    def metrics(item):
        if isinstance(item, dict):
            return item["metrics"]
        return item.metrics

    m0 = metrics(top2[0])
    m1 = metrics(top2[1])
    assert (m0["elapsed_seconds"], m0["moves"]) <= (m1["elapsed_seconds"], m1["moves"])
    assert (m0["elapsed_seconds"], m0["moves"]) == (9, 10)


def test_open_repo_creates_database(tmp_path, db_module):
    fn = getattr(db_module, "open_repo", None)
    assert callable(fn), "db.open_repo must exist per interfaces.md Section 4.3"

    db_path = tmp_path / "new.db"
    repo = fn(db_path)
    assert db_path.exists(), "open_repo must create the database file"

    player = repo.get_or_create_player("neo")
    assert player is not None


def test_question_bank_lifecycle(repo):
    questions = [
        {"id": "q1", "question_text": "What is 1+1?", "correct_answer": "2", "category": "math"},
        {"id": "q2", "question_text": "What is 2+2?", "correct_answer": "4", "category": "math"},
        {"id": "q3", "question_text": "What is 3+3?", "correct_answer": "6", "category": "math"},
    ]
    repo.seed_questions(questions)

    q = repo.get_random_question()
    assert q is not None
    assert "id" in q
    assert "question_text" in q
    assert "correct_answer" in q

    first_id = q["id"]
    repo.mark_question_asked(first_id)

    # Fetch + mark the remaining questions until exhausted. Marking as we go avoids
    # nondeterminism from random selection.
    seen_ids = {first_id}
    for _ in range(10):
        q2 = repo.get_random_question()
        if q2 is None:
            break
        assert q2["id"] != first_id, "Marked question should not be returned"
        seen_ids.add(q2["id"])
        repo.mark_question_asked(q2["id"])

    assert repo.get_random_question() is None, "All questions exhausted should return None"
    assert len(seen_ids) == 3, f"Expected to see exactly 3 unique question ids, got {seen_ids}"

    repo.reset_questions()
    q_after = repo.get_random_question()
    assert q_after is not None, "reset_questions should make questions available again"


def test_seed_questions_is_idempotent(repo):
    questions = [
        {"id": "q1", "question_text": "What is 1+1?", "correct_answer": "2"},
        {"id": "q2", "question_text": "What is 2+2?", "correct_answer": "4"},
    ]
    repo.seed_questions(questions)
    repo.seed_questions(questions)

    seen_ids = set()
    for _ in range(100):
        q = repo.get_random_question()
        if q is None:
            break
        seen_ids.add(q["id"])
        repo.mark_question_asked(q["id"])

    assert len(seen_ids) == 2, (
        f"Expected exactly 2 unique questions after double-seed, got {len(seen_ids)}"
    )


def test_get_player_returns_none_for_unknown_id(repo):
    result = repo.get_player("nonexistent-id")
    assert result is None


def test_get_game_returns_none_for_unknown_id(repo):
    result = repo.get_game("nonexistent-id")
    assert result is None


def test_hacker_seed_questions_contract(db_module):
    """HACKER_SEED_QUESTIONS: IDs unique, required keys present, all 4 categories covered."""
    seed = getattr(db_module, "HACKER_SEED_QUESTIONS", None)
    assert seed is not None, "db.HACKER_SEED_QUESTIONS must exist"
    assert len(seed) > 0, "HACKER_SEED_QUESTIONS must be non-empty"

    required_keys = {"id", "question_text", "correct_answer", "category"}
    ids = []
    categories_seen = set()
    for q in seed:
        missing = required_keys - q.keys()
        assert not missing, f"Question {q.get('id')!r} missing keys: {missing}"
        ids.append(q["id"])
        categories_seen.add(q["category"])

    assert len(ids) == len(set(ids)), (
        f"Duplicate IDs in HACKER_SEED_QUESTIONS: {[x for x in ids if ids.count(x) > 1]}"
    )

    expected_categories = {"python", "security", "output", "debugging"}
    missing_cats = expected_categories - categories_seen
    assert not missing_cats, (
        f"HACKER_SEED_QUESTIONS missing questions for categories: {missing_cats}"
    )


def test_seed_questions_preserves_asked_flags_on_reseed(repo):
    """Reseeding same IDs should preserve has_been_asked state by default."""
    questions = [
        {"id": "q1", "question_text": "What is root?", "correct_answer": "admin", "category": "security"},
    ]
    repo.seed_questions(questions)

    q = repo.get_random_question()
    assert q is not None and q["id"] == "q1"
    repo.mark_question_asked("q1")
    assert repo.get_random_question() is None

    # Reseed should refresh content fields but not clear asked flags.
    repo.seed_questions(questions)
    assert repo.get_random_question() is None, (
        "Reseeding must not re-enable already-asked questions unless reset is requested"
    )


def test_reset_questions_reenables_asked_questions_after_reseed(repo):
    """Explicit reset should make previously asked questions available again."""
    questions = [
        {"id": "q1", "question_text": "What is root?", "correct_answer": "admin", "category": "security"},
    ]
    repo.seed_questions(questions)
    repo.mark_question_asked("q1")
    assert repo.get_random_question() is None

    # Default reseed still preserves asked-state.
    repo.seed_questions(questions)
    assert repo.get_random_question() is None

    # Explicit reset should clear asked flags.
    repo.reset_questions()
    q_after_reset = repo.get_random_question()
    assert q_after_reset is not None and q_after_reset["id"] == "q1"

