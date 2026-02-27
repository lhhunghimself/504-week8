from collections import deque

import pytest


def _import_required(name: str):
    try:
        return __import__(name)
    except ModuleNotFoundError as e:
        pytest.fail(
            f"Required module '{name}.py' not found yet. "
            f"Create {name}.py to satisfy the engine integration test contract. "
            f"Original error: {e}"
        )


def _dir_token(direction) -> str:
    # Prefer enum name (e.g. "N") but tolerate other representations.
    return getattr(direction, "name", str(direction))


def _bfs_path_to_exit(maze):
    """
    Compute a physical path (list of Directions) from start to exit using only the maze API.
    Ignores gating/puzzles; engine tests will handle gates dynamically.
    """
    start = maze.start
    goal = maze.exit

    q = deque([start])
    prev = {start: None}
    prev_dir = {}

    while q:
        cur = q.popleft()
        if cur == goal:
            break
        for d in maze.available_moves(cur):
            nxt = maze.next_pos(cur, d)
            if nxt is None or nxt in prev:
                continue
            prev[nxt] = cur
            prev_dir[nxt] = d
            q.append(nxt)

    assert goal in prev, "Exit must be reachable for engine integration tests"

    # Reconstruct directions from start->goal
    dirs = []
    cur = goal
    while cur != start:
        d = prev_dir[cur]
        dirs.append(d)
        cur = prev[cur]
    dirs.reverse()
    return dirs


def test_new_game_view_has_valid_position_and_moves(maze_module, repo, puzzle_registry):
    main = _import_required("main")
    engine_cls = getattr(main, "GameEngine", None)
    cmd_cls = getattr(main, "Command", None)
    assert engine_cls is not None, "main.GameEngine must exist per interfaces.md"
    assert cmd_cls is not None, "main.Command must exist per interfaces.md"

    maze = maze_module.build_minimal_3x3_maze()
    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {"pos": {"row": maze.start.row, "col": maze.start.col}, "move_count": 0, "solved_gates": [], "started_at": "2026-02-13T00:00:00Z"}
    game = repo.create_game(player_id=player_id, maze_id=maze.maze_id, maze_version=maze.maze_version, initial_state=initial_state)
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = engine_cls(maze=maze, repo=repo, puzzles=puzzle_registry, player_id=player_id, game_id=game_id)
    view = engine.view()

    pos = view["pos"] if isinstance(view, dict) else view.pos
    assert maze.in_bounds(maze_module.Position(row=pos["row"], col=pos["col"]))

    moves = view["available_moves"] if isinstance(view, dict) else view.available_moves
    assert moves, "available_moves should be non-empty at start"


def test_player_can_progress_after_solving_required_puzzle(maze_module, repo, puzzle_registry):
    main = _import_required("main")
    engine_cls = getattr(main, "GameEngine", None)
    cmd_cls = getattr(main, "Command", None)
    assert engine_cls is not None
    assert cmd_cls is not None

    maze = maze_module.build_minimal_3x3_maze()
    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {"pos": {"row": maze.start.row, "col": maze.start.col}, "move_count": 0, "solved_gates": [], "started_at": "2026-02-13T00:00:00Z"}
    game = repo.create_game(player_id=player_id, maze_id=maze.maze_id, maze_version=maze.maze_version, initial_state=initial_state)
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = engine_cls(maze=maze, repo=repo, puzzles=puzzle_registry, player_id=player_id, game_id=game_id)

    path = _bfs_path_to_exit(maze)
    assert path, "Path to exit should have at least one move in a 3x3 maze"

    # Try first move; if gated, solve puzzle and retry.
    first_dir = path[0]
    out = engine.handle(cmd_cls(verb="go", args=[_dir_token(first_dir)]))
    view = out["view"] if isinstance(out, dict) else out.view

    pending = view["pending_puzzle"] if isinstance(view, dict) else view.pending_puzzle
    if pending is not None:
        # Solve any pending puzzle with the registry's known correct answer ('solve').
        out2 = engine.handle(cmd_cls(verb="answer", args=["solve"]))
        view2 = out2["view"] if isinstance(out2, dict) else out2.view
        pending2 = view2["pending_puzzle"] if isinstance(view2, dict) else view2.pending_puzzle
        assert pending2 is None, "Puzzle should clear after correct answer"

        out3 = engine.handle(cmd_cls(verb="go", args=[_dir_token(first_dir)]))
        view3 = out3["view"] if isinstance(out3, dict) else out3.view
        pending3 = view3["pending_puzzle"] if isinstance(view3, dict) else view3.pending_puzzle
        assert pending3 is None


def test_reaching_exit_completes_game_and_records_score(maze_module, repo, puzzle_registry):
    main = _import_required("main")
    engine_cls = getattr(main, "GameEngine", None)
    cmd_cls = getattr(main, "Command", None)
    assert engine_cls is not None
    assert cmd_cls is not None

    maze = maze_module.build_minimal_3x3_maze()
    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {"pos": {"row": maze.start.row, "col": maze.start.col}, "move_count": 0, "solved_gates": [], "started_at": "2026-02-13T00:00:00Z"}
    game = repo.create_game(player_id=player_id, maze_id=maze.maze_id, maze_version=maze.maze_version, initial_state=initial_state)
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = engine_cls(maze=maze, repo=repo, puzzles=puzzle_registry, player_id=player_id, game_id=game_id)

    for d in _bfs_path_to_exit(maze):
        out = engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
        view = out["view"] if isinstance(out, dict) else out.view

        pending = view["pending_puzzle"] if isinstance(view, dict) else view.pending_puzzle
        while pending is not None:
            out = engine.handle(cmd_cls(verb="answer", args=["solve"]))
            view = out["view"] if isinstance(out, dict) else out.view
            pending = view["pending_puzzle"] if isinstance(view, dict) else view.pending_puzzle
            if pending is not None:
                # If puzzle remains pending, engine is not accepting correct answers.
                pytest.fail("Pending puzzle did not clear after answer")

            # retry the move after solving
            out = engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
            view = out["view"] if isinstance(out, dict) else out.view
            pending = view["pending_puzzle"] if isinstance(view, dict) else view.pending_puzzle

    final_view = engine.view()
    is_complete = final_view["is_complete"] if isinstance(final_view, dict) else final_view.is_complete
    assert is_complete is True

    # Verify game marked completed in persistence
    saved = repo.get_game(game_id)
    status = saved["status"] if isinstance(saved, dict) else saved.status
    assert status == "completed"

    # Verify a score exists for this maze (exact retrieval mechanism is repo-defined;
    # we use top_scores to confirm at least one entry exists).
    scores = repo.top_scores(maze_id=maze.maze_id, limit=10)
    assert scores, "Expected at least one score to be recorded on completion"


def test_save_command_persists_progress_mid_run(maze_module, repo, puzzle_registry):
    main = _import_required("main")
    engine_cls = getattr(main, "GameEngine", None)
    cmd_cls = getattr(main, "Command", None)
    assert engine_cls is not None
    assert cmd_cls is not None

    maze = maze_module.build_minimal_3x3_maze()
    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {"pos": {"row": maze.start.row, "col": maze.start.col}, "move_count": 0, "solved_gates": [], "started_at": "2026-02-13T00:00:00Z"}
    game = repo.create_game(player_id=player_id, maze_id=maze.maze_id, maze_version=maze.maze_version, initial_state=initial_state)
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = engine_cls(maze=maze, repo=repo, puzzles=puzzle_registry, player_id=player_id, game_id=game_id)

    # Make at least one move; if first edge is gated, solve and retry.
    d = _bfs_path_to_exit(maze)[0]
    out = engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
    view = out["view"] if isinstance(out, dict) else out.view
    pending = view["pending_puzzle"] if isinstance(view, dict) else view.pending_puzzle
    if pending is not None:
        engine.handle(cmd_cls(verb="answer", args=["solve"]))
        engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
    engine.handle(cmd_cls(verb="save", args=[]))

    saved = repo.get_game(game_id)
    state = saved["state"] if isinstance(saved, dict) else saved.state
    assert state.get("move_count", 0) >= 1


def test_invalid_command_does_not_corrupt_state(maze_module, repo, puzzle_registry):
    main = _import_required("main")
    engine_cls = getattr(main, "GameEngine", None)
    cmd_cls = getattr(main, "Command", None)
    assert engine_cls is not None
    assert cmd_cls is not None

    maze = maze_module.build_minimal_3x3_maze()
    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {"pos": {"row": maze.start.row, "col": maze.start.col}, "move_count": 0, "solved_gates": [], "started_at": "2026-02-13T00:00:00Z"}
    game = repo.create_game(player_id=player_id, maze_id=maze.maze_id, maze_version=maze.maze_version, initial_state=initial_state)
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = engine_cls(maze=maze, repo=repo, puzzles=puzzle_registry, player_id=player_id, game_id=game_id)

    baseline = engine.view()
    baseline_pos = baseline["pos"] if isinstance(baseline, dict) else baseline.pos
    baseline_moves = baseline.get("move_count") if isinstance(baseline, dict) else getattr(baseline, "move_count", None)

    out = engine.handle(cmd_cls(verb="warp", args=["now"]))
    view = out["view"] if isinstance(out, dict) else out.view

    after = engine.view()
    after_pos = after["pos"] if isinstance(after, dict) else after.pos
    after_moves = after.get("move_count") if isinstance(after, dict) else getattr(after, "move_count", None)

    assert after_pos == baseline_pos
    if baseline_moves is not None and after_moves is not None:
        assert after_moves == baseline_moves


# ---------------------------------------------------------------------------
# Helper to create an engine for the common setup pattern
# ---------------------------------------------------------------------------

def _make_engine(maze_module, repo, puzzle_registry, *, maze=None):
    main = _import_required("main")
    engine_cls = getattr(main, "GameEngine")
    cmd_cls = getattr(main, "Command")

    if maze is None:
        maze = maze_module.build_minimal_3x3_maze()

    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {
        "pos": {"row": maze.start.row, "col": maze.start.col},
        "move_count": 0,
        "solved_gates": [],
        "started_at": "2026-02-13T00:00:00Z",
        "visited": [{"row": maze.start.row, "col": maze.start.col}],
        "hints_used": 0,
        "maze_size": maze.width,
        "num_gates": 1,
        "maze_seed": 0,
    }
    game = repo.create_game(
        player_id=player_id,
        maze_id=maze.maze_id,
        maze_version=maze.maze_version,
        initial_state=initial_state,
    )
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = engine_cls(
        maze=maze, repo=repo, puzzles=puzzle_registry,
        player_id=player_id, game_id=game_id,
    )
    return engine, cmd_cls, maze, player_id, game_id


def _trigger_pending_puzzle(engine, cmd_cls, maze):
    """
    Trigger a pending puzzle by finding any gated direction from the current position.
    Tries all available moves from the start position rather than only BFS-path moves,
    since the gate may be on a non-shortest-path edge.
    """
    start_pos = maze.start
    for d in maze.available_moves(start_pos):
        gate_id = maze.gate_id_for(start_pos, d)
        if gate_id is not None:
            out = engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
            view = out.view if hasattr(out, "view") else out["view"]
            pending = view.pending_puzzle if hasattr(view, "pending_puzzle") else view["pending_puzzle"]
            if pending is not None:
                return out
    return None


# ---------------------------------------------------------------------------
# C.6  hint command provides clue and increments count
# ---------------------------------------------------------------------------

def test_hint_command_provides_clue_and_increments_count(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze, player_id, game_id = _make_engine(maze_module, repo, puzzle_registry)

    gate_out = _trigger_pending_puzzle(engine, cmd_cls, maze)
    assert gate_out is not None, "Minimal maze must have at least one gate to test hint"

    # Step 1: bare hint — should return hint_options, no increment yet
    step1 = engine.handle(cmd_cls(verb="hint", args=[]))
    hint_options = step1.hint_options if hasattr(step1, "hint_options") else step1.get("hint_options")
    assert hint_options is not None and len(hint_options) > 0, \
        "bare hint with pending puzzle must return hint_options"

    # Step 2: pick a hint type — should deliver clue and increment hints_used
    out = engine.handle(cmd_cls(verb="hint", args=["letter"]))
    messages = out.messages if hasattr(out, "messages") else out["messages"]
    assert messages, "hint <type> command must return at least one message"
    assert any(len(m) > 0 for m in messages), "hint clue message must be non-empty"

    saved = repo.get_game(game_id)
    state = saved["state"] if isinstance(saved, dict) else saved.state
    assert state.get("hints_used", 0) >= 1


# ---------------------------------------------------------------------------
# C.7  hint without pending puzzle is safe
# ---------------------------------------------------------------------------

def test_hint_without_pending_puzzle_is_safe(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze, player_id, game_id = _make_engine(maze_module, repo, puzzle_registry)

    baseline = engine.view()
    out = engine.handle(cmd_cls(verb="hint", args=[]))

    messages = out.messages if hasattr(out, "messages") else out["messages"]
    assert messages, "hint without puzzle should return an info/error message"

    after = engine.view()
    assert (after.pos if hasattr(after, "pos") else after["pos"]) == (baseline.pos if hasattr(baseline, "pos") else baseline["pos"])
    assert (after.move_count if hasattr(after, "move_count") else after.get("move_count")) == (baseline.move_count if hasattr(baseline, "move_count") else baseline.get("move_count"))


# ---------------------------------------------------------------------------
# C.8  status command returns progress info
# ---------------------------------------------------------------------------

def test_status_command_returns_progress_info(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze, player_id, game_id = _make_engine(maze_module, repo, puzzle_registry)

    path = _bfs_path_to_exit(maze)
    d = path[0]
    out = engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
    view = out.view if hasattr(out, "view") else out["view"]
    pending = view.pending_puzzle if hasattr(view, "pending_puzzle") else view["pending_puzzle"]
    if pending is not None:
        engine.handle(cmd_cls(verb="answer", args=["solve"]))
        engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))

    out = engine.handle(cmd_cls(verb="status", args=[]))
    messages = out.messages if hasattr(out, "messages") else out["messages"]
    combined = " ".join(messages).lower()

    assert any(kw in combined for kw in ("position", "pos", "row", "col")), \
        f"status should mention position, got: {combined}"
    assert any(kw in combined for kw in ("move", "moves")), \
        f"status should mention moves, got: {combined}"
    assert "hint" in combined, f"status should mention hints used, got: {combined}"
    assert any(kw in combined for kw in ("gate", "gates", "puzzle", "puzzles")), \
        f"status should mention gates/puzzles solved, got: {combined}"
    assert any(kw in combined for kw in ("visit", "visited", "explor", "explored")), \
        f"status should mention exploration/visited progress, got: {combined}"


# ---------------------------------------------------------------------------
# C.9  view always includes map_text and visited_count
# ---------------------------------------------------------------------------

def test_view_always_includes_map_text_and_visited_count(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze, player_id, game_id = _make_engine(maze_module, repo, puzzle_registry)

    view = engine.view()
    map_text = view.map_text if hasattr(view, "map_text") else view.get("map_text")
    assert map_text is not None and len(map_text) > 0, "map_text must be a non-empty string"

    visited_count = view.visited_count if hasattr(view, "visited_count") else view.get("visited_count")
    assert visited_count is not None and visited_count >= 1, "visited_count must be >= 1 at start"

    path = _bfs_path_to_exit(maze)
    d = path[0]
    out = engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
    v = out.view if hasattr(out, "view") else out["view"]
    pending = v.pending_puzzle if hasattr(v, "pending_puzzle") else v["pending_puzzle"]
    if pending is not None:
        engine.handle(cmd_cls(verb="answer", args=["solve"]))
        engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))

    after = engine.view()
    after_count = after.visited_count if hasattr(after, "visited_count") else after.get("visited_count")
    assert after_count > visited_count, "visited_count must increase after moving to a new cell"


# ---------------------------------------------------------------------------
# C.10  fog of war is default in engine map
# ---------------------------------------------------------------------------

def test_fog_of_war_is_default_in_engine_map(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze, player_id, game_id = _make_engine(maze_module, repo, puzzle_registry)

    view = engine.view()
    map_text = view.map_text if hasattr(view, "map_text") else view.get("map_text")
    assert map_text is not None, "map_text must be populated"

    assert "###" in map_text, "Fog of war: unvisited cells should appear as '###'"

    if maze.start != maze.exit:
        assert " X " not in map_text, "Exit should be hidden until discovered"


# ---------------------------------------------------------------------------
# C.11  hints included in score metrics
# ---------------------------------------------------------------------------

def test_hints_included_in_score_metrics(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze, player_id, game_id = _make_engine(maze_module, repo, puzzle_registry)

    path = _bfs_path_to_exit(maze)
    hints_used = 0

    for d in path:
        out = engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
        view = out.view if hasattr(out, "view") else out["view"]
        pending = view.pending_puzzle if hasattr(view, "pending_puzzle") else view["pending_puzzle"]

        while pending is not None:
            engine.handle(cmd_cls(verb="hint", args=["letter"]))
            hints_used += 1
            engine.handle(cmd_cls(verb="answer", args=["solve"]))
            out = engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
            view = out.view if hasattr(out, "view") else out["view"]
            pending = view.pending_puzzle if hasattr(view, "pending_puzzle") else view["pending_puzzle"]

    final = engine.view()
    assert (final.is_complete if hasattr(final, "is_complete") else final["is_complete"]) is True

    scores = repo.top_scores(maze_id=maze.maze_id, limit=1)
    assert scores, "Score must be recorded on completion"
    m = scores[0]["metrics"] if isinstance(scores[0], dict) else scores[0].metrics
    assert "hints_used" in m, "Score metrics must include hints_used"
    assert m["hints_used"] == hints_used


# ---------------------------------------------------------------------------
# C.12  new state keys persisted on save
# ---------------------------------------------------------------------------

def test_new_state_keys_persisted_on_save(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze, player_id, game_id = _make_engine(maze_module, repo, puzzle_registry)

    path = _bfs_path_to_exit(maze)
    d = path[0]
    out = engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
    view = out.view if hasattr(out, "view") else out["view"]
    pending = view.pending_puzzle if hasattr(view, "pending_puzzle") else view["pending_puzzle"]
    if pending is not None:
        engine.handle(cmd_cls(verb="answer", args=["solve"]))
        engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))

    engine.handle(cmd_cls(verb="save", args=[]))

    saved = repo.get_game(game_id)
    state = saved["state"] if isinstance(saved, dict) else saved.state

    for key in ("hints_used", "maze_size", "num_gates", "maze_seed", "visited"):
        assert key in state, f"Persisted state must contain '{key}'"


# ---------------------------------------------------------------------------
# C.13  backwards compatible state load
# ---------------------------------------------------------------------------

def test_backwards_compatible_state_load(maze_module, repo, puzzle_registry):
    main = _import_required("main")
    engine_cls = getattr(main, "GameEngine")
    cmd_cls = getattr(main, "Command")

    maze = maze_module.build_minimal_3x3_maze()
    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    legacy_state = {
        "pos": {"row": maze.start.row, "col": maze.start.col},
        "move_count": 0,
        "solved_gates": [],
        "started_at": "2026-02-13T00:00:00Z",
    }
    game = repo.create_game(
        player_id=player_id,
        maze_id=maze.maze_id,
        maze_version=maze.maze_version,
        initial_state=legacy_state,
    )
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = engine_cls(
        maze=maze, repo=repo, puzzles=puzzle_registry,
        player_id=player_id, game_id=game_id,
    )
    view = engine.view()

    visited_count = view.visited_count if hasattr(view, "visited_count") else view.get("visited_count")
    assert visited_count is not None and visited_count >= 1, "Defaults should populate visited"

    # Persist and confirm defaulted keys are written back out.
    engine.handle(cmd_cls(verb="save", args=[]))
    saved = repo.get_game(game_id)
    state = saved["state"] if isinstance(saved, dict) else saved.state

    assert state.get("hints_used") == 0
    assert state.get("maze_size") == 3, "Legacy state must default maze_size to 3 per interfaces.md"
    assert state.get("num_gates") == 1
    assert state.get("maze_seed") == 0
    assert isinstance(state.get("visited"), list) and state["visited"]
    assert {"row": maze.start.row, "col": maze.start.col} in state["visited"]


# ---------------------------------------------------------------------------
# C.14  engine uses DB question bank then falls back to registry
# ---------------------------------------------------------------------------

def test_engine_uses_db_question_bank_then_falls_back_to_registry(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze, player_id, game_id = _make_engine(maze_module, repo, puzzle_registry)

    repo.seed_questions([
        {"id": "db-q1", "question_text": "DB question: what is 1+1?", "correct_answer": "2", "category": "test"},
    ])

    # Trigger a gate. The minimal maze is expected to have at least one gated move from start.
    gated_dir = None
    gate_id = None
    for d in maze.available_moves(maze.start):
        gid = maze.gate_id_for(maze.start, d)
        if gid is not None:
            gated_dir = d
            gate_id = gid
            break
    assert gated_dir is not None and gate_id is not None, "Expected at least one gated direction from start"

    out = engine.handle(cmd_cls(verb="go", args=[_dir_token(gated_dir)]))
    view = out.view if hasattr(out, "view") else out["view"]
    pending = view.pending_puzzle if hasattr(view, "pending_puzzle") else view["pending_puzzle"]
    assert pending is not None, "Gated move must produce a pending puzzle"

    # When DB questions are available, pending_puzzle['puzzle_id'] is the DB question id.
    assert pending["puzzle_id"] == "db-q1"

    # Answer the DB question correctly and ensure it's exhausted for the next gate.
    engine.handle(cmd_cls(verb="answer", args=["2"]))
    repo.mark_question_asked("db-q1")

    engine2, cmd_cls2, maze2, _, _ = _make_engine(maze_module, repo, puzzle_registry)

    out2 = engine2.handle(cmd_cls2(verb="go", args=[_dir_token(gated_dir)]))
    view2 = out2.view if hasattr(out2, "view") else out2["view"]
    pending2 = view2.pending_puzzle if hasattr(view2, "pending_puzzle") else view2["pending_puzzle"]
    assert pending2 is not None, "Gated move must produce a pending puzzle"

    # When DB questions are exhausted, engine must fall back to the registry (puzzle_id == gate_id).
    assert pending2["puzzle_id"] == gate_id


# ---------------------------------------------------------------------------
# C.15  fog of war map reveals cells after movement
# ---------------------------------------------------------------------------

def test_fog_of_war_map_reveals_cells_after_movement(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze, player_id, game_id = _make_engine(maze_module, repo, puzzle_registry)

    view_before = engine.view()
    map_before = view_before.map_text if hasattr(view_before, "map_text") else view_before.get("map_text")
    fog_before = map_before.count("###")

    path = _bfs_path_to_exit(maze)
    d = path[0]
    out = engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
    view = out.view if hasattr(out, "view") else out["view"]
    pending = view.pending_puzzle if hasattr(view, "pending_puzzle") else view["pending_puzzle"]
    if pending is not None:
        engine.handle(cmd_cls(verb="answer", args=["solve"]))
        engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))

    view_after = engine.view()
    map_after = view_after.map_text if hasattr(view_after, "map_text") else view_after.get("map_text")
    fog_after = map_after.count("###")

    assert fog_after < fog_before, (
        f"Moving to a new cell should reduce fog: {fog_before} -> {fog_after}"
    )


# ---------------------------------------------------------------------------
# C.16  completed score contains elapsed_seconds and moves
# ---------------------------------------------------------------------------

def test_completed_score_contains_elapsed_seconds_and_moves(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze, player_id, game_id = _make_engine(maze_module, repo, puzzle_registry)

    for d in _bfs_path_to_exit(maze):
        out = engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
        view = out.view if hasattr(out, "view") else out["view"]
        pending = view.pending_puzzle if hasattr(view, "pending_puzzle") else view["pending_puzzle"]
        while pending is not None:
            engine.handle(cmd_cls(verb="answer", args=["solve"]))
            out = engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
            view = out.view if hasattr(out, "view") else out["view"]
            pending = view.pending_puzzle if hasattr(view, "pending_puzzle") else view["pending_puzzle"]

    scores = repo.top_scores(maze_id=maze.maze_id, limit=1)
    assert scores, "Score must be recorded on completion"
    m = scores[0]["metrics"] if isinstance(scores[0], dict) else scores[0].metrics

    assert "elapsed_seconds" in m, "Score metrics must include elapsed_seconds"
    assert isinstance(m["elapsed_seconds"], (int, float)) and m["elapsed_seconds"] >= 0
    assert "moves" in m, "Score metrics must include moves"
    assert isinstance(m["moves"], int) and m["moves"] >= 1
    assert "hints_used" in m, "Score metrics must include hints_used"


# ---------------------------------------------------------------------------
# C.17  hint_options dict shape validation
# ---------------------------------------------------------------------------

def test_hint_options_contain_required_keys(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze, player_id, game_id = _make_engine(maze_module, repo, puzzle_registry)

    gate_out = _trigger_pending_puzzle(engine, cmd_cls, maze)
    assert gate_out is not None, "Minimal maze must have at least one gate"

    out = engine.handle(cmd_cls(verb="hint", args=[]))
    hint_options = out.hint_options if hasattr(out, "hint_options") else out.get("hint_options")
    assert hint_options is not None, "bare hint with pending puzzle must return hint_options"
    assert len(hint_options) >= 1, "must offer at least one hint type"

    for opt in hint_options:
        assert "type" in opt, f"hint option missing 'type': {opt}"
        assert "label" in opt, f"hint option missing 'label': {opt}"
        assert "cost" in opt, f"hint option missing 'cost': {opt}"
        assert isinstance(opt["type"], str) and len(opt["type"]) > 0
        assert isinstance(opt["label"], str) and len(opt["label"]) > 0
        assert isinstance(opt["cost"], int) and opt["cost"] >= 1


# ---------------------------------------------------------------------------
# C.18  hint with invalid type returns error, no state change
# ---------------------------------------------------------------------------

def test_hint_invalid_type_returns_error_no_state_change(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze, player_id, game_id = _make_engine(maze_module, repo, puzzle_registry)

    gate_out = _trigger_pending_puzzle(engine, cmd_cls, maze)
    assert gate_out is not None, "Minimal maze must have at least one gate"

    saved_before = repo.get_game(game_id)
    state_before = saved_before["state"] if isinstance(saved_before, dict) else saved_before.state
    hints_before = state_before.get("hints_used", 0)

    out = engine.handle(cmd_cls(verb="hint", args=["nonexistent_type"]))
    messages = out.messages if hasattr(out, "messages") else out["messages"]
    assert messages, "invalid hint type should return an error message"

    saved_after = repo.get_game(game_id)
    state_after = saved_after["state"] if isinstance(saved_after, dict) else saved_after.state
    assert state_after.get("hints_used", 0) == hints_before, \
        "invalid hint type must not increment hints_used"


# ---------------------------------------------------------------------------
# C.19  hint without pending puzzle does not change hints_used
# ---------------------------------------------------------------------------

def test_hint_no_puzzle_does_not_change_hints_used(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze, player_id, game_id = _make_engine(maze_module, repo, puzzle_registry)

    engine.handle(cmd_cls(verb="save", args=[]))
    saved_before = repo.get_game(game_id)
    state_before = saved_before["state"] if isinstance(saved_before, dict) else saved_before.state
    hints_before = state_before.get("hints_used", 0)

    engine.handle(cmd_cls(verb="hint", args=[]))
    engine.handle(cmd_cls(verb="hint", args=["letter"]))

    engine.handle(cmd_cls(verb="save", args=[]))
    saved_after = repo.get_game(game_id)
    state_after = saved_after["state"] if isinstance(saved_after, dict) else saved_after.state
    assert state_after.get("hints_used", 0) == hints_before, \
        "hint without pending puzzle must not change hints_used"


# ---------------------------------------------------------------------------
# C.20  different hint types apply different costs
# ---------------------------------------------------------------------------

def test_hint_types_apply_correct_costs(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze, player_id, game_id = _make_engine(maze_module, repo, puzzle_registry)

    gate_out = _trigger_pending_puzzle(engine, cmd_cls, maze)
    assert gate_out is not None, "Minimal maze must have at least one gate"

    # Use hint letter (cost 1)
    engine.handle(cmd_cls(verb="hint", args=["letter"]))
    saved = repo.get_game(game_id)
    state = saved["state"] if isinstance(saved, dict) else saved.state
    assert state.get("hints_used", 0) == 1, "hint letter should cost 1"

    # Use hint reveal (cost 2) — total should become 3
    engine.handle(cmd_cls(verb="hint", args=["reveal"]))
    saved = repo.get_game(game_id)
    state = saved["state"] if isinstance(saved, dict) else saved.state
    assert state.get("hints_used", 0) == 3, "hint reveal should cost 2 (total 1+2=3)"

    # Use hint count (cost 1) — total should become 4
    engine.handle(cmd_cls(verb="hint", args=["count"]))
    saved = repo.get_game(game_id)
    state = saved["state"] if isinstance(saved, dict) else saved.state
    assert state.get("hints_used", 0) == 4, "hint count should cost 1 (total 3+1=4)"


# ---------------------------------------------------------------------------
# C.21  legacy state without maze_size defaults to 3 (not maze.width)
# ---------------------------------------------------------------------------

def test_legacy_maze_size_defaults_to_contract_value(maze_module, repo, puzzle_registry):
    """Create a legacy state with no maze_size key and verify the engine
    defaults to 3 per §5.1 of interfaces.md, regardless of the actual maze
    dimensions.
    """
    main = _import_required("main")
    engine_cls = getattr(main, "GameEngine")
    cmd_cls = getattr(main, "Command")

    maze = maze_module.build_square_maze(size=5, seed=42, num_gates=1)
    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    legacy_state = {
        "pos": {"row": maze.start.row, "col": maze.start.col},
        "move_count": 0,
        "solved_gates": [],
        "started_at": "2026-02-13T00:00:00Z",
    }
    game = repo.create_game(
        player_id=player_id,
        maze_id=maze.maze_id,
        maze_version=maze.maze_version,
        initial_state=legacy_state,
    )
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = engine_cls(
        maze=maze, repo=repo, puzzles=puzzle_registry,
        player_id=player_id, game_id=game_id,
    )

    engine.handle(cmd_cls(verb="save", args=[]))
    saved = repo.get_game(game_id)
    state = saved["state"] if isinstance(saved, dict) else saved.state

    assert state["maze_size"] == 3, (
        f"Legacy state must default maze_size to 3 per contract, got {state['maze_size']}"
    )


# ---------------------------------------------------------------------------
# C.22  hint works with contract-only puzzle (no private attrs)
# ---------------------------------------------------------------------------

def test_hint_with_contract_only_puzzle(maze_module, repo):
    """Use a puzzle registry that returns an object with ONLY the contract
    interface (id, title, prompt, check) — no _accept, no hint_answer.
    The engine must still produce a hint (even if generic) and not crash.
    """
    from dataclasses import dataclass
    from typing import Any

    @dataclass(frozen=True)
    class MinimalPuzzle:
        id: str
        title: str
        prompt: str

        def check(self, answer: str, state: dict[str, Any]) -> bool:
            return answer.strip().lower() == "42"

    class MinimalRegistry:
        def get(self, puzzle_id: str):
            return MinimalPuzzle(
                id=puzzle_id,
                title=f"Minimal({puzzle_id})",
                prompt="What is the answer? (42)",
            )

    main = _import_required("main")
    engine_cls = getattr(main, "GameEngine")
    cmd_cls = getattr(main, "Command")

    maze = maze_module.build_minimal_3x3_maze()
    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {
        "pos": {"row": maze.start.row, "col": maze.start.col},
        "move_count": 0,
        "solved_gates": [],
        "started_at": "2026-02-13T00:00:00Z",
        "visited": [{"row": maze.start.row, "col": maze.start.col}],
        "hints_used": 0,
    }
    game = repo.create_game(
        player_id=player_id,
        maze_id=maze.maze_id,
        maze_version=maze.maze_version,
        initial_state=initial_state,
    )
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = engine_cls(
        maze=maze, repo=repo, puzzles=MinimalRegistry(),
        player_id=player_id, game_id=game_id,
    )

    gate_out = _trigger_pending_puzzle(engine, cmd_cls, maze)
    assert gate_out is not None, "Minimal maze must have at least one gate"

    for hint_type in ("letter", "count", "category", "reveal"):
        out = engine.handle(cmd_cls(verb="hint", args=[hint_type]))
        messages = out.messages if hasattr(out, "messages") else out["messages"]
        assert messages, f"hint {hint_type} must return at least one message"
        assert any(len(m) > 0 for m in messages), f"hint {hint_type} must produce non-empty clue"


# ---------------------------------------------------------------------------
# C.23  bare hint does not persist, hint <type> does persist
# ---------------------------------------------------------------------------

def test_hint_persist_semantics(maze_module, repo, puzzle_registry):
    """bare hint → did_persist=False; hint <type> → did_persist=True."""
    engine, cmd_cls, maze, player_id, game_id = _make_engine(maze_module, repo, puzzle_registry)

    gate_out = _trigger_pending_puzzle(engine, cmd_cls, maze)
    assert gate_out is not None, "Minimal maze must have at least one gate"

    out_bare = engine.handle(cmd_cls(verb="hint", args=[]))
    assert out_bare.did_persist is False, "bare hint must not persist"

    out_typed = engine.handle(cmd_cls(verb="hint", args=["letter"]))
    assert out_typed.did_persist is True, "hint <type> must persist (it changes hints_used)"


# ---------------------------------------------------------------------------
# C.24  progressive reveal increases chars and resets after solve
#       Uses a deterministic 2-gate 5x5 maze so reset is always exercised.
# ---------------------------------------------------------------------------

def _reveal_depth_from_clue(clue: str) -> int:
    """Parse reveal clue depth from a message like: 'Clue: s o _ _ _'."""
    payload = clue.split(":", 1)[1].strip() if ":" in clue else clue.strip()
    tokens = payload.split()
    if not tokens:
        return 0
    return sum(1 for t in tokens if t != "_")


def test_progressive_reveal_and_reset(maze_module, repo, puzzle_registry):
    """Repeated 'hint reveal' should progress, then reset for the next gate.

    Uses a deterministic 2-gate 5x5 maze (seed=42) and walks the BFS path
    from start to exit. Gate encounters are discovered from actual traversal,
    so this test does not rely on hardcoded gate IDs.
    """
    main = _import_required("main")
    engine_cls = getattr(main, "GameEngine")
    cmd_cls = getattr(main, "Command")

    maze = maze_module.build_square_maze(size=5, seed=42, num_gates=2)
    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {
        "pos": {"row": maze.start.row, "col": maze.start.col},
        "move_count": 0,
        "solved_gates": [],
        "started_at": "2026-02-13T00:00:00Z",
        "visited": [{"row": maze.start.row, "col": maze.start.col}],
        "hints_used": 0,
        "maze_size": 5,
        "num_gates": 2,
        "maze_seed": 42,
    }
    game = repo.create_game(
        player_id=player_id,
        maze_id=maze.maze_id,
        maze_version=maze.maze_version,
        initial_state=initial_state,
    )
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = engine_cls(
        maze=maze, repo=repo, puzzles=puzzle_registry,
        player_id=player_id, game_id=game_id,
    )

    path = _bfs_path_to_exit(maze)
    gate_hits = 0
    gate1_level1 = None
    gate1_level2 = None
    gate2_level1 = None

    for d in path:
        out = engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
        view = out.view if hasattr(out, "view") else out["view"]
        pending = view.pending_puzzle if hasattr(view, "pending_puzzle") else view["pending_puzzle"]
        if pending is None:
            continue

        gate_hits += 1

        # First reveal on this gate.
        out_r1 = engine.handle(cmd_cls(verb="hint", args=["reveal"]))
        msgs_r1 = out_r1.messages if hasattr(out_r1, "messages") else out_r1["messages"]
        assert msgs_r1, "hint reveal must return at least one message"
        level1 = _reveal_depth_from_clue(msgs_r1[0])
        assert level1 >= 1, f"first reveal depth must be >=1, got {level1}"

        if gate_hits == 1:
            # Same gate, second reveal should advance depth.
            out_r2 = engine.handle(cmd_cls(verb="hint", args=["reveal"]))
            msgs_r2 = out_r2.messages if hasattr(out_r2, "messages") else out_r2["messages"]
            assert msgs_r2, "second hint reveal must return a message"
            level2 = _reveal_depth_from_clue(msgs_r2[0])
            assert level2 > level1, (
                f"second reveal must increase depth on same gate: level1={level1}, level2={level2}"
            )
            gate1_level1 = level1
            gate1_level2 = level2

        elif gate_hits == 2:
            # New gate should reset back to first-reveal depth.
            gate2_level1 = level1
            assert gate1_level1 is not None and gate1_level2 is not None
            assert gate2_level1 == gate1_level1, (
                "first reveal depth on second gate should reset to first-reveal depth"
            )
            assert gate2_level1 < gate1_level2, (
                "first reveal on second gate should not carry over deeper reveal level from first gate"
            )

        # Solve pending puzzle and retry same move to cross the gated edge.
        out_ans = engine.handle(cmd_cls(verb="answer", args=["solve"]))
        view_ans = out_ans.view if hasattr(out_ans, "view") else out_ans["view"]
        pending_ans = view_ans.pending_puzzle if hasattr(view_ans, "pending_puzzle") else view_ans["pending_puzzle"]
        assert pending_ans is None, "pending puzzle should clear after correct answer"

        out_retry = engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
        view_retry = out_retry.view if hasattr(out_retry, "view") else out_retry["view"]
        pending_retry = (
            view_retry.pending_puzzle
            if hasattr(view_retry, "pending_puzzle")
            else view_retry["pending_puzzle"]
        )
        assert pending_retry is None, "after solving, retried move should pass gate"

        if gate_hits >= 2:
            break

    assert gate_hits >= 2, "expected to encounter at least two gates on deterministic 2-gate maze"
    assert gate2_level1 is not None, "second gate must be exercised for reset validation"

