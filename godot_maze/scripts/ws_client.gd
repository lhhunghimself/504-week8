## WebSocket client — connects to the PyQt MazeCanvas bridge.
##
## Protocol:
##   Python → Godot:  {"type":"maze_update","snapshot":{...}}
##                    {"type":"highlight_player","row":N,"col":N}
##   Godot → Python:  {"type":"direction","value":"N"|"S"|"E"|"W"}
extends Node

signal maze_update_received(snapshot: Dictionary)
signal highlight_player_received(row: int, col: int)

var _socket := WebSocketPeer.new()
var _connected := false
var _url := ""

func _ready() -> void:
	var port := _parse_ws_port()
	if port <= 0:
		push_warning("No --ws-port argument found; running standalone (no PyQt bridge)")
		return
	_url = "ws://127.0.0.1:%d" % port
	_connect_to_server()

func _parse_ws_port() -> int:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--ws-port="):
			return int(arg.split("=")[1])
	return -1

func _connect_to_server() -> void:
	var err := _socket.connect_to_url(_url)
	if err != OK:
		push_error("WebSocket connect failed: %s" % error_string(err))

func _process(_delta: float) -> void:
	_socket.poll()

	var state := _socket.get_ready_state()
	match state:
		WebSocketPeer.STATE_OPEN:
			if not _connected:
				_connected = true
				print("[ws] Connected to PyQt bridge at %s" % _url)
			while _socket.get_available_packet_count() > 0:
				var raw := _socket.get_packet().get_string_from_utf8()
				_handle_message(raw)
		WebSocketPeer.STATE_CLOSING:
			pass
		WebSocketPeer.STATE_CLOSED:
			if _connected:
				_connected = false
				print("[ws] Connection closed (code=%d)" % _socket.get_close_code())

func _handle_message(raw: String) -> void:
	var parsed = JSON.parse_string(raw)
	if parsed == null or not parsed is Dictionary:
		push_warning("Invalid JSON from bridge: %s" % raw.left(200))
		return

	var msg: Dictionary = parsed
	match msg.get("type", ""):
		"maze_update":
			var snapshot: Dictionary = msg.get("snapshot", {})
			if snapshot.size() > 0:
				maze_update_received.emit(snapshot)
		"highlight_player":
			var row: int = msg.get("row", 0)
			var col: int = msg.get("col", 0)
			highlight_player_received.emit(row, col)
		_:
			push_warning("Unknown message type: %s" % msg.get("type", ""))

func send_direction(direction: String) -> void:
	if _socket.get_ready_state() != WebSocketPeer.STATE_OPEN:
		return
	var payload := JSON.stringify({"type": "direction", "value": direction})
	_socket.send_text(payload)
