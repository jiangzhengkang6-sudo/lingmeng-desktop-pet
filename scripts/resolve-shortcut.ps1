$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$shortcutPath = 'C:\ProgramData\Microsoft\Windows\Start Menu\Programs\腾讯软件\QQ音乐\QQ音乐.lnk'
$shortcut = $shell.CreateShortcut($shortcutPath)
[pscustomobject]@{
  TargetPath = $shortcut.TargetPath
  Arguments = $shortcut.Arguments
  WorkingDirectory = $shortcut.WorkingDirectory
} | Format-List
