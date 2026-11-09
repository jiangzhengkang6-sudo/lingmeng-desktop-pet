extends SceneTree

const PolicyScript := preload("res://scripts/WalkMotionPolicy.gd")
const LoaderScript := preload("res://scripts/SpriteManifestLoader.gd")
const CHARACTER_MANIFEST_PATH := "res://assets/characters/crimson-elf/manifest.json"

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var playable_frames: Array[int] = []
	for frame_index in range(32):
		playable_frames.append(frame_index)

	var default_action := {
		"frame_indices": playable_frames,
	}
	var moving_frames := PolicyScript.movement_frame_indices(default_action)
	var expected_first_moving_frame := 3
	var expected_last_moving_frame := 28
	var expected_count := expected_last_moving_frame - expected_first_moving_frame + 1
	if moving_frames.size() != expected_count:
		_fail("默认行走动作应有 %d 个位移帧，实际为 %d 个。" % [expected_count, moving_frames.size()])
		return
	for frame_index in [0, 1, 2, 29, 30, 31]:
		if PolicyScript.can_move(default_action, frame_index):
			_fail("默认行走动作的停顿帧 %d 不应移动窗口。" % frame_index)
			return
	for frame_index in range(expected_first_moving_frame, expected_last_moving_frame + 1):
		if not PolicyScript.can_move(default_action, frame_index):
			_fail("默认行走动作的迈步帧 %d 应允许移动窗口。" % frame_index)
			return

	var active_speed := PolicyScript.movement_speed_px_per_sec(default_action, 80.0)
	var expected_active_speed := 80.0 * 32.0 / float(expected_count)
	if not is_equal_approx(active_speed, expected_active_speed):
		_fail("位移速度未按停顿帧补偿，期望 %f，实际 %f。" % [expected_active_speed, active_speed])
		return

	var configured_action := {
		"frame_indices": playable_frames,
		"movement_frame_indices": [0, 5, 99, 5],
	}
	var configured_frames := PolicyScript.movement_frame_indices(configured_action)
	if configured_frames != [0, 5]:
		_fail("显式位移帧应去重并过滤越界帧，实际为 %s。" % str(configured_frames))
		return

	var custom_action := {
		"frame_indices": [0, 1, 2, 3],
	}
	if PolicyScript.movement_frame_indices(custom_action) != [0, 1, 2, 3]:
		_fail("缺少元数据的自定义 4 帧动作应保持旧行为。")
		return

	for walk_action_id in [
		"walk-left",
		"walk-right",
		"walk-front-left",
		"walk-front-right",
		"walk-back-left",
		"walk-back-right",
	]:
		var walk_action := LoaderScript.load_action(CHARACTER_MANIFEST_PATH, walk_action_id)
		if walk_action.is_empty():
			_fail("无法加载行走动作 %s。" % walk_action_id)
			return
		if not _has_default_pause_frames(walk_action):
			_fail("内置行走动作 %s 的循环边界停顿帧仍会移动。" % walk_action_id)
			return

	print("Walk motion policy smoke test passed.")
	quit(0)

func _has_default_pause_frames(action: Dictionary) -> bool:
	for frame_index in [0, 1, 2, 29, 30, 31]:
		if PolicyScript.can_move(action, frame_index):
			return false
	for frame_index in range(3, 29):
		if not PolicyScript.can_move(action, frame_index):
			return false
	return true

func _fail(message: String) -> void:
	push_error(message)
	quit(1)
