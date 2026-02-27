# GUI Forms Team (Team 1) — Interfaces Delta

Additions to `interfaces.md` owned by the GUI Forms team.
Target branch: `feat/gui-forms`

---

## Widgets and Signal/Slot Contracts

See `interfaces.md` Section 7.3 for the full signal/slot tables.

### FormsPanel

- Signal `command_issued(Command)`: emitted on N/S/E/W button clicks
- Slot `update_view(GameView)`: refreshes room info, enables/disables movement buttons based on `available_moves`
- Slot `show_messages(list[str])`: displays engine feedback in a message area
- Attribute `direction_buttons: dict[str, QPushButton]`: keyed by "N", "S", "E", "W"
- Attribute `completion_overlay: QWidget`: visible when `GameView.is_complete` is True

### PuzzleDialog

- Signal `answer_submitted(str)`: emitted when user submits answer text
- Signal `hint_requested(str)`: emitted with hint type name or empty string for options
- Slot `show_puzzle(dict | None)`: shows puzzle area if dict, hides if None
- Slot `show_hint_options(list[dict])`: creates one button per hint option
- Slot `show_hint_result(str)`: displays clue text
- Attribute `answer_input: QLineEdit`
- Attribute `submit_button: QPushButton`
- Attribute `hint_buttons: list[QPushButton]`
- Attribute `puzzle_area: QWidget`: container, visibility toggled by `show_puzzle`
- Attribute `title_label: QLabel`: displays `pending_puzzle["title"]`
- Attribute `prompt_label: QLabel`: displays `pending_puzzle["prompt"]`

### StatusBar

- Slot `update_status(GameView)`: renders position, moves, visited_count
- Method `status_text() -> str`: returns the current display text

### ScoreBoard

- Slot `show_scores(list[dict])`: populates the score table
- Attribute `table: QTableWidget`: one row per score

---

## Data Consumed

All data comes from `GameView` and `GameOutput` — no direct engine or DB access.

| Widget | GameView fields consumed |
|---|---|
| FormsPanel | `available_moves`, `cell_title`, `cell_description`, `is_complete` |
| PuzzleDialog | `pending_puzzle` via `show_puzzle` slot |
| StatusBar | `pos`, `move_count`, `visited_count` |
| ScoreBoard | score dicts from `repo.top_scores()` via Controller |

---

## Test Coverage

| Test ID | Test Name | Status |
|---|---|---|
| E.1 | `test_direction_buttons_emit_correct_commands` | pending |
| E.2 | `test_answer_submit_emits_command` | pending |
| E.3 | `test_hint_options_render_as_buttons` | pending |
| E.4 | `test_hint_button_emits_hint_command` | pending |
| E.5 | `test_movement_buttons_disabled_when_unavailable` | pending |
| E.6 | `test_puzzle_panel_hidden_when_no_puzzle` | pending |
| E.7 | `test_puzzle_panel_shows_prompt` | pending |
| E.8 | `test_status_bar_displays_all_fields` | pending |
| E.9 | `test_score_board_renders_rows` | pending |
| E.10 | `test_completion_screen_shown` | pending |
