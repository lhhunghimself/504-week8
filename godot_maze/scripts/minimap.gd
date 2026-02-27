## Minimap overlay rendered inside the Godot viewport.
## Shows a compact 2D maze map and player facing arrow.
extends Control

const CELL_PX := 14.0
const PAD := 8.0
const HEADER_PX := 16.0

const COLOR_PANEL := Color(0.0, 0.0, 0.0, 0.58)
const COLOR_PANEL_BORDER := Color(0.2, 0.6, 0.3, 0.9)
const COLOR_GRID := Color(0.2, 0.26, 0.35, 1.0)
const COLOR_FOG := Color(0.07, 0.08, 0.1, 0.95)
const COLOR_CELL := Color(0.14, 0.2, 0.28, 0.95)
const COLOR_START := Color(0.08, 0.35, 0.55, 0.95)
const COLOR_EXIT := Color(0.45, 0.2, 0.58, 0.95)
const COLOR_GATE := Color(0.85, 0.58, 0.12, 0.95)
const COLOR_GATE_SOLVED := Color(0.2, 0.72, 0.3, 0.95)
const COLOR_PLAYER_ARROW := Color(0.93, 0.35, 0.32, 1.0)
const COLOR_PASSAGE := Color(0.33, 0.92, 0.45, 0.9)

var _snapshot: Dictionary = {}
var _player_row := 0
var _player_col := 0
var _facing := "S"

@onready var _ws: Node = get_tree().current_scene.get_node("WSClient")
@onready var _player: Node = get_tree().current_scene.get_node("Player")

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	if _ws != null:
		_ws.maze_update_received.connect(_on_maze_update)
		_ws.highlight_player_received.connect(_on_highlight_player)
		_ws.view_direction_received.connect(_on_view_direction)
	set_process(true)

func _process(_delta: float) -> void:
	if _player != null and _player.has_method("get_facing_dir"):
		var d: String = _player.call("get_facing_dir")
		if d != _facing:
			_facing = d
			queue_redraw()

func _on_maze_update(snapshot: Dictionary) -> void:
	_snapshot = snapshot
	for cell in snapshot.get("cells", []):
		if cell.get("is_player", false):
			_player_row = int(cell.get("row", 0))
			_player_col = int(cell.get("col", 0))
			break
	_update_size()
	queue_redraw()

func _on_highlight_player(row: int, col: int) -> void:
	_player_row = row
	_player_col = col
	queue_redraw()

func _on_view_direction(direction: String) -> void:
	var d := direction.to_upper()
	if d in ["N", "S", "E", "W"]:
		_facing = d
		queue_redraw()

func _update_size() -> void:
	var w := int(_snapshot.get("width", 0))
	var h := int(_snapshot.get("height", 0))
	if w <= 0 or h <= 0:
		return
	custom_minimum_size = Vector2(PAD * 2 + w * CELL_PX, PAD * 2 + HEADER_PX + h * CELL_PX)
	size = custom_minimum_size

func _draw() -> void:
	if _snapshot.is_empty():
		return

	var width := int(_snapshot.get("width", 0))
	var height := int(_snapshot.get("height", 0))
	if width <= 0 or height <= 0:
		return

	var panel_rect := Rect2(Vector2.ZERO, custom_minimum_size)
	draw_rect(panel_rect, COLOR_PANEL, true)
	draw_rect(panel_rect, COLOR_PANEL_BORDER, false, 1.0)

	if ThemeDB.fallback_font != null:
		draw_string(
			ThemeDB.fallback_font,
			Vector2(PAD, PAD + 10),
			"MAP  Facing: %s" % _facing,
			HORIZONTAL_ALIGNMENT_LEFT,
			-1,
			12,
			Color(0.82, 0.95, 0.82, 1.0),
		)

	var origin := Vector2(PAD, PAD + HEADER_PX)
	for cell_data in _snapshot.get("cells", []):
		var row := int(cell_data.get("row", 0))
		var col := int(cell_data.get("col", 0))
		var visible := bool(cell_data.get("visible", false))
		var kind := String(cell_data.get("kind", "normal"))
		var has_gate := bool(cell_data.get("has_gate", false))
		var solved := bool(cell_data.get("solved", false))
		var is_player := bool(cell_data.get("is_player", false))

		var rect := Rect2(
			origin.x + col * CELL_PX,
			origin.y + row * CELL_PX,
			CELL_PX - 1,
			CELL_PX - 1,
		)
		var fill := COLOR_FOG if not visible else COLOR_CELL
		if visible and kind == "start":
			fill = COLOR_START
		elif visible and kind == "exit":
			fill = COLOR_EXIT
		elif visible and has_gate and not solved:
			fill = COLOR_GATE
		elif visible and has_gate and solved:
			fill = COLOR_GATE_SOLVED
		draw_rect(rect, fill, true)
		draw_rect(rect, COLOR_GRID, false, 1.0)

		if visible:
			_draw_connections(rect, cell_data.get("connections", []))
		if is_player or (row == _player_row and col == _player_col):
			_draw_player_arrow(rect)

func _draw_connections(rect: Rect2, connections: Array) -> void:
	var center := rect.get_center()
	for conn in connections:
		var d := String(conn)
		match d:
			"N":
				draw_line(center, Vector2(center.x, rect.position.y), COLOR_PASSAGE, 2.0)
			"S":
				draw_line(center, Vector2(center.x, rect.end.y), COLOR_PASSAGE, 2.0)
			"W":
				draw_line(center, Vector2(rect.position.x, center.y), COLOR_PASSAGE, 2.0)
			"E":
				draw_line(center, Vector2(rect.end.x, center.y), COLOR_PASSAGE, 2.0)

func _draw_player_arrow(rect: Rect2) -> void:
	var center := rect.get_center()
	var r := minf(rect.size.x, rect.size.y) * 0.36
	var points := _arrow_points_for_dir(_facing)
	var poly := PackedVector2Array()
	for p in points:
		poly.append(center + p * r)
	draw_colored_polygon(poly, COLOR_PLAYER_ARROW)

func _arrow_points_for_dir(direction: String) -> Array[Vector2]:
	match direction:
		"N":
			return [Vector2(0, -1), Vector2(-0.8, 0.75), Vector2(0.8, 0.75)]
		"S":
			return [Vector2(0, 1), Vector2(-0.8, -0.75), Vector2(0.8, -0.75)]
		"E":
			return [Vector2(1, 0), Vector2(-0.75, -0.8), Vector2(-0.75, 0.8)]
		"W":
			return [Vector2(-1, 0), Vector2(0.75, -0.8), Vector2(0.75, 0.8)]
	return [Vector2(0, 1), Vector2(-0.8, -0.75), Vector2(0.8, -0.75)]
