$ErrorActionPreference = 'Stop'
$edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$shot = Join-Path $env:TEMP 'ui-pet.png'
if (Test-Path $shot) { Remove-Item -LiteralPath $shot -Force }
$arguments = @(
  '--headless=new',
  '--disable-gpu',
  '--window-size=1440,900',
  "--screenshot=$shot",
  'http://127.0.0.1:5174/'
)
Start-Process -FilePath $edge -ArgumentList $arguments -Wait -WindowStyle Hidden
Get-Item -LiteralPath $shot | Select-Object FullName, Length
