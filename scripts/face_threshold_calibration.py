"""
人脸阈值标定实验脚本（迭代方案 P1-1）。

用法（在项目根目录执行）：

    python scripts/face_threshold_calibration.py \
      --owner samples/face/owner \
      --others samples/face/others \
      --report runtime/logs/face-calibration.json

目录要求：
- owner：主人 5 张以上照片，覆盖不同表情、角度、光照；
- others：非主人 5 张以上照片（每人 1 张即可，也可多人多张）。

脚本完全离线运行，只读取本地图片并输出相似度分布；当主人最低分与他人
最高分的 gap 不足时会明确提示“当前几何关键点方案区分度不足，需要换
SFace / InsightFace 等身份嵌入模型”。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.face_calibration import calibrate_similarity  # noqa: E402
from backend.app.face_recognition import (  # noqa: E402
    SFACE_MODEL_FILENAME,
    SFaceFaceEngine,
    YUNET_MODEL_FILENAME,
    resolve_model_path,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def list_images(directory: Path) -> list[Path]:
    return sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def extract_features(image_paths: list[Path], engine: MediaPipeFaceEngine) -> list[np.ndarray]:
    features: list[np.ndarray] = []
    for image_path in image_paths:
        feature = engine.extract_feature_from_image(image_path.read_bytes())
        features.append(feature)
        print(f"  已提取特征: {image_path.name}")
    return features


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="本地人脸相似度阈值标定")
    parser.add_argument("--owner", required=True, type=Path, help="主人样本目录")
    parser.add_argument("--others", required=True, type=Path, help="他人样本目录")
    parser.add_argument("--detector", default=None, help="YuNet ONNX 路径（缺省自动解析）")
    parser.add_argument("--recognizer", default=None, help="SFace ONNX 路径（缺省自动解析）")
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="可选：把完整分布写入 JSON 报告文件",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    owner_dir = args.owner.resolve()
    others_dir = args.others.resolve()
    if not owner_dir.is_dir():
        print(f"主人样本目录不存在: {owner_dir}")
        return 2
    if not others_dir.is_dir():
        print(f"他人样本目录不存在: {others_dir}")
        return 2

    owner_images = list_images(owner_dir)
    other_images = list_images(others_dir)
    print(f"主人样本 {len(owner_images)} 张，他人样本 {len(other_images)} 张")
    if len(owner_images) < 5 or len(other_images) < 5:
        print("警告：方案要求主人/他人各至少 5 张，样本不足时结论不可靠。")

    models_dir = PROJECT_ROOT / "backend" / "models"
    detector_path = args.detector or resolve_model_path(
        models_dir / YUNET_MODEL_FILENAME, None, YUNET_MODEL_FILENAME
    )
    recognizer_path = args.recognizer or resolve_model_path(
        models_dir / SFACE_MODEL_FILENAME, None, SFACE_MODEL_FILENAME
    )
    engine = SFaceFaceEngine(detector_path, recognizer_path)

    print("提取主人特征...")
    owner_features = extract_features(owner_images, engine)
    print("提取他人特征...")
    impostor_features = extract_features(other_images, engine)

    result = calibrate_similarity(owner_features, impostor_features).to_dict()
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    result["owner_files"] = [path.name for path in owner_images]
    result["impostor_files"] = [path.name for path in other_images]
    result["backend"] = "sface"
    result["detector_path"] = str(Path(detector_path).resolve())
    result["recognizer_path"] = str(Path(recognizer_path).resolve())

    print("\n=== 相似度分布 ===")
    for label, key in (("主人（留一法）", "owner"), ("他人", "impostor")):
        dist = result[key]
        print(
            f"{label}: min={dist['min']:.4f} max={dist['max']:.4f} "
            f"mean={dist['mean']:.4f} std={dist['std']:.4f} n={dist['count']}"
        )
    print(f"gap（主人最低分 - 他人最高分）= {result['gap']:.4f}")
    if result["separable"]:
        print(f"两类分布可分，建议阈值取中点: {result['recommended_threshold']:.4f}")
    else:
        print("结论：gap 不足或分布重叠，当前样本下身份阈值无法可靠设定。")
        print("可先增加样本复标；仍不可分则换用更强的身份嵌入（如 InsightFace）。")

    if args.report:
        report_path = args.report.resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n完整报告已写入: {report_path}")

    return 0 if result["separable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
