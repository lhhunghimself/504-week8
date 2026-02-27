## MazeBuilder3D — builds the 3D dungeon geometry from a MazeSnapshot dict.
##
## Each cell in the snapshot maps to a 4m x 4m floor tile.  Walls are placed
## wherever a cell does NOT have a connection in that direction.  Special cell
## types (gate, exit, start) get distinct materials.
##
## Uses CSGBox3D for geometry so no external mesh assets are required.
extends Node3D

const CELL_SIZE := 4.0
const WALL_HEIGHT := 3.0
const WALL_THICKNESS := 0.3

var _built_cells: Dictionary = {}  # key: "r,c" → Node3D
var _snapshot: Dictionary = {}

@onready var _ws: Node = get_node("../WSClient")
@onready var _player: CharacterBody3D = get_node("../Player")

# Hacker-themed materials — use procedural textures when available
var _mat_floor: StandardMaterial3D
var _mat_ceiling: StandardMaterial3D
var _mat_wall: StandardMaterial3D
var _mat_wall_fog := _make_material(Color(0.02, 0.02, 0.04))
var _mat_gate: StandardMaterial3D
var _mat_gate_solved := _make_material(Color(0.2, 0.7, 0.3))
var _mat_exit: StandardMaterial3D
var _mat_start := _make_material(Color(0.05, 0.2, 0.4))
var _mat_floor_player := _make_material(Color(0.6, 0.15, 0.2))

func _init_materials() -> void:
	_mat_floor = _make_textured_material(TextureGen.metal_floor(), Color(0.06, 0.08, 0.12))
	_mat_ceiling = _make_textured_material(TextureGen.ceiling_panel(), Color(0.03, 0.04, 0.06))
	_mat_wall = _make_textured_material(TextureGen.brick_wall(), Color(0.08, 0.12, 0.08))
	_mat_gate = _make_textured_material(TextureGen.gate_texture(), Color(0.8, 0.5, 0.1))
	_mat_exit = _make_textured_material(TextureGen.exit_portal(), Color(0.4, 0.1, 0.6))

func _ready() -> void:
	_init_materials()
	_ws.maze_update_received.connect(_on_maze_update)

func _on_maze_update(snapshot: Dictionary) -> void:
	_snapshot = snapshot
	_rebuild(snapshot)

func _rebuild(snapshot: Dictionary) -> void:
	var width: int = snapshot.get("width", 3)
	var height: int = snapshot.get("height", 3)
	var cells: Array = snapshot.get("cells", [])

	var cell_map: Dictionary = {}
	for cell_data in cells:
		var key := "%d,%d" % [cell_data["row"], cell_data["col"]]
		cell_map[key] = cell_data

	# Remove cells that no longer exist
	for key in _built_cells.keys():
		if not cell_map.has(key):
			_built_cells[key].queue_free()
			_built_cells.erase(key)

	for cell_data in cells:
		var r: int = cell_data["row"]
		var c: int = cell_data["col"]
		var key := "%d,%d" % [r, c]
		var visible: bool = cell_data.get("visible", false)
		var kind: String = cell_data.get("kind", "normal")
		var has_gate: bool = cell_data.get("has_gate", false)
		var solved: bool = cell_data.get("solved", false)
		var is_player: bool = cell_data.get("is_player", false)
		var connections: Array = cell_data.get("connections", [])

		# Remove old geometry for this cell if it changed
		if _built_cells.has(key):
			_built_cells[key].queue_free()

		var cell_node := Node3D.new()
		cell_node.name = "Cell_%s" % key
		var world_x := c * CELL_SIZE
		var world_z := r * CELL_SIZE
		cell_node.position = Vector3(world_x, 0, world_z)
		add_child(cell_node)
		_built_cells[key] = cell_node

		if not visible:
			_build_fog_cell(cell_node)
			continue

		_build_floor(cell_node, kind, is_player)
		_build_ceiling(cell_node)
		_build_walls(cell_node, connections, has_gate, solved)

		if has_gate and not solved:
			_build_gate_door(cell_node)
		elif kind == "exit":
			_build_exit_marker(cell_node)

		# Point light per visible cell for that retro look
		var light := OmniLight3D.new()
		light.position = Vector3(CELL_SIZE / 2.0, WALL_HEIGHT * 0.8, CELL_SIZE / 2.0)
		light.light_energy = 0.6
		light.light_color = Color(0.0, 1.0, 0.25) if not has_gate else Color(1.0, 0.6, 0.1)
		light.omni_range = CELL_SIZE * 1.2
		light.omni_attenuation = 1.5
		light.shadow_enabled = false
		cell_node.add_child(light)

func _build_fog_cell(parent: Node3D) -> void:
	# Fog cells: just a dark floor so the void isn't empty
	var floor_box := CSGBox3D.new()
	floor_box.size = Vector3(CELL_SIZE, 0.1, CELL_SIZE)
	floor_box.position = Vector3(CELL_SIZE / 2.0, -0.05, CELL_SIZE / 2.0)
	floor_box.material = _mat_wall_fog
	parent.add_child(floor_box)

func _build_floor(parent: Node3D, kind: String, is_player: bool) -> void:
	var floor_box := CSGBox3D.new()
	floor_box.size = Vector3(CELL_SIZE, 0.1, CELL_SIZE)
	floor_box.position = Vector3(CELL_SIZE / 2.0, -0.05, CELL_SIZE / 2.0)

	if is_player:
		floor_box.material = _mat_floor_player
	elif kind == "start":
		floor_box.material = _mat_start
	elif kind == "exit":
		floor_box.material = _mat_exit
	else:
		floor_box.material = _mat_floor

	parent.add_child(floor_box)

func _build_ceiling(parent: Node3D) -> void:
	var ceil_box := CSGBox3D.new()
	ceil_box.size = Vector3(CELL_SIZE, 0.1, CELL_SIZE)
	ceil_box.position = Vector3(CELL_SIZE / 2.0, WALL_HEIGHT, CELL_SIZE / 2.0)
	ceil_box.material = _mat_ceiling
	parent.add_child(ceil_box)

func _build_walls(parent: Node3D, connections: Array, has_gate: bool, solved: bool) -> void:
	var half := CELL_SIZE / 2.0
	var cx := half
	var cz := half

	# North wall (negative Z direction in our coordinate system)
	if not "N" in connections:
		_add_wall(parent, Vector3(cx, WALL_HEIGHT / 2.0, 0), Vector3(CELL_SIZE, WALL_HEIGHT, WALL_THICKNESS))

	# South wall
	if not "S" in connections:
		_add_wall(parent, Vector3(cx, WALL_HEIGHT / 2.0, CELL_SIZE), Vector3(CELL_SIZE, WALL_HEIGHT, WALL_THICKNESS))

	# West wall
	if not "W" in connections:
		_add_wall(parent, Vector3(0, WALL_HEIGHT / 2.0, cz), Vector3(WALL_THICKNESS, WALL_HEIGHT, CELL_SIZE))

	# East wall
	if not "E" in connections:
		_add_wall(parent, Vector3(CELL_SIZE, WALL_HEIGHT / 2.0, cz), Vector3(WALL_THICKNESS, WALL_HEIGHT, CELL_SIZE))

func _add_wall(parent: Node3D, pos: Vector3, sz: Vector3) -> void:
	var wall := CSGBox3D.new()
	wall.size = sz
	wall.position = pos
	wall.material = _mat_wall
	parent.add_child(wall)

func _build_gate_door(parent: Node3D) -> void:
	# A glowing barrier across the center of the cell
	var door := CSGBox3D.new()
	door.size = Vector3(CELL_SIZE * 0.8, WALL_HEIGHT * 0.9, 0.15)
	door.position = Vector3(CELL_SIZE / 2.0, WALL_HEIGHT * 0.45, CELL_SIZE / 2.0)
	door.material = _mat_gate
	parent.add_child(door)

func _build_exit_marker(parent: Node3D) -> void:
	# A glowing pillar at the exit
	var pillar := CSGBox3D.new()
	pillar.size = Vector3(0.5, WALL_HEIGHT * 0.6, 0.5)
	pillar.position = Vector3(CELL_SIZE / 2.0, WALL_HEIGHT * 0.3, CELL_SIZE / 2.0)
	pillar.material = _mat_exit
	parent.add_child(pillar)

	var exit_light := OmniLight3D.new()
	exit_light.position = Vector3(CELL_SIZE / 2.0, WALL_HEIGHT * 0.5, CELL_SIZE / 2.0)
	exit_light.light_energy = 2.0
	exit_light.light_color = Color(0.6, 0.2, 0.9)
	exit_light.omni_range = CELL_SIZE * 2.0
	exit_light.shadow_enabled = false
	parent.add_child(exit_light)

func get_cell_world_pos(row: int, col: int) -> Vector3:
	return Vector3(col * CELL_SIZE + CELL_SIZE / 2.0, 0.8, row * CELL_SIZE + CELL_SIZE / 2.0)

func get_current_snapshot() -> Dictionary:
	return _snapshot

static func _make_material(color: Color) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = 0.9
	mat.metallic = 0.0
	mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	return mat

static func _make_textured_material(tex: ImageTexture, fallback_color: Color) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	if tex:
		mat.albedo_texture = tex
	else:
		mat.albedo_color = fallback_color
	mat.roughness = 0.9
	mat.metallic = 0.0
	mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	return mat
