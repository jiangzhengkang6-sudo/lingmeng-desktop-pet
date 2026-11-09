extends SceneTree

const PackageScript := preload("res://scripts/SpriteResourcePackage.gd")
const SOURCE_TEXTURE_PATH := "res://assets/testing/idle-spritesheet-test.png"
const PACKAGE_DIRECTORY := "user://external-resource-package-smoke"
const MANIFEST_PATH := PACKAGE_DIRECTORY + "/manifest.json"
const TEXTURE_PATH := PACKAGE_DIRECTORY + "/sheet-0.png"

func _init() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(PACKAGE_DIRECTORY))
	if DirAccess.copy_absolute(ProjectSettings.globalize_path(SOURCE_TEXTURE_PATH), ProjectSettings.globalize_path(TEXTURE_PATH)) != OK:
		_fail("Unable to prepare the external SpriteSheet.")
		return

	var manifest := {
		"schema_version": "1.0",
		"name": "external-resource-package-smoke",
		"version": "0.1.0",
		"canvas": {"width": 720, "height": 720, "background": "transparent"},
		"sprite_sheets": {
			"idle": {
				"file": "sheet-0.png",
				"width": 3600,
				"height": 3600,
				"frame_width": 720,
				"frame_height": 720,
				"columns": 5,
				"rows": 5,
				"frame_count": 25,
				"valid_frame_indices": [0, 1],
				"blank_frame_indices": [],
				"anchor": "bottom-center",
			},
		},
		"actions": {
			"idle": {
				"id": "idle",
				"label": "External idle",
				"sheet": "idle",
				"frame_indices": [0, 1],
				"fps": 8,
				"loop": true,
				"interruptible": true,
				"anchor": "bottom-center",
			},
		},
	}
	var file := FileAccess.open(MANIFEST_PATH, FileAccess.WRITE)
	if file == null:
		_fail("Unable to write the external manifest.")
		return
	file.store_string(JSON.stringify(manifest))
	file.close()

	var package = PackageScript.new()
	if not package.open(MANIFEST_PATH):
		_fail("Unable to open the external resource package.")
		return
	var action: Dictionary = package.load_action_with_fallback("idle")
	if package.load_texture(action) == null:
		_fail("Unable to load an external SpriteSheet texture.")
		return

	print("External resource package smoke test passed.")
	quit(0)

func _fail(message: String) -> void:
	push_error(message)
	quit(1)
