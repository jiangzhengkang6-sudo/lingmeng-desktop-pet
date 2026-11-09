$ErrorActionPreference = 'Stop'
$source = @'
using System;
using System.Threading.Tasks;
using Windows.Media.Control;

public static class MediaSessionInspector
{
    public static string Describe()
    {
        var manager = GlobalSystemMediaTransportControlsSessionManager.RequestAsync().AsTask().GetAwaiter().GetResult();
        var session = manager.GetCurrentSession();
        if (session == null) return "NO_SESSION";
        var props = session.GetMediaPropertiesAsync().AsTask().GetAwaiter().GetResult();
        var playback = session.GetPlaybackInfo();
        return $"{props.Title}|{playback.PlaybackStatus}|{session.SourceAppUserModelId}";
    }
}
'@
Add-Type -Language CSharp -TypeDefinition $source
[MediaSessionInspector]::Describe()
