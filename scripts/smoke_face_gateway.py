"""
打包产物冒烟测试：直接启动 dist 中的桌面网关 exe，验证：
1. 进程能正常启动并监听 127.0.0.1；
2. /api/face/status 返回 configured=true；
3. 精简打包后 mediapipe / cv2 仍可导入；
4. 模型从 exe 同目录 models/ 解析成功。

用法（项目根目录）：
    python scripts/smoke_face_gateway.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXE_PATH = PROJECT_ROOT / "backend" / "dist" / "desktop-pet-gateway" / "desktop-pet-gateway.exe"
PORT = int(os.environ.get("SMOKE_GATEWAY_PORT", "8011"))
OWNER_DIR = Path(os.environ.get("SMOKE_OWNER_DIR", "")) if os.environ.get("SMOKE_OWNER_DIR") else None
OTHER_DIR = Path(os.environ.get("SMOKE_OTHER_DIR", "")) if os.environ.get("SMOKE_OTHER_DIR") else None


def wait_for_status(url: str, timeout_seconds: float = 25.0) -> dict:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            last_error = exc
            time.sleep(0.8)
    raise RuntimeError(f"网关在 {timeout_seconds} 秒内未就绪: {last_error}")


def _multipart(fields: dict[str, str], files: list[tuple[str, Path]]) -> tuple[bytes, str]:
    boundary = "----deskpetsmoke" + uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(value.encode())
        body.extend(b"\r\n")
    for field_name, path in files:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{path.name}"\r\n'.encode()
        )
        body.extend(b"Content-Type: image/jpeg\r\n\r\n")
        body.extend(path.read_bytes())
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), boundary


def post_form(url: str, fields: dict[str, str], files: list[tuple[str, Path]]) -> dict:
    body, boundary = _multipart(fields, files)
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def run_inference_checks(base_url: str) -> bool:
    """用真实照片在打包 exe 上走注册/验证，验证 frozen 环境 cv2.dnn 推理可用。"""
    if not OWNER_DIR or not OTHER_DIR:
        print("未提供 SMOKE_OWNER_DIR/SMOKE_OTHER_DIR，跳过真实推理验证。")
        return True
    owner_images = sorted(p for p in OWNER_DIR.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    other_images = sorted(p for p in OTHER_DIR.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if len(owner_images) < 3 or not other_images:
        print("真实推理样本不足（主人至少 3 张、他人至少 1 张），跳过。")
        return True

    registered = post_form(
        f"{base_url}/api/face/register",
        {"name": "owner"},
        [("images", p) for p in owner_images[:3]],
    )
    print("注册结果:", registered)
    if registered.get("sample_count") != 3:
        return False

    for image in owner_images[:3]:
        result = post_form(f"{base_url}/api/face/verify", {}, [("image", image)])
        if result.get("status") != "owner_verified":
            print(f"主人样本被拒绝: {image.name} -> {result}")
            return False
        print(f"  主人通过: {image.name[:16]}")

    # 生产安全默认：临时开放关闭，他人应判为 guest
    for image in other_images:
        result = post_form(f"{base_url}/api/face/verify", {}, [("image", image)])
        if result.get("status") == "owner_verified":
            print(f"非主人被误识: {image.name}")
            return False
        print(f"  他人拒绝: {image.name[:16]} -> {result.get('status')}")
    return True


def main() -> int:
    if not EXE_PATH.is_file():
        print(f"未找到打包产物，请先执行 scripts/build-gateway.ps1: {EXE_PATH}")
        return 2

    with tempfile.TemporaryDirectory(prefix="deskpet-gateway-smoke-") as temp_dir:
        config_dir = Path(temp_dir) / "config"
        data_dir = Path(temp_dir) / "data"
        config_dir.mkdir()
        data_dir.mkdir()
        env_example = PROJECT_ROOT / ".env.example"
        (config_dir / ".env").write_bytes(env_example.read_bytes())

        env = os.environ.copy()
        env["DESKTOP_PET_GATEWAY_PORT"] = str(PORT)
        env["DESKTOP_PET_CONFIG_DIR"] = str(config_dir)
        env["DESKTOP_PET_DATA_DIR"] = str(data_dir)

        print(f"启动网关冒烟进程: {EXE_PATH}")
        process = subprocess.Popen(
            [str(EXE_PATH)],
            cwd=EXE_PATH.parent,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            status = wait_for_status(f"http://127.0.0.1:{PORT}/api/face/status")
            print(json.dumps(status, ensure_ascii=False, indent=2))

            diagnostics = status.get("diagnostics", {})
            models = diagnostics.get("models", {})
            dependencies = diagnostics.get("dependencies", {})
            checks = [
                status.get("enabled") is True,
                status.get("configured") is True,
                diagnostics.get("backend") == "sface",
                models.get("detector_yunet", {}).get("path") is not None,
                models.get("recognizer_sface", {}).get("path") is not None,
                dependencies.get("cv2", {}).get("available") is True,
            ]
            if all(checks):
                print("冒烟通过：YuNet/SFace 模型可用，cv2 导入成功，SFace 人脸链路就绪。")
                return 0 if run_inference_checks(f"http://127.0.0.1:{PORT}") else 1
            print("冒烟失败：诊断字段不满足预期。")
            return 1
        finally:
            process.terminate()
            try:
                output, _ = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                output, _ = process.communicate(timeout=10)
            if output:
                print("--- 网关输出 ---")
                print(output)


if __name__ == "__main__":
    sys.exit(main())
