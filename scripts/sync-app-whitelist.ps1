$ErrorActionPreference = 'Stop'
$target = 'C:\Users\j\AppData\Local\LingMengDesktopPet\.env'
$whitelistLine = 'TOOLS_ALLOWED_APPLICATIONS=QQ音乐=D:\QQMusic\QQMusic.exe'
$lines = Get-Content -LiteralPath $target
$filtered = @($lines | Where-Object { $_ -notmatch '^\s*TOOLS_ALLOWED_APPLICATIONS\s*=' })
$filtered += $whitelistLine
Set-Content -LiteralPath $target -Value $filtered -Encoding UTF8
Get-Content -LiteralPath $target | Where-Object { $_ -match '^\s*TOOLS_ALLOWED_APPLICATIONS\s*=' }

