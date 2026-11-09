#Requires -Version 5.1
# Docker Desktop 卡在“Starting the Docker Engine...”时的安全修复脚本。
# 本脚本不会删除容器、镜像、数据卷或 WSL/VHDX 磁盘文件。
$ErrorActionPreference = 'Stop'

Write-Host '正在停止 Docker Desktop 相关进程...'
Get-Process -ErrorAction SilentlyContinue |
  Where-Object { $_.ProcessName -like 'Docker*' -or $_.ProcessName -like 'com.docker*' -or $_.ProcessName -eq 'docker-sandbox' -or $_.ProcessName -eq 'vpnkit-bridge' } |
  Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

Write-Host '正在关闭 WSL2 虚拟机...'
wsl.exe --shutdown
Start-Sleep -Seconds 8

$wslConfig = Join-Path $env:USERPROFILE '.wslconfig'
if (-not (Test-Path $wslConfig)) {
  Write-Host '正在为 Docker Desktop 的 WSL2 后端写入保守资源配置...'
  $wslLines = @(
    '[wsl2]',
    'memory=8GB',
    'processors=4',
    'swap=2GB',
    'localhostForwarding=true',
    'debugConsole=false',
    'vmIdleTimeout=60000',
    '',
    '[experimental]',
    'autoMemoryReclaim=gradual',
    'sparseVhd=true'
  )
  $wslLines | Set-Content -Path $wslConfig -Encoding ASCII
} else {
  Write-Host ".wslconfig 已存在，保留现有配置：$wslConfig"
}

Write-Host '正在启动 Docker Desktop...'
$dockerDesktop = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
if (Test-Path $dockerDesktop) { Start-Process $dockerDesktop } else { throw '未找到 Docker Desktop 可执行文件。' }

Write-Host '等待 Docker 引擎就绪...'
$ready = $false
for ($i = 0; $i -lt 36; $i++) {
  Start-Sleep -Seconds 5
  docker info *> $null
  if ($LASTEXITCODE -eq 0) { $ready = $true; break }
}
if (-not $ready) { throw 'Docker 引擎在 180 秒内未就绪，请检查 Docker Desktop 日志。' }

docker version
docker info --format 'Server={{.ServerVersion}} Containers={{.Containers}} Images={{.Images}}'
Write-Host 'Docker Desktop 已就绪。'
