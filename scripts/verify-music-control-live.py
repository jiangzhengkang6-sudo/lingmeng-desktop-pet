import json
import time
import urllib.request

base = "http://127.0.0.1:8000"


def call(action: str):
    payload = {
        "session_id": f"music-live-{action}",
        "tool_name": "control_music",
        "arguments": {"action": action},
    }
    request = urllib.request.Request(
        base + "/api/tools/execute",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


for action in ("play", "pause"):
    result = call(action)
    print(action, json.dumps(result, ensure_ascii=False))
    time.sleep(2)
