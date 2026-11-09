extends Node2D

const PetEventBridgeScript := preload("res://scripts/PetEventBridge.gd")
const SpriteResourcePackageScript := preload("res://scripts/SpriteResourcePackage.gd")
const WalkMotionPolicyScript := preload("res://scripts/WalkMotionPolicy.gd")
const IDLE_MANIFEST_PATH := "res://assets/characters/crimson-elf/manifest.json"
const MIN_WINDOW_SIZE := 120
const MAX_WINDOW_SIZE := 480
const WINDOW_SIZE_STEP := 24
const SNAP_DISTANCE := 24
const GODOT_PACKAGE_DIRECTORY := "LingMengDesktopPet/godot-resource-package"
const SHARED_PACKAGE_POLL_SECONDS := 1.0
const SHARED_PREVIEW_POLL_SECONDS := 0.12
const WALK_ACTION_KEYS := {
	KEY_F1: "walk-left",
	KEY_F2: "walk-right",
	KEY_F3: "walk-front-left",
	KEY_F4: "walk-front-right",
	KEY_F5: "walk-back-left",
	KEY_F6: "walk-back-right",
}
const IDLE_TO_WALK_TRANSITIONS := {
	"walk-left": "transition-idle-to-walk-left",
	"walk-right": "transition-idle-to-walk-right",
	"walk-front-left": "transition-idle-to-walk-front-left",
	"walk-front-right": "transition-idle-to-walk-front-right",
}
const WANDER_DIRS := [
	"walk-left",
	"walk-right",
	"walk-front-left",
	"walk-front-right",
	"walk-back-left",
	"walk-back-right",
]
const WALK_DIRECTION_VECTORS := {
	"walk-left": Vector2(-1.0, 0.0),
	"walk-right": Vector2(1.0, 0.0),
	"walk-front-left": Vector2(-0.85, 0.0),
	"walk-front-right": Vector2(0.85, 0.0),
	"walk-back-left": Vector2(-0.85, 0.0),
	"walk-back-right": Vector2(0.85, 0.0),
}
const MIRRORED_WALK_ACTIONS := {
	"walk-left": "walk-right",
	"walk-right": "walk-left",
	"walk-front-left": "walk-front-right",
	"walk-front-right": "walk-front-left",
	"walk-back-left": "walk-back-right",
	"walk-back-right": "walk-back-left",
}
const WALK_SPEED_PX_PER_SEC := 80.0
const WANDER_IDLE_MIN_SECONDS := 2.5
const WANDER_IDLE_MAX_SECONDS := 8.0
const WANDER_WALK_MIN_SECONDS := 3.0
const WANDER_WALK_MAX_SECONDS := 8.0
const WANDER_EDGE_REVERSE_CHANCE := 0.7
const WANDER_CONTINUE_CHANCE := 0.35
const MOTION_TIME_EPSILON := 0.000001

@onready var character: Sprite2D = $Character
@onready var event_bridge: Node = $EventBridge

@export_file("*.json") var manifest_path := IDLE_MANIFEST_PATH

var _resource_package: Object
var _frame_indices: Array[int] = []
var _movement_frame_indices: Array[int] = []
var _frame_cursor := 0
var _frame_duration := 0.125
var _elapsed := 0.0
var _loop := true
var _active_action_id := "idle"
var _dragging := false
var _emotion := ""
var _mouth_mode := "closed"
var _paused := false
var _anchor := "bottom-center"
var _action_interruptible := true
var _action_remaining_seconds := 0.0
var _queued_action_id := ""
var _shared_manifest_path := ""
var _shared_manifest_signature := ""
var _shared_package_elapsed := 0.0
var _shared_preview_path := ""
var _shared_preview_signature := ""
var _shared_preview_elapsed := 0.0
var _window_size := 360
# 自主随机游走状态：在桌面上真实移动窗口，而不是原地踏步。
var _wander_walking := false
var _wander_time_left := 0.0
var _idle_wait_time := 0.0
var _next_idle_pause := 4.0
var _walk_movement_residual := Vector2.ZERO

func _ready() -> void:
	randomize()
	var window := get_window()
	window.borderless = true
	window.always_on_top = true
	window.transparent = DisplayServer.is_window_transparency_available()
	window.min_size = Vector2i(MIN_WINDOW_SIZE, MIN_WINDOW_SIZE)
	window.max_size = Vector2i(MAX_WINDOW_SIZE, MAX_WINDOW_SIZE)
	window.size = Vector2i(360, 360)
	_window_size = window.size.x

	if not window.transparent and DisplayServer.get_name() != "headless":
		push_warning("Per-pixel window transparency is unavailable on this system.")

	_resource_package = SpriteResourcePackageScript.new()
	_shared_manifest_path = _get_shared_manifest_path()
	_shared_preview_path = _get_shared_preview_path()
	if not _try_open_shared_resource_package() and not _resource_package.call("open", manifest_path):
		push_error("Unable to open sprite resource package: %s" % manifest_path)
	_load_action("idle")
	_center_character()
	_next_idle_pause = _random_idle_pause()
	_apply_shared_preview_state_if_changed()
	event_bridge.action_received.connect(_on_action_event)

func _process(delta: float) -> void:
	_shared_package_elapsed += delta
	if _shared_package_elapsed >= SHARED_PACKAGE_POLL_SECONDS:
		_shared_package_elapsed = 0.0
		_reload_shared_resource_package_if_changed()
	_shared_preview_elapsed += delta
	if _shared_preview_elapsed >= SHARED_PREVIEW_POLL_SECONDS:
		_shared_preview_elapsed = 0.0
		_apply_shared_preview_state_if_changed()
	if _paused:
		_center_character()
		return
	# 行走位移必须先按“本帧开始时”的动画时间轴结算，再推进帧序号。
	# 否则掉帧或进程卡顿时，一个 delta 可能跨过停顿帧和迈步帧，窗口会把整段时间都当成移动。
	_update_wander(delta)
	_elapsed += delta
	while _elapsed >= _frame_duration:
		_elapsed = fmod(_elapsed, _frame_duration)
		_advance_frame()
	if _action_remaining_seconds > 0.0:
		_action_remaining_seconds -= delta
		if _action_remaining_seconds <= 0.0 and _active_action_id != "idle":
			_set_local_action("idle")
	_center_character()

func _get_shared_manifest_path() -> String:
	var local_app_data := OS.get_environment("LOCALAPPDATA")
	if local_app_data.is_empty():
		return ""
	return local_app_data.path_join(GODOT_PACKAGE_DIRECTORY).path_join("manifest.json")

func _get_shared_preview_path() -> String:
	var local_app_data := OS.get_environment("LOCALAPPDATA")
	if local_app_data.is_empty():
		return ""
	return local_app_data.path_join(GODOT_PACKAGE_DIRECTORY).path_join("preview.json")

func _read_shared_preview_signature() -> String:
	if _shared_preview_path.is_empty() or not FileAccess.file_exists(_shared_preview_path):
		return ""
	var file := FileAccess.open(_shared_preview_path, FileAccess.READ)
	if file == null:
		return ""
	return file.get_as_text().sha256_text()

func _apply_shared_preview_state_if_changed() -> void:
	if _shared_preview_path.is_empty() or not FileAccess.file_exists(_shared_preview_path):
		return
	var signature := _read_shared_preview_signature()
	if signature.is_empty() or signature == _shared_preview_signature:
		return

	var file := FileAccess.open(_shared_preview_path, FileAccess.READ)
	if file == null:
		return
	var payload: Variant = JSON.parse_string(file.get_as_text())
	if not payload is Dictionary:
		return

	var state: Dictionary = payload
	var requested_size := clampi(int(state.get("size", _window_size)), MIN_WINDOW_SIZE, MAX_WINDOW_SIZE)
	if requested_size != _window_size:
		_set_window_size(requested_size)
	var requested_action := _map_available_action(String(state.get("action", "idle")))
	if requested_action != _active_action_id:
		_set_local_action(requested_action)

	var requested_mouth_mode := String(state.get("mouthMode", state.get("mouth_mode", "closed")))
	if PetEventBridgeScript.MOUTH_MODES.has(requested_mouth_mode):
		_mouth_mode = requested_mouth_mode
	else:
		_mouth_mode = "closed"
	_paused = bool(state.get("paused", false))
	_shared_preview_signature = signature

func _read_shared_manifest_signature() -> String:
	if _shared_manifest_path.is_empty():
		return ""
	var file := FileAccess.open(_shared_manifest_path, FileAccess.READ)
	if file == null:
		return ""
	return file.get_as_text().sha256_text()

func _try_open_shared_resource_package() -> bool:
	if _shared_manifest_path.is_empty() or not FileAccess.file_exists(_shared_manifest_path):
		return false
	var candidate = SpriteResourcePackageScript.new()
	if not candidate.call("open", _shared_manifest_path):
		return false
	_resource_package = candidate
	_shared_manifest_signature = _read_shared_manifest_signature()
	return true

func _reload_shared_resource_package_if_changed() -> void:
	if _shared_manifest_path.is_empty() or not FileAccess.file_exists(_shared_manifest_path):
		return
	var signature := _read_shared_manifest_signature()
	if signature.is_empty() or signature == _shared_manifest_signature:
		return

	var candidate = SpriteResourcePackageScript.new()
	if not candidate.call("open", _shared_manifest_path):
		return
	var previous_package = _resource_package
	var previous_action_id := _active_action_id
	_resource_package = candidate
	if _load_action(previous_action_id).is_empty():
		_resource_package = previous_package
		_load_action(previous_action_id)
		return
	_shared_manifest_signature = signature

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT:
			if event.pressed:
				_dragging = true
				_wander_walking = false
				_idle_wait_time = 0.0
				_next_idle_pause = _random_idle_pause()
				if WANDER_DIRS.has(_active_action_id) or _active_action_id.begins_with("transition-"):
					_set_local_action("idle")
				get_window().start_drag()
			elif _dragging:
				_dragging = false
				_snap_to_screen_edge()
		elif event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_UP:
			_resize_window(WINDOW_SIZE_STEP)
		elif event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_resize_window(-WINDOW_SIZE_STEP)
	elif event is InputEventKey and event.pressed and not event.echo:
		_handle_action_key(event)

func _load_action(action_id: String) -> String:
	if _resource_package == null:
		return ""

	var action: Dictionary = _resource_package.call("load_action_with_fallback", action_id)
	if action.is_empty():
		return ""

	var texture: Texture2D = _resource_package.call("load_texture", action)
	if texture == null:
		if action_id != "idle":
			action = _resource_package.call("load_action_with_fallback", "idle")
			texture = _resource_package.call("load_texture", action) if not action.is_empty() else null
		if texture == null:
			push_error("Unable to load SpriteSheet: %s" % action.get("texture_path", ""))
			return ""

	character.texture = texture
	character.hframes = int(action.columns)
	character.vframes = int(action.rows)
	_frame_indices.assign(action.frame_indices)
	_movement_frame_indices = WalkMotionPolicyScript.movement_frame_indices(action)
	_frame_duration = 1.0 / maxf(float(action.get("fps", 8.0)), 1.0)
	_loop = bool(action.loop)
	_frame_cursor = 0
	_elapsed = 0.0
	_walk_movement_residual = Vector2.ZERO
	_active_action_id = String(action.action_id)
	_action_interruptible = bool(action.get("interruptible", true))
	_anchor = String(action.get("anchor", "bottom-center"))
	character.frame = _frame_indices[_frame_cursor]
	_center_character()
	return _active_action_id

func _advance_frame() -> void:
	if _frame_indices.is_empty():
		return

	var next_cursor := _frame_cursor + 1
	if next_cursor >= _frame_indices.size():
		if not _loop:
			if not _queued_action_id.is_empty():
				var queued_action := _queued_action_id
				_queued_action_id = ""
				_action_interruptible = true
				_set_local_action(queued_action)
			elif _active_action_id != "idle":
				_set_local_action("idle")
			return
		next_cursor = 0

	_frame_cursor = next_cursor
	character.frame = _frame_indices[_frame_cursor]

func _center_character() -> void:
	var viewport_size := get_viewport_rect().size
	if character.texture == null:
		character.position = viewport_size * 0.5
		return

	var frame_size := character.texture.get_size() / Vector2(character.hframes, character.vframes)
	if _anchor == "center":
		character.position = viewport_size * 0.5
	else:
		character.position = Vector2(viewport_size.x * 0.5, viewport_size.y - frame_size.y * 0.5)

func _wander_supported() -> bool:
	return DisplayServer.get_name() != "headless"

func _random_idle_pause() -> float:
	return randf_range(WANDER_IDLE_MIN_SECONDS, WANDER_IDLE_MAX_SECONDS)

func _update_wander(delta: float) -> void:
	if not _wander_supported() or _paused or _dragging:
		return

	if _wander_walking:
		_wander_time_left -= delta
		var hit_edge := _move_window_for_walk(delta)
		if hit_edge:
			_handle_wander_edge()
		elif _wander_time_left <= 0.0:
			_finish_wander_segment()
		return

	if _active_action_id != "idle" or not _queued_action_id.is_empty():
		_idle_wait_time = 0.0
		return
	if _action_remaining_seconds > 0.0 or _mouth_mode != "closed":
		_idle_wait_time = 0.0
		return

	_idle_wait_time += delta
	if _idle_wait_time >= _next_idle_pause:
		_start_wander_segment()

func _start_wander_segment() -> void:
	if not _wander_supported():
		return
	var action_id := String(WANDER_DIRS[randi() % WANDER_DIRS.size()])
	_wander_walking = true
	_idle_wait_time = 0.0
	_wander_time_left = randf_range(WANDER_WALK_MIN_SECONDS, WANDER_WALK_MAX_SECONDS)
	_set_local_action(action_id)

func _finish_wander_segment() -> void:
	_wander_walking = false
	_idle_wait_time = 0.0
	_next_idle_pause = randf_range(0.6, 1.6) if randf() < WANDER_CONTINUE_CHANCE else _random_idle_pause()
	_set_local_action("idle")

func _handle_wander_edge() -> void:
	var mirrored := String(MIRRORED_WALK_ACTIONS.get(_active_action_id, ""))
	if not mirrored.is_empty() and randf() < WANDER_EDGE_REVERSE_CHANCE:
		_wander_time_left = randf_range(WANDER_WALK_MIN_SECONDS, WANDER_WALK_MAX_SECONDS)
		_set_local_action(mirrored)
	else:
		_finish_wander_segment()

func _move_window_for_walk(delta: float) -> bool:
	var direction: Vector2 = WALK_DIRECTION_VECTORS.get(_active_action_id, Vector2.ZERO)
	if direction == Vector2.ZERO:
		_walk_movement_residual = Vector2.ZERO
		return false

	var motion_delta := _walk_motion_delta(delta)
	if motion_delta <= MOTION_TIME_EPSILON:
		# 循环边界的直立停顿帧必须零位移，也不能把亚像素余量带到下一轮。
		_walk_movement_residual = Vector2.ZERO
		return false

	var motion_action := {
		"frame_indices": _frame_indices,
		"movement_frame_indices": _movement_frame_indices,
	}
	var movement_speed := WalkMotionPolicyScript.movement_speed_px_per_sec(
		motion_action,
		WALK_SPEED_PX_PER_SEC,
	)
	var window := get_window()
	var screen := DisplayServer.window_get_current_screen()
	var usable_rect := DisplayServer.screen_get_usable_rect(screen)
	var min_x := usable_rect.position.x
	var max_x := usable_rect.position.x + usable_rect.size.x - window.size.x
	var min_y := usable_rect.position.y
	var max_y := usable_rect.position.y + usable_rect.size.y - window.size.y
	var position := window.position
	_walk_movement_residual.x += direction.x * movement_speed * motion_delta
	_walk_movement_residual.y += direction.y * movement_speed * motion_delta
	var travel := Vector2i(
		_integer_component(_walk_movement_residual.x),
		_integer_component(_walk_movement_residual.y),
	)
	if travel == Vector2i.ZERO:
		return false
	var target := position + travel
	var next_x := clampi(int(round(target.x)), min_x, max_x)
	var next_y := clampi(int(round(target.y)), min_y, max_y)
	var hit_horizontal_edge := (
		(direction.x < 0.0 and next_x <= min_x)
		or (direction.x > 0.0 and next_x >= max_x)
	)
	window.position = Vector2i(next_x, next_y)
	# 保存不足 1 像素的亚像素位移，避免高刷新率下速度被逐帧取整改慢。
	_walk_movement_residual.x -= float(next_x - position.x)
	_walk_movement_residual.y -= float(next_y - position.y)
	return hit_horizontal_edge

func _walk_motion_delta(delta: float) -> float:
	if delta <= 0.0 or _frame_indices.is_empty() or _frame_duration <= 0.0:
		return 0.0

	# 从当前帧已经走过的时间开始，把本次 delta 切成逐帧时间段；
	# 只有时间段落在迈步帧内时才计入位移，跨过多帧或循环边界时也不会让停顿帧滑动。
	var remaining := delta
	var cursor := _frame_cursor
	var time_left_in_frame := clampf(_frame_duration - _elapsed, 0.0, _frame_duration)
	var result := 0.0
	while remaining > MOTION_TIME_EPSILON:
		var slice := minf(remaining, time_left_in_frame)
		if slice > MOTION_TIME_EPSILON and _movement_frame_indices.has(_frame_indices[cursor]):
			result += slice
		remaining -= slice
		if remaining <= MOTION_TIME_EPSILON:
			break
		cursor = (cursor + 1) % _frame_indices.size()
		time_left_in_frame = _frame_duration
	return result

func _integer_component(value: float) -> int:
	if value >= 0.0:
		return int(floor(value))
	return -int(floor(-value))

func _cancel_wander_to_idle() -> void:
	if not _wander_walking:
		return
	_wander_walking = false
	_idle_wait_time = 0.0
	_next_idle_pause = _random_idle_pause()
	_set_local_action("idle")

func _handle_action_key(event: InputEventKey) -> void:
	if WALK_ACTION_KEYS.has(event.keycode):
		_set_local_action(String(WALK_ACTION_KEYS[event.keycode]))
		return

	match event.keycode:
		KEY_1:
			_set_local_action("idle")
		KEY_2:
			_set_local_action("listening")
		KEY_3:
			_set_local_action("thinking")
		KEY_4:
			_set_local_action("speaking")
		KEY_5:
			_set_local_action("displeased")
		KEY_6:
			_set_local_action("shy")
		KEY_7:
			_set_local_action("open-app")


func _map_available_action(action_id: String) -> String:
	match action_id:
		"failure", "refuse":
			return "displeased" if _has_action("displeased") else "idle"
		"success", "working":
			return "open-app" if _has_action("open-app") else "idle"
		"sleeping", "reminder":
			return "idle"
	return action_id

func _on_action_event(event: Dictionary) -> void:
	var requested_action := _map_available_action(String(event.get("action_id", "idle")))
	if not _action_interruptible and _active_action_id != "idle" and requested_action != "idle":
		return

	if not PetEventBridgeScript.ACTION_IDS.has(requested_action):
		requested_action = "idle"

	_emotion = String(event.get("emotion", ""))
	_mouth_mode = String(event.get("mouth_mode", "closed"))
	var duration: Variant = event.get("duration_ms")
	# WebSocket and local preview state can converge on the same action.
	# Do not restart the animation when the event carries no new duration.
	if requested_action == _active_action_id and (duration == null or int(duration) <= 0):
		return
	# 外部动作（对话、语音、状态）优先，打断自主游走。
	if requested_action != "idle":
		_wander_walking = false
		_idle_wait_time = 0.0
	else:
		_next_idle_pause = _random_idle_pause()
	_set_local_action(
		requested_action,
		bool(event.get("interruptible", true)),
		int(duration) if duration != null else 0,
	)

func _set_local_action(action_id: String, interruptible: bool = true, duration_ms: int = 0) -> void:
	if not _action_interruptible and _active_action_id != "idle" and action_id != "idle":
		return
	if IDLE_TO_WALK_TRANSITIONS.has(action_id) and _active_action_id == "idle":
		var transition_action_id := String(IDLE_TO_WALK_TRANSITIONS[action_id])
		if _has_action(transition_action_id):
			_queued_action_id = action_id
			_action_interruptible = false
			_action_remaining_seconds = 0.0
			_load_action(transition_action_id)
			return
	_queued_action_id = ""
	_action_interruptible = interruptible
	_action_remaining_seconds = maxf(float(duration_ms) / 1000.0, 0.0)
	_load_action(action_id)

func _has_action(action_id: String) -> bool:
	if _resource_package == null:
		return false
	var action: Dictionary = _resource_package.call("load_action", action_id, false)
	return not action.is_empty()

func _resize_window(delta: int) -> void:
	var next_size := clampi(_window_size + delta, MIN_WINDOW_SIZE, MAX_WINDOW_SIZE)
	if next_size == _window_size:
		return
	_set_window_size(next_size)

func _set_window_size(next_size: int) -> void:
	var window := get_window()
	var current_size := clampi(window.size.x, MIN_WINDOW_SIZE, MAX_WINDOW_SIZE)
	var center := window.position + Vector2i(current_size / 2, current_size / 2)
	window.size = Vector2i(next_size, next_size)
	window.position = center - Vector2i(next_size / 2, next_size / 2)
	_window_size = next_size
	_snap_to_screen_edge()

func _snap_to_screen_edge() -> void:
	var window := get_window()
	var screen := DisplayServer.window_get_current_screen()
	var usable_rect := DisplayServer.screen_get_usable_rect(screen)
	var position := window.position
	var size := window.size
	var right := usable_rect.position.x + usable_rect.size.x - size.x
	var bottom := usable_rect.position.y + usable_rect.size.y - size.y

	if abs(position.x - usable_rect.position.x) <= SNAP_DISTANCE:
		position.x = usable_rect.position.x
	elif abs(position.x - right) <= SNAP_DISTANCE:
		position.x = right

	if abs(position.y - usable_rect.position.y) <= SNAP_DISTANCE:
		position.y = usable_rect.position.y
	elif abs(position.y - bottom) <= SNAP_DISTANCE:
		position.y = bottom

	window.position = position
