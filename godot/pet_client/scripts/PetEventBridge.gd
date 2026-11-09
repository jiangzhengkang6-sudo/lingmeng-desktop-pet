class_name PetEventBridge
extends Node

signal action_received(event: Dictionary)

const DEFAULT_URL := "ws://127.0.0.1:8000/api/pet/events"
const RETRY_DELAY_SECONDS := 2.0
const ACTION_IDS := [
	"idle", "listening", "thinking", "speaking",
	"displeased", "shy", "open-app",
	"working", "success", "failure", "refuse", "sleeping", "reminder",
]
const MOUTH_MODES := ["closed", "half-open", "open"]

@export var websocket_url := DEFAULT_URL

var _socket: WebSocketPeer
var _retry_at := 0.0

func _ready() -> void:
	set_process(true)
	_connect()

func _process(_delta: float) -> void:
	if _socket == null:
		if Time.get_ticks_msec() / 1000.0 >= _retry_at:
			_connect()
		return

	_socket.poll()
	var state := _socket.get_ready_state()
	if state == WebSocketPeer.STATE_OPEN:
		while _socket.get_available_packet_count() > 0:
			var packet := _socket.get_packet()
			if _socket.was_string_packet():
				_handle_text(packet.get_string_from_utf8())
	elif state == WebSocketPeer.STATE_CLOSED:
		_socket = null
		_retry_at = Time.get_ticks_msec() / 1000.0 + RETRY_DELAY_SECONDS

func _exit_tree() -> void:
	if _socket != null:
		_socket.close()

func _connect() -> void:
	if websocket_url.is_empty():
		_retry_at = Time.get_ticks_msec() / 1000.0 + RETRY_DELAY_SECONDS
		return

	var socket := WebSocketPeer.new()
	var error := socket.connect_to_url(websocket_url)
	if error != OK:
		_retry_at = Time.get_ticks_msec() / 1000.0 + RETRY_DELAY_SECONDS
		return
	_socket = socket

func _handle_text(text: String) -> void:
	var payload: Variant = JSON.parse_string(text)
	var event := normalize_event(payload)
	if not event.is_empty():
		action_received.emit(event)

static func normalize_event(payload: Variant) -> Dictionary:
	if not payload is Dictionary:
		return {}

	var source: Dictionary = payload
	if String(source.get("type", "")) != "pet.action":
		return {}

	var action_id := _read_string(source, "action_id", "actionId")
	if not ACTION_IDS.has(action_id):
		return {}

	var event := {
		"type": "pet.action",
		"action_id": action_id,
		"emotion": _optional_string(source, "emotion"),
		"mouth_mode": _optional_string(source, "mouth_mode", "mouthMode"),
		"duration_ms": _optional_duration(source),
		"interruptible": _optional_bool(source, "interruptible", true),
	}
	if event.mouth_mode != null and not MOUTH_MODES.has(event.mouth_mode):
		return {}
	if event.duration_ms != null and (event.duration_ms < 0 or event.duration_ms > 600000):
		return {}
	return event

static func _read_string(source: Dictionary, snake_key: String, camel_key: String = "") -> String:
	var value: Variant = source.get(snake_key, source.get(camel_key, ""))
	return value.strip_edges() if value is String else ""

static func _optional_string(source: Dictionary, snake_key: String, camel_key: String = "") -> Variant:
	var value: Variant = source.get(snake_key, source.get(camel_key))
	if value == null:
		return null
	return value if value is String and not value.is_empty() else null

static func _optional_duration(source: Dictionary) -> Variant:
	var value: Variant = source.get("duration_ms", source.get("durationMs"))
	if value == null:
		return null
	if value is int:
		return value
	if value is float and value == floor(value):
		return int(value)
	return -1

static func _optional_bool(source: Dictionary, key: String, fallback: bool) -> bool:
	var value: Variant = source.get(key, fallback)
	return value if value is bool else fallback
