extends SceneTree

const BridgeScript := preload("res://scripts/PetEventBridge.gd")

func _init() -> void:
	var snake_case := BridgeScript.normalize_event({
		"type": "pet.action",
		"action_id": "speaking",
		"mouth_mode": "open",
		"duration_ms": 1000,
		"interruptible": true,
	})
	if snake_case.is_empty() or snake_case.action_id != "speaking" or snake_case.mouth_mode != "open":
		_fail("Snake_case event was not normalized.")
		return

	var camel_case := BridgeScript.normalize_event({
		"type": "pet.action",
		"actionId": "success",
		"mouthMode": "closed",
		"durationMs": 500,
	})
	if camel_case.is_empty() or camel_case.action_id != "success" or camel_case.duration_ms != 500:
		_fail("CamelCase event was not normalized.")
		return

	for invalid_event in [
		{"type": "other", "action_id": "idle"},
		{"type": "pet.action", "action_id": "dance"},
		{"type": "pet.action", "action_id": "idle", "mouth_mode": "wide"},
		{"type": "pet.action", "action_id": "idle", "duration_ms": 600001},
	]:
		if not BridgeScript.normalize_event(invalid_event).is_empty():
			_fail("Invalid event was accepted.")
			return

	print("Event bridge smoke test passed.")
	quit(0)

func _fail(message: String) -> void:
	push_error(message)
	quit(1)
