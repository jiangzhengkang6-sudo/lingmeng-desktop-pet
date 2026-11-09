param(
  [switch]$Editor
)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$godot = Join-Path $projectRoot 'tools\godot\Godot_v4.7.2-stable_win64.exe'
$petProject = Join-Path $projectRoot 'godot\pet_client'

if (-not (Test-Path -LiteralPath $godot)) {
  throw "Godot was not found at $godot. Download the portable engine before running the pet client."
}

if ($Editor) {
  & $godot --editor --path $petProject
} else {
  & $godot --path $petProject
}
