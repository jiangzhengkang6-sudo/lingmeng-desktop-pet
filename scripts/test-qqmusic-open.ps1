$ErrorActionPreference = 'Stop'

Start-Process -FilePath 'C:\Program Files\灵梦桌宠\lingmeng-desktop-pet.exe'
Write-Output '等待应用和网关启动...'
Start-Sleep -Seconds 16

Get-Process -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -like 'C:\Program Files\灵梦桌宠*' } |
  Select-Object Id, ProcessName, Path |
  Format-Table -AutoSize

$health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 10
Write-Output "HEALTH=$($health.ok)"
Write-Output "IDENTITY=$($health.identityStatus)"

$session = 'qqmusic-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$body = @{
  session_id = $session
  tool_name = 'open_application'
  arguments = @{ app_name = 'QQ音乐' }
} | ConvertTo-Json -Depth 4

$result = Invoke-RestMethod `
  -Uri 'http://127.0.0.1:8000/api/tools/execute' `
  -Method Post `
  -ContentType 'application/json; charset=utf-8' `
  -Body $body `
  -TimeoutSec 20

$result | ConvertTo-Json -Depth 5
Start-Sleep -Seconds 3
$qqMusic = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq 'D:\QQMusic\QQMusic.exe' }
if (-not $qqMusic) { throw '工具调用成功，但未检测到 QQMusic 进程' }
$qqMusic | Select-Object Id, ProcessName, Path | Format-Table -AutoSize

