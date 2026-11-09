param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$TauriArguments
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$cargoBin = Join-Path $HOME '.cargo\bin'
$driveLetter = (90..68 |
  ForEach-Object { '{0}:' -f [char]$_ } |
  Where-Object { -not (Test-Path $_) } |
  Select-Object -First 1)

if (Test-Path (Join-Path $cargoBin 'cargo.exe')) {
  $env:Path = "$cargoBin;$env:Path"
}

if (-not $driveLetter) {
  throw 'No available drive letter for the desktop packaging workspace.'
}

& (Join-Path $PSScriptRoot 'build-gateway.ps1')
if ($LASTEXITCODE -ne 0) {
  throw "build-gateway.ps1 失败，退出码 $LASTEXITCODE"
}
Write-Host '=== 阶段 2/3：映射 ASCII 打包盘符 ==='

cmd /c "subst $driveLetter `"$projectRoot`""
if ($LASTEXITCODE -ne 0) {
  throw "Unable to map $driveLetter to the project workspace."
}

try {
  Push-Location "$driveLetter\"
  Write-Host ('=== 阶段 3/3：Tauri NSIS 打包（工作目录 {0}） ===' -f (Get-Location).Path)
  if (-not $env:CARGO_TARGET_DIR) {
    # Keep build outputs out of an older, permission-damaged Cargo cache,
    # while preserving the ASCII path required by the WiX MSI tooling.
    $env:CARGO_TARGET_DIR = "$driveLetter\src-tauri\.tauri-target-user"
  }
  # 发布通道统一使用 NSIS：网关资源约 265MB / 900 个文件，
  # 32 位 WiX light.exe 在该规模下内存崩溃，NSIS 对大文件更稳定。
  Write-Host '执行: npx tauri build --bundles nsis'
  & npx tauri build --bundles nsis @TauriArguments
  Write-Host ('npx tauri build 退出码: ' + $LASTEXITCODE)
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
}
finally {
  Pop-Location
  cmd /c "subst $driveLetter /D" | Out-Null
}
