$ErrorActionPreference = 'Stop'
$oldCode = '{1C89B841-241A-40CD-8C52-4483121F2D44}'
$log = Join-Path $env:TEMP 'uninstall-old.log'
if (Test-Path $log) { Remove-Item -LiteralPath $log -Force }

$argString = '/X ' + $oldCode + ' /quiet /norestart /L*v "' + $log + '"'
Write-Output ("ARGS: " + $argString)
$p = Start-Process -FilePath 'msiexec.exe' -ArgumentList $argString -Wait -PassThru
Write-Output ("UNINSTALL_EXIT=" + $p.ExitCode)

if (Test-Path $log) {
  Write-Output '--- KEY LOG LINES ---'
  Select-String -LiteralPath $log -Pattern 'Error 1|Return value 3|denied|in use|value 3' |
    Select-Object -Last 30 |
    ForEach-Object { $_.Line }
} else {
  Write-Output 'LOG NOT CREATED'
}
