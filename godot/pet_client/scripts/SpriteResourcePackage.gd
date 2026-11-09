class_name SpriteResourcePackage
extends RefCounted

const ManifestLoaderScript := preload("res://scripts/SpriteManifestLoader.gd")

var manifest_path := ""
var manifest: Dictionary = {}
var _texture_cache: Dictionary = {}

func open(path: String) -> bool:
	manifest_path = path
	manifest = ManifestLoaderScript.load_manifest(path)
	_texture_cache.clear()
	return not manifest.is_empty()

func load_action(action_id: String, report_errors: bool = true) -> Dictionary:
	if manifest.is_empty():
		return {}
	return ManifestLoaderScript.load_action_from_manifest(manifest, manifest_path, action_id, report_errors)

func load_action_with_fallback(action_id: String, fallback_action_id: String = "idle") -> Dictionary:
	var action := load_action(action_id, false)
	if not action.is_empty():
		return action

	if action_id != fallback_action_id:
		var fallback := load_action(fallback_action_id)
		if not fallback.is_empty():
			fallback["requested_action_id"] = action_id
			fallback["fallback"] = true
			return fallback

	return {}

func load_texture(action: Dictionary) -> Texture2D:
	var texture_path := String(action.get("texture_path", ""))
	if texture_path.is_empty():
		return null
	if _texture_cache.has(texture_path):
		return _texture_cache[texture_path] as Texture2D

	var texture: Texture2D = null
	if (texture_path.begins_with("res://") or texture_path.begins_with("uid://")) and ResourceLoader.exists(texture_path):
		texture = ResourceLoader.load(texture_path, "Texture2D") as Texture2D
	if texture == null:
		var file_path := ProjectSettings.globalize_path(texture_path) if texture_path.begins_with("res://") else texture_path
		var image := Image.load_from_file(file_path)
		if image != null and not image.is_empty():
			texture = ImageTexture.create_from_image(image)
	if texture != null:
		_texture_cache[texture_path] = texture
	return texture
