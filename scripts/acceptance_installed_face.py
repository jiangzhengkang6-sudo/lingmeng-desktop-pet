"""
对已安装并在 8000 端口运行的网关做人脸端到端验收：
注册 3 张主人 -> 主人通过 -> 他人拒绝 -> 删除测试档案。

直接走 HTTP（不修改代码/不重启网关），验证的是用户真实安装形态。
"""
from __future__ import annotations

import json
import sys
import uuid
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"
OWNER_DIR = Path(r"C:\Users\j\Desktop\我的人脸样本")
OTHER_DIR = Path(r"C:\Users\j\Desktop\他人的人脸样本")


def multipart(fields, files):
    boundary = "----acceptance" + uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(str(value).encode())
        body.extend(b"\r\n")
    for field, path in files:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="{field}"; filename="{path.name}"\r\n'.encode()
        )
        body.extend(b"Content-Type: image/jpeg\r\n\r\n")
        body.extend(path.read_bytes())
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def call(method, path, fields=None, files=None):
    data = content_type = None
    if files is not None:
        data, content_type = multipart(fields or {}, files)
    request = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": content_type} if content_type else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def main() -> int:
    owners = sorted(OWNER_DIR.glob("*.jpg"))
    others = sorted(OTHER_DIR.glob("*.jpg"))
    print(f"主人 {len(owners)} 张，他人 {len(others)} 张")

    # 先清掉可能残留的旧档案，保证从干净状态开始
    call("DELETE", "/api/face/profile")

    code, body = call("POST", "/api/face/register", {"name": "owner"},
                      [("images", p) for p in owners[:3]])
    print("注册:", code, body)
    if code != 200 or body.get("sample_count") != 3:
        return 1

    failures = 0
    for image in owners[:3]:
        # 每张验证前重置身份，避免 owner_verified 状态延续影响判定
        call("POST", "/api/identity/reset")
        code, body = call("POST", "/api/face/verify", files=[("image", image)])
        ok = body.get("status") == "owner_verified"
        print(f"  主人 {image.name[:14]} -> {code} {body.get('status')}  {'OK' if ok else 'FAIL'}")
        if not ok:
            failures += 1

    false_accept = 0
    for image in others:
        call("POST", "/api/identity/reset")
        code, body = call("POST", "/api/face/verify", files=[("image", image)])
        accepted = body.get("status") == "owner_verified"
        print(f"  他人 {image.name[:14]} -> {code} {body.get('status')}  {'误识!' if accepted else '拒绝 OK'}")
        if accepted:
            false_accept += 1

    # 清理测试档案与身份状态
    call("DELETE", "/api/face/profile")
    call("POST", "/api/identity/reset")

    print(f"\n主人漏识 {failures} 次，他人误识 {false_accept} 次")
    if failures == 0 and false_accept == 0:
        print("验收通过：主人 3/3，他人 0/5 误识。")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
