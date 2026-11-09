# Godot Desktop Pet Client

This folder contains the Godot 4 desktop-pet renderer used by the packaged app.
It includes the first production character package under
  `assets/characters/crimson-elf/`. The original `idle-spritesheet-test.png`
remains available as a regression-test asset.

## MVP behavior

- Transparent, borderless, always-on-top desktop window.
- Drag the visible window with the left mouse button.
- A cached, manifest-driven resource package with separate SpriteSheet bindings
  per action. The default character includes a verified front-facing static
  32-frame idle animation, a thinking animation, six directional walk animations,
  and an idle-to-front-right transition;
  missing actions fall back to `idle`.
- Press `1` through `5` to preview actions; `6` exercises missing action
  fallback.
- Press `F1` through `F6` to preview left, right, front-left, front-right,
  back-left, and back-right walking animations.
- Starting front-right walking from idle automatically plays the
  `transition-idle-to-walk-front-right` transition before the looping walk.
- Use the mouse wheel over the pet to resize the square window from 120px to
  480px. The window snaps to nearby screen edges after dragging.
- The known blank 25th grid cell is excluded. Only frame indices `0` through
  `23` are played.

## Run

From the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run-godot-pet.ps1
```

To open the project in the editor:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run-godot-pet.ps1 -Editor
```

The portable Godot executable is intentionally stored under `tools/godot/` and
is ignored by Git.

The package contract is documented in `docs/角色资源包规范.md`. A package
manifest can register multiple PNG files under `sprite_sheets`; each action
selects one binding with `sheet`.

## Scope

The Tauri/Vue client is the debugging and resource-authoring console. It starts
and stops the Godot process and writes preview state to the local package
directory. The console can restore the default crimson-elf package or import a
user package; Agent, voice, RAG, and permission controls are not connected to
the Godot renderer yet.
