$ErrorActionPreference = 'Stop'

Start-Process -FilePath 'C:\Program Files\灵梦桌宠\lingmeng-desktop-pet.exe'
Write-Output '等待应用与网关启动...'
Start-Sleep -Seconds 16

Get-Process -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -like 'C:\Program Files\灵梦桌宠*' } |
  Select-Object Id, ProcessName, Path |
  Format-Table -AutoSize

$health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 10
Write-Output "HEALTH=$($health.ok) IDENTITY=$($health.identityStatus)"

$tools = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/tools' -TimeoutSec 10
$tools | Where-Object { $_.name -eq 'control_music' } | ConvertTo-Json -Depth 4

