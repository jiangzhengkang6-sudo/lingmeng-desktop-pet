class_name SpriteManifestLoader
extends RefCounted

static func load_manifest(manifest_path: String, report_errors: bool = true) -> Dictionary:
	var file := FileAccess.open(manifest_path, FileAccess.READ)
	if file == null:
		if report_errors:
			push_error("Unable to open sprite manifest: %s" % manifest_path)
		return {}

	var json := JSON.new()
	if json.parse(file.get_as_text()) != OK or not json.data is Dictionary:
		if report_errors:
			push_error("Invalid sprite manifest JSON: %s" % manifest_path)
		return {}

	return json.data

static func load_action_from_manifest(
	manifest: Dictionary,
	manifest_path: String,
	action_id: String,
	report_errors: bool = true
) -> Dictionary:
	var actions: Dictionary = manifest.get("actions", {})
	var raw_action: Variant = actions.get(action_id)
	if not raw_action is Dictionary:
		if report_errors:
			push_error("Action '%s' is not registered." % action_id)
		return {}

	var action: Dictionary = raw_action
	var sheets: Dictionary = manifest.get("sprite_sheets", {})
	if sheets.is_empty():
		var legacy_sheet: Variant = manifest.get("sprite_sheet")
		if legacy_sheet is Dictionary:
			sheets = {"legacy": legacy_sheet}

	var sheet_key := String(action.get("sheet", ""))
	var sheet: Dictionary = {}
	if not sheet_key.is_empty():
		var registered_sheet: Variant = sheets.get(sheet_key)
		if registered_sheet is Dictionary:
			sheet = registered_sheet
		else:
			for candidate in sheets.values():
				if candidate is Dictionary and String(candidate.get("file", "")) == sheet_key:
					sheet = candidate
					sheet_key = String(candidate.get("file", ""))
					break
	elif sheets.size() == 1:
		sheet_key = String(sheets.keys()[0])
		sheet = sheets[sheet_key]

	if sheet.is_empty():
		if report_errors:
			push_error("Action '%s' does not reference a registered SpriteSheet." % action_id)
		return {}

	var frame_count := int(sheet.get("frame_count", 0))
	var valid_frames := _to_int_array(sheet.get("valid_frame_indices", []))
	var blank_frames := _to_int_array(sheet.get("blank_frame_indices", []))
	var frame_indices: Array[int] = []
	for raw_frame in _to_int_array(action.get("frame_indices", [])):
		var frame := int(raw_frame)
		if frame < 0 or frame >= frame_count:
			continue
		if blank_frames.has(frame):
			continue
		if not valid_frames.is_empty() and not valid_frames.has(frame):
			continue
		frame_indices.append(frame)

	if frame_indices.is_empty():
		if report_errors:
			push_error("Action '%s' has no valid frames." % action_id)
		return {}

	return {
		"action_id": action_id,
		"sheet_key": sheet_key,
		"texture_path": manifest_path.get_base_dir().path_join(String(sheet.get("file", ""))),
		"frame_width": int(sheet.get("frame_width", 0)),
		"frame_height": int(sheet.get("frame_height", 0)),
		"columns": int(sheet.get("columns", 1)),
		"rows": int(sheet.get("rows", 1)),
		"frame_indices": frame_indices,
		"movement_frame_indices": _to_int_array(action.get("movement_frame_indices", [])),
		"fps": maxf(float(action.get("fps", 8.0)), 1.0),
		"loop": bool(action.get("loop", true)),
		"interruptible": bool(action.get("interruptible", true)),
		"anchor": String(action.get("anchor", sheet.get("anchor", "bottom-center"))),
	}

static func _to_int_array(value: Variant) -> Array[int]:
	var result: Array[int] = []
	if not value is Array:
		return result
	for item in value:
		if item is int or item is float:
			result.append(int(item))
	return result

static func load_action(
	manifest_path: String,
	action_id: String,
	report_errors: bool = true
) -> Dictionary:
	var manifest := load_manifest(manifest_path, report_errors)
	if manifest.is_empty():
		return {}
	return load_action_from_manifest(manifest, manifest_path, action_id, report_errors)

static func load_action_with_fallback(
	manifest_path: String,
	action_id: String,
	fallback_action_id: String = "idle"
) -> Dictionary:
	var action := load_action(manifest_path, action_id, false)
	if not action.is_empty():
		return action

	if action_id != fallback_action_id:
		var fallback := load_action(manifest_path, fallback_action_id)
		if not fallback.is_empty():
			fallback["requested_action_id"] = action_id
			fallback["fallback"] = true
			return fallback

	return {}
