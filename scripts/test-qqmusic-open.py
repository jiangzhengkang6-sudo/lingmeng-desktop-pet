import json
import time
import urllib.error
import urllib.request
from pathlib import Path

base = "http://127.0.0.1:8000"


def request(path: str, payload=None, method="GET"):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc


health = request("/api/health")
print("HEALTH", health["ok"], "IDENTITY", health["identityStatus"])

payload = {
    "session_id": "qqmusic-py-test",
    "tool_name": "open_application",
    "arguments": {"app_name": "QQ音乐"},
}
result = request("/api/tools/execute", payload=payload, method="POST")
print("RESULT", json.dumps(result, ensure_ascii=False))
time.sleep(3)

import subprocess
processes = subprocess.check_output(
    ["powershell", "-NoProfile", "-Command",
     "Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq 'D:\\QQMusic\\QQMusic.exe' } | Select-Object Id,ProcessName,Path | ConvertTo-Json"],
    text=True,
)
print(processes)
