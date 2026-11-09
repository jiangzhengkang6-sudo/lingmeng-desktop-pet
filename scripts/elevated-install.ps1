$ErrorActionPreference = 'Stop'
$result = Join-Path $env:TEMP 'elevated-install-result.txt'
if (Test-Path $result) { Remove-Item -LiteralPath $result -Force }

$oldCode = '{C48135F6-CBD0-4C47-A141-2E25FA28F296}'
$msi = Join-Path $env:TEMP 'AnimeAgentDesktopPet-0.4.0.msi'

$uninstall = Start-Process -FilePath 'msiexec.exe' `
  -ArgumentList ('/X ' + $oldCode + ' /quiet /norestart') `
  -Wait -PassThru
('UNINSTALL_EXIT=' + $uninstall.ExitCode) | Out-File -LiteralPath $result -Encoding ASCII

Start-Sleep -Seconds 2

$install = Start-Process -FilePath 'msiexec.exe' `
  -ArgumentList ('/I "' + $msi + '" /quiet /norestart') `
  -Wait -PassThru
('INSTALL_EXIT=' + $install.ExitCode) | Out-File -LiteralPath $result -Append -Encoding ASCII
