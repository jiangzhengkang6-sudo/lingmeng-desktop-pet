$ErrorActionPreference = 'Stop'
$edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$profile = Join-Path $env:TEMP 'edge-ui-debug-profile'
New-Item -ItemType Directory -Force -Path $profile | Out-Null
$arguments = @(
  '--headless=new',
  '--remote-debugging-port=9223',
  "--user-data-dir=$profile",
  '--window-size=1440,900',
  'http://127.0.0.1:5174/'
)
$process = Start-Process -FilePath $edge -ArgumentList $arguments -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 3
$process.Id
