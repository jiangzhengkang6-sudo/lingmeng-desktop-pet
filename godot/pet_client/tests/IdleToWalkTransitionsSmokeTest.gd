extends SceneTree

const PET_SCENE := preload("res://scenes/Pet.tscn")
const CHARACTER_MANIFEST_PATH := "res://assets/characters/crimson-elf/manifest.json"
const TRANSITIONS := {
	"walk-left": "transition-idle-to-walk-left",
	"walk-right": "transition-idle-to-walk-right",
	"walk-front-left": "transition-idle-to-walk-front-left",
	"walk-front-right": "transition-idle-to-walk-front-right",
}
const TRANSITION_FRAME_COUNT := 16

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	for walk_action_id in TRANSITIONS.keys():
		var pet = PET_SCENE.instantiate()
		root.add_child(pet)
		await process_frame
		pet._resource_package.open(CHARACTER_MANIFEST_PATH)
		pet._load_action("idle")
		pet._set_local_action(walk_action_id)
		var transition_action_id := String(TRANSITIONS[walk_action_id])
		if pet._active_action_id != transition_action_id:
			pet.queue_free()
			_fail("Walking %s from idle must begin with %s." % [walk_action_id, transition_action_id])
			return
		for _frame in range(TRANSITION_FRAME_COUNT):
			pet._advance_frame()
		if pet._active_action_id != walk_action_id:
			pet.queue_free()
			_fail("Transition %s must enter %s." % [transition_action_id, walk_action_id])
			return
		if pet._frame_cursor != 0:
			pet.queue_free()
			_fail("Walk %s must begin from its first frame." % walk_action_id)
			return
		pet.queue_free()
		await process_frame

	print("All idle-to-walk transitions smoke test passed.")
	quit(0)

func _fail(message: String) -> void:
	push_error(message)
	quit(1)
