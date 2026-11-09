$ErrorActionPreference = 'Stop'
$source = @"
using System;
using System.Threading.Tasks;
using Windows.Media.Control;

public static class MediaSessionInspector
{
    public static async Task<string> DescribeAsync()
    {
        var manager = GlobalSystemMediaTransportControlsSessionManager.RequestAsync().GetAwaiter().GetResult();
        var session = manager.GetCurrentSession();
        if (session == null) return "NO_SESSION";
        var props = session.GetMediaPropertiesAsync().GetAwaiter().GetResult();
        var playback = session.GetPlaybackInfo();
        return $"{props.Title}|{playback.PlaybackStatus}";
    }
}
"@
Add-Type -Language CSharp -TypeDefinition $source -ReferencedAssemblies @(
  'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\System.Runtime.WindowsRuntime.dll'
  'C:\Program Files (x86)\Windows Kits\10\UnionMetadata\10.0.26100.0\Windows.winmd'
)
[MediaSessionInspector]::DescribeAsync()
