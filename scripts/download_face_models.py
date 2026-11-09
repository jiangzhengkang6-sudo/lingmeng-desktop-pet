"""
下载 OpenCV 人脸身份识别所需的两个离线 ONNX 模型：

- face_detection_yunet_2023mar.onnx：YuNet 人脸检测（提供对齐用关键点）
- face_recognition_sface_2021dec.onnx：SFace 身份嵌入（128 维特征）

模型来自官方 opencv_zoo 仓库（Apache-2.0）。国内直连 GitHub 常被重置，
因此依次尝试官方地址与多个镜像；下载后校验文件头（ONNX/protobuf）与
最小字节数，避免把镜像的 HTML 错误页当成模型。

用法：
    python scripts/download_face_models.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = PROJECT_ROOT / "backend" / "models"

GITHUB_BASE = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
)
MIRROR_PREFIXES = [
    "",  # 官方直连
    "https://ghfast.top/",
    "https://gh-proxy.com/",
    "https://ghproxy.net/",
    "https://mirror.ghproxy.com/",
    "https://gh.llkk.cc/",
    "https://github.moeyy.xyz/",
    "https://ghps.cc/",
]

MODELS = {
    "face_detection_yunet_2023mar.onnx": {
        "zoo_path": "face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "min_bytes": 200_000,
    },
    "face_recognition_sface_2021dec.onnx": {
        "zoo_path": "face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "min_bytes": 30_000_000,
    },
}


def looks_like_onnx(path: Path, min_bytes: int) -> bool:
    """ONNX 是 protobuf，文件头不是 HTML；用大小与文件头粗校验。"""
    if not path.is_file() or path.stat().st_size < min_bytes:
        return False
    with path.open("rb") as handle:
        head = handle.read(16)
    if head.lstrip().lower().startswith(b"<!doctype html") or head.lstrip().lower().startswith(b"<html"):
        return False
    return True


def download(url: str, target: Path, min_bytes: int, timeout: int = 120) -> bool:
    print(f"  尝试: {url}")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            with tempfile.NamedTemporaryFile(delete=False, dir=target.parent) as tmp:
                tmp_path = Path(tmp.name)
            try:
                with tmp_path.open("wb") as output:
                    while True:
                        chunk = response.read(1 << 20)
                        if not chunk:
                            break
                        output.write(chunk)
                if looks_like_onnx(tmp_path, min_bytes):
                    os.replace(tmp_path, target)
                    print(f"    成功，{target.stat().st_size / 1_048_576:.1f} MB")
                    return True
                print("    下载内容不是有效模型（太小或为 HTML），换下一个镜像")
            finally:
                tmp_path.unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001 - 逐个镜像尝试，打印原因即可
        print(f"    失败: {type(exc).__name__}: {exc}")
    return False


def main() -> int:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    failed = []
    for filename, spec in MODELS.items():
        target = MODEL_DIR / filename
        if looks_like_onnx(target, spec["min_bytes"]):
            print(f"已存在且有效，跳过: {filename}")
            continue

        print(f"下载 {filename} ...")
        official_url = GITHUB_BASE + spec["zoo_path"]
        urls = [prefix + official_url for prefix in MIRROR_PREFIXES]
        if not any(download(url, target, spec["min_bytes"]) for url in urls):
            failed.append(filename)

    if failed:
        print("\n以下模型下载失败，请开启代理/梯子后重试：")
        for name in failed:
            print(f"  - {name}")
        return 1

    print("\n全部人脸模型就绪，位于 backend/models/。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
