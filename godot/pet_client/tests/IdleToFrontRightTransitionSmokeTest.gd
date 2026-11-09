extends SceneTree

const PET_SCENE := preload("res://scenes/Pet.tscn")
const CHARACTER_MANIFEST_PATH := "res://assets/characters/crimson-elf/manifest.json"
const TRANSITION_ACTION_ID := "transition-idle-to-walk-front-right"
const WALK_ACTION_ID := "walk-front-right"
const TRANSITION_FRAME_COUNT := 16

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var pet = PET_SCENE.instantiate()
	root.add_child(pet)
	await process_frame
	pet._resource_package.open(CHARACTER_MANIFEST_PATH)
	pet._load_action("idle")

	pet._set_local_action(WALK_ACTION_ID)
	if pet._active_action_id != TRANSITION_ACTION_ID:
		_fail("Walking front-right from idle must begin with the transition.")
		return

	for _frame in range(TRANSITION_FRAME_COUNT):
		pet._advance_frame()

	if pet._active_action_id != WALK_ACTION_ID:
		_fail("The completed transition must enter front-right walking.")
		return
	if pet._frame_cursor != 0:
		_fail("Front-right walking must begin from its first frame.")
		return

	pet.queue_free()
	print("Idle-to-front-right transition smoke test passed.")
	quit(0)

func _fail(message: String) -> void:
	push_error(message)
	quit(1)
