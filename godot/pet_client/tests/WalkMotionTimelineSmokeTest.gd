extends SceneTree

const PET_SCENE := preload("res://scenes/Pet.tscn")
const CHARACTER_MANIFEST_PATH := "res://assets/characters/crimson-elf/manifest.json"
const FRAME_DURATION := 0.125

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var pet = PET_SCENE.instantiate()
	root.add_child(pet)
	await process_frame
	pet._resource_package.open(CHARACTER_MANIFEST_PATH)
	pet._load_action("walk-right")

	# 一帧内只落在迈步帧时，整段时间都应移动。
	_check_motion(pet, 3, 0.0, FRAME_DURATION, FRAME_DURATION)
	# 从第 28 帧跨入第 29 帧，只有第 28 帧的前半段允许移动。
	_check_motion(pet, 28, 0.0, FRAME_DURATION * 2.0, FRAME_DURATION)
	# 从第 2 帧跨入第 3 帧，只有第 3 帧的后半段允许移动。
	_check_motion(pet, 2, 0.0, FRAME_DURATION * 2.0, FRAME_DURATION)
	# 跨越第 29–31、0–2 帧的完整循环停顿时必须零位移。
	_check_motion(pet, 29, 0.0, FRAME_DURATION * 6.0, 0.0)
	# 掉帧跳过停顿后到达第 3、4 帧，只计算这两个迈步帧。
	_check_motion(pet, 29, 0.0, FRAME_DURATION * 8.0, FRAME_DURATION * 2.0)
	# 当前帧已经播放一半时，继续跨到下一帧，两段均为迈步帧则仍计满。
	_check_motion(pet, 3, FRAME_DURATION * 0.5, FRAME_DURATION, FRAME_DURATION)
	# 当前迈步帧只剩一半，随后进入停顿帧，只允许这一半位移。
	_check_motion(pet, 28, FRAME_DURATION * 0.5, FRAME_DURATION, FRAME_DURATION * 0.5)

	pet.queue_free()
	await process_frame
	print("Walk motion timeline smoke test passed.")
	quit(0)

func _check_motion(pet: Node, cursor: int, elapsed: float, delta: float, expected: float) -> void:
	pet._frame_cursor = cursor
	pet._elapsed = elapsed
	var actual: float = pet._walk_motion_delta(delta)
	if not is_equal_approx(actual, expected):
		_fail(
			"第 %d 帧起位移时间应为 %.6f 秒，实际为 %.6f 秒。" % [cursor, expected, actual]
		)

func _fail(message: String) -> void:
	push_error(message)
	quit(1)
