"""Standalone Pygame raycaster validation script.

Opens a plain Pygame window and renders the maze using the raycaster module.
Use WASD / arrow keys / Q / E to move and turn.

Usage:
    python pygame_standalone_test.py [--size N] [--seed N]
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pygame

from gui.renderers.raycaster import (
    FACING_ANGLES,
    Grid,
    angle_for_facing,
    build_grid,
    facing_for_angle,
    render_frame,
)

SCREEN_W, SCREEN_H = 800, 600
FPS = 60
FONT_SIZE = 18


def _build_snapshot(size: int, seed: int) -> dict:
    """Build a maze snapshot dict via the game engine."""
    from db import HACKER_SEED_QUESTIONS, open_repo
    from main import (
        GameEngine,
        StartupConfig,
        _build_maze,
        _initialize_question_bank,
        _utc_now_iso,
    )
    from puzzles import PuzzleRegistry

    tmpdir = TemporaryDirectory(prefix="pygame-test-")
    save_path = Path(tmpdir.name) / "test.db"
    repo = open_repo(save_path)
    _initialize_question_bank(repo, HACKER_SEED_QUESTIONS, reset_game=True)

    config = StartupConfig(maze_size=size, maze_seed=seed, num_gates=max(1, size // 3))
    maze = _build_maze(config)

    player = repo.get_or_create_player("test")
    pid = player["id"] if isinstance(player, dict) else player.id

    visited = [{"row": r, "col": c} for r in range(maze.height) for c in range(maze.width)]
    state = {
        "pos": {"row": maze.start.row, "col": maze.start.col},
        "move_count": 0,
        "solved_gates": sorted(
            cid for cid in (getattr(cell, "puzzle_id", None) for cell in maze.cells.values())
            if cid is not None
        ),
        "started_at": _utc_now_iso(),
        "visited": visited,
        "hints_used": 0,
        "maze_size": size,
        "num_gates": config.num_gates,
        "maze_seed": seed,
    }
    game = repo.create_game(
        player_id=pid,
        maze_id=maze.maze_id,
        maze_version=maze.maze_version,
        initial_state=state,
    )
    gid = game["id"] if isinstance(game, dict) else game.id

    engine = GameEngine(
        maze=maze, repo=repo, puzzles=PuzzleRegistry(),
        player_id=pid, game_id=gid,
    )
    view = engine.view()
    snap = view.maze_snapshot
    cells_data = [
        {
            "row": cv.row, "col": cv.col, "kind": cv.kind,
            "visible": cv.visible, "is_player": cv.is_player,
            "has_gate": cv.has_gate, "solved": cv.solved,
            "connections": list(cv.connections),
        }
        for cv in snap.cells
    ]
    tmpdir.cleanup()
    return {"width": snap.width, "height": snap.height, "cells": cells_data}


def _move_dir(facing: str) -> tuple[int, int]:
    return {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}[facing]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pygame raycaster standalone test")
    parser.add_argument("--size", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv or sys.argv[1:])

    snapshot = _build_snapshot(args.size, args.seed)
    grid = build_grid(snapshot)

    # Find player start
    player_col, player_row = 0, 0
    for c in snapshot["cells"]:
        if c.get("is_player"):
            player_row, player_col = c["row"], c["col"]
            break

    px = player_col + 0.5
    py = player_row + 0.5
    facing = "S"
    angle = angle_for_facing(facing)

    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Pygame Raycaster Test")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("monospace", FONT_SIZE)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key in (pygame.K_q, pygame.K_a, pygame.K_LEFT):
                    angle = (angle + math.pi / 2) % (2 * math.pi)
                    facing = facing_for_angle(angle)
                elif event.key in (pygame.K_e, pygame.K_d, pygame.K_RIGHT):
                    angle = (angle - math.pi / 2) % (2 * math.pi)
                    facing = facing_for_angle(angle)
                elif event.key in (pygame.K_w, pygame.K_UP):
                    dc, dr = _move_dir(facing)
                    nr, nc = int(py) + dr, int(px) + dc
                    cell = grid.cell(int(py), int(px))
                    if cell and not cell.walls.get(facing, True):
                        px = nc + 0.5
                        py = nr + 0.5
                elif event.key in (pygame.K_s, pygame.K_DOWN):
                    opp = {"N": "S", "S": "N", "E": "W", "W": "E"}[facing]
                    dc, dr = _move_dir(opp)
                    nr, nc = int(py) + dr, int(px) + dc
                    cell = grid.cell(int(py), int(px))
                    if cell and not cell.walls.get(opp, True):
                        px = nc + 0.5
                        py = nr + 0.5

        render_frame(screen, grid, px, py, angle, SCREEN_W, SCREEN_H)

        hud = font.render(
            f"Facing: {facing}  Cell: ({int(py)},{int(px)})  "
            f"Angle: {math.degrees(angle):.0f}deg",
            True, (0, 255, 65),
        )
        screen.blit(hud, (8, SCREEN_H - FONT_SIZE - 8))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
