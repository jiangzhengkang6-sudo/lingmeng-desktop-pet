class_name WalkMotionPolicy
extends RefCounted

# 默认角色的一轮行走共有 32 帧；首尾各 3 帧是直立启停姿态，
# 第 3 到第 28 帧才是持续迈步帧。
const DEFAULT_WALK_FRAME_COUNT := 32
const DEFAULT_FIRST_MOVING_FRAME := 3
const DEFAULT_LAST_MOVING_FRAME := 28

static func movement_frame_indices(action: Dictionary) -> Array[int]:
	var configured := _to_int_array(
		action.get("movement_frame_indices", action.get("movementFrameIndices", []))
	)
	var playable := _to_int_array(action.get("frame_indices", []))

	if not configured.is_empty():
		var configured_result: Array[int] = []
		for frame in configured:
			if playable.has(frame) and not configured_result.has(frame):
				configured_result.append(frame)
		return configured_result

	# 兼容已经写到本地的旧版角色清单：没有显式配置时，
	# 对内置 32 帧行走动作使用安全默认值。
	if playable.size() == DEFAULT_WALK_FRAME_COUNT:
		var default_result: Array[int] = []
		for frame in range(DEFAULT_FIRST_MOVING_FRAME, DEFAULT_LAST_MOVING_FRAME + 1):
			default_result.append(frame)
		return default_result

	return playable.duplicate()

static func can_move(action: Dictionary, frame_index: int) -> bool:
	return movement_frame_indices(action).has(frame_index)

static func movement_speed_px_per_sec(action: Dictionary, average_speed: float) -> float:
	var playable := _to_int_array(action.get("frame_indices", []))
	var moving_frames := movement_frame_indices(action)
	if playable.is_empty() or moving_frames.is_empty():
		return average_speed
	# 停顿帧不移动，因此迈步阶段略微加快，使整轮的平均速度仍保持 average_speed。
	return average_speed * float(playable.size()) / float(moving_frames.size())

static func _to_int_array(value: Variant) -> Array[int]:
	var result: Array[int] = []
	if not value is Array:
		return result
	for item in value:
		if item is int or item is float:
			result.append(int(item))
	return result
