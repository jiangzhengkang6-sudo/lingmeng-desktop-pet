param(
  [Parameter(Mandatory = $true)]
  [string]$ProjectRoot,
  [string]$InstallDir = "C:\Program Files\灵梦桌宠"
)

$ErrorActionPreference = "Stop"

function Write-Step {
  param([string]$Message)
  Write-Host "`n=== $Message ==="
}

function Get-Sha256Hex {
  # 用 .NET 直接算哈希，不依赖 Get-FileHash（某些受限/嵌套 PowerShell
  # 会话里该模块 cmdlet 无法自动加载）。
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

function Assert-Administrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "热更新需要写入 Program Files，请使用管理员身份的 PowerShell 重新执行本脚本。"
  }
}

function Get-FileManifest {
  param(
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$RelativePath
  )

  $path = Join-Path $Root $RelativePath
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
    throw "关键文件不存在: $path"
  }

  $item = Get-Item -LiteralPath $path
  $hash = Get-Sha256Hex -Path $path
  [pscustomobject]@{
    RelativePath = $RelativePath
    FullName     = $item.FullName
    Length       = $item.Length
    Hash         = $hash
  }
}

function Assert-TargetMatchesManifest {
  param(
    [Parameter(Mandatory = $true)][string]$TargetRoot,
    [Parameter(Mandatory = $true)][pscustomobject[]]$Manifest
  )

  $results = @()
  foreach ($expected in $Manifest) {
    $targetPath = Join-Path $TargetRoot $expected.RelativePath
    if (-not (Test-Path -LiteralPath $targetPath -PathType Leaf)) {
      throw "替换后关键文件仍不存在: $targetPath"
    }

    $targetItem = Get-Item -LiteralPath $targetPath
    $targetHash = Get-Sha256Hex -Path $targetPath
    $hashMatches = ($targetHash -eq $expected.Hash -and $targetItem.Length -eq $expected.Length)
    $results += [pscustomobject]@{
      RelativePath = $expected.RelativePath
      Length       = $targetItem.Length
      ExpectedSize = $expected.Length
      HashMatch    = $hashMatches
    }
    if (-not $hashMatches) {
      throw "关键文件替换失败或被进程锁阻止: $targetPath"
    }
  }

  $results | Format-Table -AutoSize
}

function Stop-RequiredProcesses {
  $processNames = @("desktop-pet-gateway", "lingmeng-desktop-pet")
  $processes = Get-Process -Name $processNames -ErrorAction SilentlyContinue
  if ($processes) {
    Write-Host "停止桌宠与网关进程..."
    $processes | Stop-Process -Force
    foreach ($name in $processNames) {
      Wait-Process -Name $name -Timeout 15 -ErrorAction SilentlyContinue
    }
  }

  $remaining = Get-Process -Name $processNames -ErrorAction SilentlyContinue
  if ($remaining) {
    $remaining | Select-Object Name, Id, Path | Format-Table -AutoSize
    throw "仍有进程占用待替换文件，已中止热更新。"
  }
}

Assert-Administrator

$projectItem = Get-Item -LiteralPath $ProjectRoot
$ProjectRoot = $projectItem.FullName
if (-not (Test-Path -LiteralPath $InstallDir -PathType Container)) {
  throw "安装目录不存在: $InstallDir"
}

Write-Step "热更新前检查"
Write-Host "项目目录: $ProjectRoot"
Write-Host "安装目录: $InstallDir"
Stop-RequiredProcesses

# ── 1. 替换 Godot 脚本（目录不存在时跳过，不影响网关修复） ──
$godotSrc = Join-Path $ProjectRoot "godot\pet_client\scripts"
$godotDst = Join-Path $InstallDir "godot\pet_client\scripts"
if ((Test-Path -LiteralPath $godotSrc -PathType Container) -and
    (Test-Path -LiteralPath $godotDst -PathType Container)) {
  Write-Step "更新 Godot 脚本"
  Copy-Item -Path (Join-Path $godotSrc "*") -Destination $godotDst -Recurse -Force
  Write-Host "Godot 脚本已更新"
}

# ── 2. 替换 Gateway：停进程 → 覆盖 → 校验哈希/字节数 ──
Write-Step "更新 Gateway"
$gatewaySrc = Join-Path $ProjectRoot "backend\dist\desktop-pet-gateway"
$gatewayDst = Join-Path $InstallDir "gateway"
if (-not (Test-Path -LiteralPath $gatewaySrc -PathType Container)) {
  throw "Gateway 构建产物不存在: $gatewaySrc"
}
if (-not (Test-Path -LiteralPath $gatewayDst -PathType Container)) {
  throw "安装目录中的 gateway 不存在: $gatewayDst"
}

$gatewayManifest = @(
  Get-FileManifest -Root $gatewaySrc -RelativePath "desktop-pet-gateway.exe"
  Get-FileManifest -Root $gatewaySrc -RelativePath "models\face_detection_yunet_2023mar.onnx"
  Get-FileManifest -Root $gatewaySrc -RelativePath "models\face_recognition_sface_2021dec.onnx"
)

& robocopy $gatewaySrc $gatewayDst /E /IS /IT /IM /MT:4 /R:2 /W:2
$robocopyExitCode = $LASTEXITCODE
if ($robocopyExitCode -ge 8) {
  throw "robocopy 替换 Gateway 失败，退出码: $robocopyExitCode"
}
Write-Host "robocopy 退出码: $robocopyExitCode（0-7 为成功）"
Assert-TargetMatchesManifest -TargetRoot $gatewayDst -Manifest $gatewayManifest

# ── 3. 替换主程序 exe（存在时才更新，并立即校验） ──
$exeSrc = Join-Path $ProjectRoot "src-tauri\target\release\lingmeng-desktop-pet.exe"
$exeDst = Join-Path $InstallDir "lingmeng-desktop-pet.exe"
if (Test-Path -LiteralPath $exeSrc -PathType Leaf) {
  Write-Step "更新主程序"
  $exeSourceRoot = Split-Path -Parent $exeSrc
  $exeManifest = @(Get-FileManifest -Root $exeSourceRoot -RelativePath "lingmeng-desktop-pet.exe")
  Copy-Item -LiteralPath $exeSrc -Destination $exeDst -Force
  Assert-TargetMatchesManifest -TargetRoot (Split-Path -Parent $exeDst) -Manifest $exeManifest | Out-Null
  Write-Host "主程序 exe 已更新并通过哈希校验"
} else {
  Write-Host "未找到主程序构建产物，跳过主程序 exe 更新。"
}

Write-Step "热更新完成"
Write-Host "请重新启动应用，并访问 /api/face/status 检查 configured 与 diagnostics 字段。"

