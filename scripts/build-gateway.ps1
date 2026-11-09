param(
  [switch]$Clean
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Get-Sha256Hex {
  # 用 .NET 直接算哈希，不依赖 Get-FileHash（npm 嵌套启动的 PowerShell
  # 会话里该模块 cmdlet 曾出现无法自动加载的问题）。
  param([Parameter(Mandatory = $true)][string]$Path)
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try {
    $stream = [System.IO.File]::OpenRead($Path)
    try {
      return ([System.BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '')
    }
    finally {
      $stream.Dispose()
    }
  }
  finally {
    $sha.Dispose()
  }
}

# MediaPipe/PyInstaller 对含 Unicode 破折号的路径兼容性差，打包时映射到 ASCII 盘符。
$driveLetter = (90..68 |
  ForEach-Object { '{0}:' -f [char]$_ } |
  Where-Object { -not (Test-Path $_) } |
  Select-Object -First 1)

if (-not $driveLetter) {
  throw 'No available drive letter for the gateway packaging workspace.'
}

cmd /c "subst $driveLetter `"$projectRoot`""
if ($LASTEXITCODE -ne 0) {
  throw "Unable to map $driveLetter to the gateway packaging workspace."
}

$pushedLocation = $false
try {
  $workspaceRoot = "$driveLetter\"
  $specPath = Join-Path $workspaceRoot 'backend\desktop-pet-gateway.spec'
  $distPath = Join-Path $workspaceRoot 'backend\dist'
  $workPath = Join-Path $workspaceRoot 'backend\build'
  $distRoot = Join-Path $distPath 'desktop-pet-gateway'

  if ($Clean) {
    Remove-Item -LiteralPath $distPath, $workPath -Recurse -Force -ErrorAction SilentlyContinue
  }

  Push-Location $workspaceRoot
  $pushedLocation = $true

  # 唯一打包通道：一切收集/排除规则以 backend/desktop-pet-gateway.spec 为准。
  & python -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $distPath `
    --workpath $workPath `
    $specPath
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
}
finally {
  if ($pushedLocation) {
    Pop-Location
  }
  cmd /c "subst $driveLetter /D" | Out-Null
}

# ── 产物自校验：关键文件缺失或哈希不一致一律视为构建失败 ──
$realDistRoot = Join-Path $projectRoot 'backend\dist\desktop-pet-gateway'
$exePath = Join-Path $realDistRoot 'desktop-pet-gateway.exe'
$envExampleDstPath = Join-Path $realDistRoot '.env.example'
$envExampleSrcPath = Join-Path $projectRoot '.env.example'

if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
  throw "Gateway executable was not generated: $exePath"
}
if ((Get-Item -LiteralPath $exePath).Length -lt 10MB) {
  throw "Gateway executable is unexpectedly small, PyInstaller output may be incomplete: $exePath"
}
# 应用资源文件统一放到 exe 同目录（Tauri 按 gateway/models、gateway/.env.example 收集）。
$modelsDir = Join-Path $realDistRoot 'models'
New-Item -ItemType Directory -Path $modelsDir -Force | Out-Null

$modelFiles = @(
  'face_detection_yunet_2023mar.onnx',
  'face_recognition_sface_2021dec.onnx'
)

if (-not (Test-Path -LiteralPath $envExampleSrcPath -PathType Leaf)) {
  throw "Gateway .env.example source not found: $envExampleSrcPath"
}
Copy-Item -LiteralPath $envExampleSrcPath -Destination $envExampleDstPath -Force

foreach ($modelFile in $modelFiles) {
  $modelSrcPath = Join-Path $projectRoot (Join-Path 'backend\models' $modelFile)
  $modelDstPath = Join-Path $modelsDir $modelFile
  if (-not (Test-Path -LiteralPath $modelSrcPath -PathType Leaf)) {
    throw "Face model source not found: $modelSrcPath（先运行 python scripts/download_face_models.py）"
  }
  Copy-Item -LiteralPath $modelSrcPath -Destination $modelDstPath -Force
  if (-not (Test-Path -LiteralPath $modelDstPath -PathType Leaf)) {
    throw "Face model is missing from gateway artifact: $modelDstPath"
  }
  $sourceModelHash = (Get-Sha256Hex -Path $modelSrcPath)
  $targetModelHash = (Get-Sha256Hex -Path $modelDstPath)
  if ($sourceModelHash -ne $targetModelHash) {
    throw "Copied face model hash does not match source: $modelFile"
  }
}

if (-not (Test-Path -LiteralPath $envExampleDstPath -PathType Leaf)) {
  throw "Gateway .env.example is missing from artifact: $envExampleDstPath"
}

$fileCount = (Get-ChildItem -LiteralPath $realDistRoot -Recurse -File | Measure-Object).Count
$totalBytes = (Get-ChildItem -LiteralPath $realDistRoot -Recurse -File | Measure-Object Length -Sum).Sum

[pscustomobject]@{
  File = 'desktop-pet-gateway.exe'
  Length = (Get-Item -LiteralPath $exePath).Length
  Hash = (Get-Sha256Hex -Path $exePath)
}
[pscustomobject]@{
  File = 'models/' + $modelFiles[0]
  Length = (Get-Item -LiteralPath (Join-Path $modelsDir $modelFiles[0])).Length
  Hash = (Get-Sha256Hex -Path (Join-Path $modelsDir $modelFiles[0]))
}
[pscustomobject]@{
  File = 'models/' + $modelFiles[1]
  Length = (Get-Item -LiteralPath (Join-Path $modelsDir $modelFiles[1])).Length
  Hash = (Get-Sha256Hex -Path (Join-Path $modelsDir $modelFiles[1]))
}
[pscustomobject]@{
  File = '.env.example'
  Length = (Get-Item -LiteralPath $envExampleDstPath).Length
  Hash = (Get-Sha256Hex -Path $envExampleDstPath)
}
Write-Host ("Gateway artifact verification passed. Files={0}, Size={1:N1} MB" -f $fileCount, ($totalBytes / 1MB))

