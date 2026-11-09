"""启动已安装的桌宠主程序并等待本地网关就绪。"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

APP = Path(r"C:\Program Files\灵梦桌宠\lingmeng-desktop-pet.exe")
URL = "http://127.0.0.1:8000/api/face/status"


def main() -> int:
    print(f"启动主程序: {APP}")
    subprocess.Popen([str(APP)], cwd=str(APP.parent))
    for second in range(40):
        time.sleep(1)
        try:
            with urllib.request.urlopen(URL, timeout=3) as response:
                if response.status == 200:
                    body = json.loads(response.read().decode("utf-8"))
                    print(f"网关就绪，等待 {second + 1}s")
                    print(json.dumps({
                        "enabled": body.get("enabled"),
                        "configured": body.get("configured"),
                        "has_profile": body.get("has_profile"),
                        "threshold": body.get("similarity_threshold"),
                        "backend": body.get("diagnostics", {}).get("backend"),
                        "models": {
                            k: v.get("path")
                            for k, v in body.get("diagnostics", {}).get("models", {}).items()
                        },
                        "deps": {
                            k: v.get("available")
                            for k, v in body.get("diagnostics", {}).get("dependencies", {}).items()
                        },
                    }, ensure_ascii=False, indent=2))
                    return 0
        except Exception:
            pass
    print("网关在 40 秒内未就绪")
    return 1


if __name__ == "__main__":
    sys.exit(main())

