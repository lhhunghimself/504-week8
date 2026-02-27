## Player — grid-locked first-person camera with Doom/DN3D-style movement.
##
## Movement is cell-to-cell with smooth tween interpolation.
## WASD or arrow keys to move, Q/E to snap-turn 90 degrees.
## Direction commands are sent to PyQt via the WSClient.
extends CharacterBody3D

const MOVE_DURATION := 0.25
const TURN_DURATION := 0.15

@onready var _camera: Camera3D = $Camera3D
@onready var _ws: Node = get_node("../WSClient")
@onready var _builder: Node3D = get_node("../MazeBuilder")

# Grid position — row increases south (Z+), col increases east (X+)
var _grid_row: int = 0
var _grid_col: int = 0

# Facing direction as a yaw angle (degrees): 0=North, 90=East, 180=South, 270=West
var _facing_yaw: float = 180.0  # Start facing south (into the maze)

var _is_moving := false
var _snapshot: Dictionary = {}

# Cardinal direction vectors in world space (row, col deltas)
const DIR_DELTA := {
	"N": Vector2i(-1, 0),
	"S": Vector2i(1, 0),
	"E": Vector2i(0, 1),
	"W": Vector2i(0, -1),
}
const DIR_YAW := {"N": 0.0, "S": 180.0, "E": 90.0, "W": 270.0}

func _ready() -> void:
	_ws.maze_update_received.connect(_on_maze_update)
	_ws.highlight_player_received.connect(_on_highlight_player)

func _on_maze_update(snapshot: Dictionary) -> void:
	_snapshot = snapshot
	# Find player position and teleport there on first update
	for cell in snapshot.get("cells", []):
		if cell.get("is_player", false):
			var target_row: int = cell["row"]
			var target_col: int = cell["col"]
			if _grid_row != target_row or _grid_col != target_col:
				_grid_row = target_row
				_grid_col = target_col
				_teleport_to_grid()
			break

func _on_highlight_player(row: int, col: int) -> void:
	if _grid_row != row or _grid_col != col:
		_grid_row = row
		_grid_col = col
		_smooth_move_to_grid()

func _teleport_to_grid() -> void:
	position = _builder.get_cell_world_pos(_grid_row, _grid_col)

func _smooth_move_to_grid() -> void:
	if _is_moving:
		return
	_is_moving = true
	var target := _builder.get_cell_world_pos(_grid_row, _grid_col)
	var tween := create_tween()
	tween.tween_property(self, "position", target, MOVE_DURATION)\
		.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	tween.tween_callback(func(): _is_moving = false)

func _unhandled_input(event: InputEvent) -> void:
	if _is_moving:
		return

	if event is InputEventKey and event.pressed and not event.echo:
		var dir := ""
		match event.keycode:
			KEY_W, KEY_UP:
				dir = _facing_to_cardinal()
			KEY_S, KEY_DOWN:
				dir = _opposite(_facing_to_cardinal())
			KEY_A:
				dir = _left_of(_facing_to_cardinal())
			KEY_D:
				dir = _right_of(_facing_to_cardinal())
			KEY_Q:
				_snap_turn(-90.0)
				return
			KEY_E:
				_snap_turn(90.0)
				return
			KEY_LEFT:
				_snap_turn(-90.0)
				return
			KEY_RIGHT:
				_snap_turn(90.0)
				return
			_:
				return

		if dir != "":
			_try_move(dir)

func _try_move(dir: String) -> void:
	# Turn to face the movement direction, then send command to engine
	var target_yaw: float = DIR_YAW[dir]
	if abs(_facing_yaw - target_yaw) > 1.0:
		_facing_yaw = target_yaw
		_apply_yaw()
	_ws.send_direction(dir)

func _snap_turn(degrees: float) -> void:
	_is_moving = true
	_facing_yaw = fmod(_facing_yaw + degrees + 360.0, 360.0)
	var tween := create_tween()
	tween.tween_property(self, "rotation_degrees:y", -_facing_yaw, TURN_DURATION)\
		.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	tween.tween_callback(func(): _is_moving = false)

func _apply_yaw() -> void:
	rotation_degrees.y = -_facing_yaw

func _facing_to_cardinal() -> String:
	# Snap yaw to nearest cardinal
	var y := fmod(_facing_yaw + 360.0, 360.0)
	if y < 45.0 or y >= 315.0:
		return "N"
	elif y < 135.0:
		return "E"
	elif y < 225.0:
		return "S"
	else:
		return "W"

static func _opposite(dir: String) -> String:
	match dir:
		"N": return "S"
		"S": return "N"
		"E": return "W"
		"W": return "E"
	return dir

static func _left_of(dir: String) -> String:
	match dir:
		"N": return "W"
		"W": return "S"
		"S": return "E"
		"E": return "N"
	return dir

static func _right_of(dir: String) -> String:
	match dir:
		"N": return "E"
		"E": return "S"
		"S": return "W"
		"W": return "N"
	return dir
