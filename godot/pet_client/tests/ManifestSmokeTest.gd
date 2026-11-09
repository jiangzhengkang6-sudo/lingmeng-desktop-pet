extends SceneTree

const MANIFEST_PATH := "res://assets/testing/manifest.json"
const EXPECTED_FRAME_COUNT := 24
const EXCLUDED_FRAME := 24
const TEST_ACTION_IDS := ["idle", "listening", "thinking", "speaking", "success"]
const CHARACTER_ACTION_IDS := ["idle", "listening", "thinking", "speaking", "displeased", "shy", "open-app"]
const PackageScript := preload("res://scripts/SpriteResourcePackage.gd")
const LoaderScript := preload("res://scripts/SpriteManifestLoader.gd")
const MULTI_SHEET_MANIFEST_PATH := "res://assets/testing/multi-sheet-manifest.json"
const CHARACTER_MANIFEST_PATH := "res://assets/characters/crimson-elf/manifest.json"
const WALK_ACTION_IDS := [
	"walk-left", "walk-right", "walk-front-left",
	"walk-front-right", "walk-back-left", "walk-back-right",
]
const WALK_FRAME_COUNT := 32
const WALK_BLANK_FRAMES := [32, 33, 34, 35]
const IDLE_FRAME_COUNT := 32
const IDLE_BLANK_FRAMES := [32, 33, 34, 35]
const TRANSITION_ACTION_IDS := [
	"transition-idle-to-walk-left",
	"transition-idle-to-walk-right",
	"transition-idle-to-walk-front-left",
	"transition-idle-to-walk-front-right",
]
const TRANSITION_FRAME_COUNT := 16

func _init() -> void:
	var action := LoaderScript.load_action(MANIFEST_PATH, "idle")
	if action.is_empty():
		_fail("The test idle action could not be loaded.")
		return

	var frames: Array[int] = action.frame_indices
	if frames.size() != EXPECTED_FRAME_COUNT:
		_fail("Expected %d valid frames, received %d." % [EXPECTED_FRAME_COUNT, frames.size()])
		return

	if frames.has(EXCLUDED_FRAME):
		_fail("The known blank frame %d must not be playable." % EXCLUDED_FRAME)
		return

	if not ResourceLoader.exists(String(action.texture_path)):
		_fail("The test SpriteSheet is missing: %s" % action.texture_path)
		return

	for action_id in TEST_ACTION_IDS:
		var registered_action := LoaderScript.load_action_with_fallback(MANIFEST_PATH, action_id)
		if registered_action.is_empty() or String(registered_action.action_id) != action_id:
			_fail("Registered action '%s' could not be loaded." % action_id)
			return

	var missing_action := LoaderScript.load_action_with_fallback(MANIFEST_PATH, "failure")
	if missing_action.is_empty() or not bool(missing_action.get("fallback", false)):
		_fail("Missing actions must fall back to idle.")
		return

	var package = PackageScript.new()
	if not package.open(MANIFEST_PATH):
		_fail("The resource package could not be opened.")
		return
	var cached_idle: Dictionary = package.load_action_with_fallback("idle")
	var cached_speaking: Dictionary = package.load_action_with_fallback("speaking")
	if cached_idle.get("sheet_key") != "testing-idle" or cached_speaking.get("sheet_key") != "testing-idle":
		_fail("Package actions did not preserve their SpriteSheet binding.")
		return
	if package.load_texture(cached_idle) == null:
		_fail("The package could not load its cached SpriteSheet texture.")
		return

	var multi_sheet_package = PackageScript.new()
	if not multi_sheet_package.open(MULTI_SHEET_MANIFEST_PATH):
		_fail("The multi-SpriteSheet package could not be opened.")
		return
	var multi_idle: Dictionary = multi_sheet_package.load_action_with_fallback("idle")
	var multi_speaking: Dictionary = multi_sheet_package.load_action_with_fallback("speaking")
	if multi_idle.get("sheet_key") == multi_speaking.get("sheet_key"):
		_fail("Actions in the multi-SpriteSheet package must keep separate bindings.")
		return
	if multi_speaking.get("anchor") != "center":
		_fail("The action anchor must override the SpriteSheet anchor.")
		return

	var character_action := LoaderScript.load_action(CHARACTER_MANIFEST_PATH, "idle")
	if character_action.is_empty():
		_fail("The default character idle action could not be loaded.")
		return
	if character_action.columns != 6 or character_action.rows != 6 or character_action.frame_indices.size() != IDLE_FRAME_COUNT:
		_fail("The default character idle frame geometry is invalid.")
		return

	var character_package := PackageScript.new()
	if not character_package.open(CHARACTER_MANIFEST_PATH):
		_fail("The default character package could not be opened.")
		return
	if character_package.load_texture(character_action) == null:
		_fail("The default character package could not load its idle texture.")
		return

	for core_action_id in CHARACTER_ACTION_IDS:
		var core_action := LoaderScript.load_action(CHARACTER_MANIFEST_PATH, core_action_id)
		if core_action.is_empty():
			_fail("The core action '%s' could not be loaded." % core_action_id)
			return
		if core_action.columns != 6 or core_action.rows != 6 or core_action.frame_indices.size() != WALK_FRAME_COUNT:
			_fail("The core action '%s' has invalid frame geometry." % core_action_id)
			return
		if character_package.load_texture(core_action) == null:
			_fail("The core texture is missing for '%s'." % core_action_id)
			return

	for transition_action_id in TRANSITION_ACTION_IDS:
		var transition_action := LoaderScript.load_action(CHARACTER_MANIFEST_PATH, transition_action_id)
		if transition_action.is_empty():
			_fail("The transition action '%s' could not be loaded." % transition_action_id)
			return
		if transition_action.columns != 4 or transition_action.rows != 4 or transition_action.frame_indices.size() != TRANSITION_FRAME_COUNT:
			_fail("The transition action '%s' has invalid frame geometry." % transition_action_id)
			return
		if bool(transition_action.loop) or bool(transition_action.interruptible):
			_fail("Transition '%s' must be one-shot and non-interruptible." % transition_action_id)
			return
		if character_package.load_texture(transition_action) == null:
			_fail("The transition texture is missing for '%s'." % transition_action_id)
			return

	for walk_action_id in WALK_ACTION_IDS:
		var walk_action := LoaderScript.load_action(CHARACTER_MANIFEST_PATH, walk_action_id)
		if walk_action.is_empty():
			_fail("The walk action '%s' could not be loaded." % walk_action_id)
			return
		if walk_action.columns != 6 or walk_action.rows != 6 or walk_action.frame_indices.size() != WALK_FRAME_COUNT:
			_fail("The walk action '%s' has invalid frame geometry." % walk_action_id)
			return
		for frame_index in range(WALK_FRAME_COUNT):
			if walk_action.frame_indices[frame_index] != frame_index:
				_fail("The walk action '%s' must preserve its exported frame order." % walk_action_id)
				return
		for blank_frame in WALK_BLANK_FRAMES:
			if walk_action.frame_indices.has(blank_frame):
				_fail("The walk action '%s' includes a blank frame." % walk_action_id)
				return
		if not ResourceLoader.exists(String(walk_action.texture_path)):
			_fail("The walk texture is missing for '%s': %s" % [walk_action_id, walk_action.texture_path])
			return
		if character_package.load_texture(walk_action) == null:
			_fail("The default character package could not load walk action '%s'." % walk_action_id)
			return

	print("Manifest smoke test passed.")
	quit(0)

func _fail(message: String) -> void:
	push_error(message)
	quit(1)
