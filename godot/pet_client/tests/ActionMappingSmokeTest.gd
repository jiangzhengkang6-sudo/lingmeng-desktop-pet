extends SceneTree

const PET_SCENE := preload("res://scenes/Pet.tscn")
const CHARACTER_MANIFEST_PATH := "res://assets/characters/crimson-elf/manifest.json"
const EXPECTED_MAPPINGS := {
	"failure": "displeased",
	"refuse": "displeased",
	"success": "open-app",
	"working": "open-app",
	"sleeping": "idle",
	"reminder": "idle",
}

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var pet = PET_SCENE.instantiate()
	root.add_child(pet)
	await process_frame
	pet._resource_package.open(CHARACTER_MANIFEST_PATH)
	pet._load_action("idle")

	for legacy_action_id in EXPECTED_MAPPINGS.keys():
		var mapped_action_id: String = pet._map_available_action(String(legacy_action_id))
		if mapped_action_id != String(EXPECTED_MAPPINGS[legacy_action_id]):
			pet.queue_free()
			_fail("Legacy action %s mapped to %s, expected %s." % [
				legacy_action_id, mapped_action_id, String(EXPECTED_MAPPINGS[legacy_action_id])
			])
			return
		var event := {
			"type": "pet.action",
			"action_id": legacy_action_id,
			"mouth_mode": "closed",
		}
		pet._on_action_event(event)
		if pet._active_action_id != String(EXPECTED_MAPPINGS[legacy_action_id]):
			pet.queue_free()
			_fail("Event %s played %s, expected %s." % [
				legacy_action_id, pet._active_action_id, String(EXPECTED_MAPPINGS[legacy_action_id])
			])
			return

	pet.queue_free()
	print("Action mapping smoke test passed.")
	quit(0)

func _fail(message: String) -> void:
	push_error(message)
	quit(1)
