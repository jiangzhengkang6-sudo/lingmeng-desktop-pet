import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.controlled_tools import ControlledToolService

service = ControlledToolService(
    r"C:\Users\j\AppData\Local\LingMengDesktopPet\debug-music.sqlite3",
    allowed_applications={"QQ音乐": r"D:\QQMusic\QQMusic.exe"},
)

try:
    print("windows")
    windows = service._find_application_windows(r"D:\QQMusic\QQMusic.exe")
    print(json.dumps(windows, ensure_ascii=False))
    print("play validation")
    print(service._validate_arguments("control_music", {"action": "play"}))
    print("send key")
    ControlledToolService._send_music_play_pause(windows[0][0])
except Exception:
    traceback.print_exc()

