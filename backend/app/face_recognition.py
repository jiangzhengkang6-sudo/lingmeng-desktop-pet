"""
本地人脸识别身份认证适配器。

基于 MediaPipe FaceLandmarker 提取人脸关键点，
将关键点归一化后计算特征向量，用余弦相似度做 1:1 人脸验证。
完全离线运行，不依赖任何云服务。
"""
from __future__ import annotations

import base64
import importlib
import json
import math
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import List, Sequence

import numpy as np

from .identity import IdentitySnapshot, IdentityService, VoiceprintAdapter  # noqa: F401


# ── 人脸模型文件名 ────────────────────────────────────────────
# SFace 身份识别链路（P1-2 切换后的默认方案）
YUNET_MODEL_FILENAME = "face_detection_yunet_2023mar.onnx"
SFACE_MODEL_FILENAME = "face_recognition_sface_2021dec.onnx"
# MediaPipe 关键点（仅保留给未来的实时表情/注意力感知，身份认证不再使用）
LANDMARKER_MODEL_FILENAME = "face_landmarker.task"

# 向后兼容别名
FACE_MODEL_FILENAME = LANDMARKER_MODEL_FILENAME

SFACE_FEATURE_DIM = 128
LANDMARKER_FEATURE_DIM = 478 * 3
# 当前默认身份引擎输出维度
FEATURE_DIM = SFACE_FEATURE_DIM


@dataclass(frozen=True)
class FaceModelCandidate:
    """人脸模型的一个候选路径。"""

    source: str
    path: Path


@dataclass(frozen=True)
class FaceDependencyStatus:
    """可选人脸依赖的导入诊断。"""

    module: str
    available: bool
    version: str | None = None
    error: str | None = None


def face_model_candidates(
    requested_path: str | Path,
    config_directory: str | Path | None = None,
    filename: str = LANDMARKER_MODEL_FILENAME,
) -> list[FaceModelCandidate]:
    """
    按优先级列用人脸模型候选路径。

    打包环境下即使配置文件指向 %LOCALAPPDATA% 中不存在的路径，也会继续检查
    gateway exe 同目录、_internal 与 PyInstaller 解包目录。
    """
    requested = Path(requested_path)
    candidates: list[FaceModelCandidate] = []
    seen: set[str] = set()

    def add(source: str, path: str | Path) -> None:
        candidate_path = Path(path)
        if not candidate_path.is_absolute():
            candidate_path = Path.cwd() / candidate_path
        candidate_path = candidate_path.resolve(strict=False)
        # Windows 文件系统默认大小写不敏感，诊断去重时也归一化大小写。
        key = str(candidate_path).casefold() if os.name == "nt" else str(candidate_path)
        if key not in seen:
            seen.add(key)
            candidates.append(FaceModelCandidate(source=source, path=candidate_path))

    if requested.is_absolute():
        add(f"配置项指定模型 {filename}", requested)
    else:
        add("配置路径（按 gateway 当前工作目录解析）", Path.cwd() / requested)
        if config_directory is not None:
            add("配置路径（按 DESKTOP_PET_CONFIG_DIR 解析）", Path(config_directory) / requested)

    if getattr(sys, "frozen", False):
        exe_directory = Path(sys.executable).resolve(strict=False).parent
        add("PyInstaller：exe 同目录 models", exe_directory / "models" / filename)
        add("PyInstaller：exe/_internal/models", exe_directory / "_internal" / "models" / filename)
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            add("PyInstaller：_MEIPASS/models", Path(meipass) / "models" / filename)

    if not getattr(sys, "frozen", False):
        backend_root = Path(__file__).resolve(strict=False).parents[1]
        add("开发目录 backend/models", backend_root / "models" / filename)
    return candidates


def resolve_model_path(
    requested_path: str | Path,
    config_directory: str | Path | None = None,
    filename: str = LANDMARKER_MODEL_FILENAME,
) -> str:
    """
    解析人脸模型文件路径，按优先级查找：
    1. 配置指定的路径（如果存在）
    2. 可执行文件同目录下的 models/face_landmarker.task（PyInstaller 打包后）
    3. _internal/models/face_landmarker.task（PyInstaller onefile 模式）
    4. 打包 datas 中的 models/face_landmarker.task
    """
    for candidate in face_model_candidates(requested_path, config_directory, filename):
        if candidate.path.is_file():
            return str(candidate.path)

    return str(requested_path)  # 返回原路径，让上层报更清晰的错


def inspect_face_model_candidates(
    requested_path: str | Path,
    config_directory: str | Path | None = None,
    filename: str = LANDMARKER_MODEL_FILENAME,
) -> list[dict[str, str | bool | int | None]]:
    """返回候选路径、来源、存在性与字节数，供 /api/face/status 诊断。"""
    result: list[dict[str, str | bool | int | None]] = []
    for candidate in face_model_candidates(requested_path, config_directory, filename):
        size: int | None = None
        exists = candidate.path.is_file()
        if exists:
            size = candidate.path.stat().st_size
        result.append({
            "source": candidate.source,
            "path": str(candidate.path),
            "exists": exists,
            "size_bytes": size,
        })
    return result


_face_dependency_cache: dict[str, FaceDependencyStatus] = {}


def check_face_dependency(module_name: str) -> FaceDependencyStatus:
    """实际导入可选依赖，并缓存导入结果和版本号。"""
    if module_name in _face_dependency_cache:
        return _face_dependency_cache[module_name]
    try:
        module = importlib.import_module(module_name)
        status = FaceDependencyStatus(
            module=module_name,
            available=True,
            version=getattr(module, "__version__", None),
        )
    except Exception as exc:  # pragma: no cover - 取决于本机依赖环境
        status = FaceDependencyStatus(
            module=module_name,
            available=False,
            error=f"{type(exc).__name__}: {exc}",
        )
    _face_dependency_cache[module_name] = status
    return status


def face_runtime_diagnostics(
    requested_paths: dict[str, str | Path],
    config_directory: str | Path | None = None,
    required_dependencies: tuple[str, ...] = ("cv2",),
    optional_dependencies: tuple[str, ...] = ("mediapipe",),
) -> dict[str, object]:
    """
    收集多个人脸模型的路径诊断、依赖导入结果和运行时环境。

    requested_paths: {模型角色: 配置的模型路径}，例如
    {"detector_yunet": ..., "recognizer_sface": ...}。
    """
    models: dict[str, object] = {}
    for role, requested_path in requested_paths.items():
        filename = Path(str(requested_path)).name
        resolved = resolve_model_path(requested_path, config_directory, filename)
        resolved_path = Path(resolved)
        model_exists = resolved_path.is_file()
        models[role] = {
            "path": resolved if model_exists else None,
            "size_bytes": resolved_path.stat().st_size if model_exists else None,
            "candidates": inspect_face_model_candidates(
                requested_path, config_directory, filename
            ),
        }
    dependencies = {
        name: check_face_dependency(name).__dict__
        for name in (*required_dependencies, *optional_dependencies)
    }
    return {
        "backend": "sface" if required_dependencies == ("cv2",) else "unknown",
        "models": models,
        "dependencies": dependencies,
        "runtime": {
            "cwd": str(Path.cwd()),
            "frozen": bool(getattr(sys, "frozen", False)),
            "executable": sys.executable,
            "meipass": getattr(sys, "_MEIPASS", None),
            "config_directory": str(config_directory) if config_directory is not None else None,
        },
    }


# 人脸特征维度（FaceLandmarker 478 个 3D 关键点 → 1434 维）
FEATURE_DIM = 478 * 3


class FaceRecognitionError(RuntimeError):
    """人脸识别相关错误。"""


def _normalize_landmarks(landmarks: np.ndarray) -> np.ndarray:
    """
    将人脸关键点做刚性对齐归一化：
    1. 减去中心点（平移归一化）
    2. 按两眼间距缩放（尺度归一化）
    返回归一化后的 (N, 3) 数组。
    """
    if landmarks.shape[0] < 10:
        raise FaceRecognitionError("关键点数量不足")

    # 中心：所有点的均值
    center = landmarks.mean(axis=0)
    centered = landmarks - center

    # 用左右眼内眦点估算尺度（MediaPipe FaceLandmarker 中点 33 和 263）
    # 如果点数不够，就用所有点的标准差
    if landmarks.shape[0] > 263:
        left_eye = landmarks[33]
        right_eye = landmarks[263]
        eye_distance = np.linalg.norm(left_eye - right_eye)
        if eye_distance > 1e-6:
            scale = 1.0 / eye_distance
        else:
            scale = 1.0
    else:
        scale = 1.0 / (np.linalg.norm(centered, axis=1).mean() + 1e-6)

    normalized = centered * scale
    return normalized


def _landmarks_to_feature(landmarks: np.ndarray) -> np.ndarray:
    """将归一化后的关键点展平为特征向量并做 L2 归一化。"""
    feat = landmarks.flatten().astype(np.float32)
    norm = np.linalg.norm(feat)
    if norm < 1e-6:
        raise FaceRecognitionError("特征向量范数过小")
    return feat / norm


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """计算两个特征向量的余弦相似度。"""
    return float(np.dot(a, b))


def _stage_model_for_opencv(source_path: str | Path) -> str:
    """
    OpenCV DNN 在 Windows 下无法打开含 Unicode（含 U+2011 特殊连字符）的
    模型路径。按源文件 SHA256 复制到 ASCII 临时目录，内容不变则复用缓存。
    """
    import hashlib
    import shutil

    source = Path(source_path)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    target_dir = Path(tempfile.gettempdir()) / "deskpet_face_models"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{source.stem}-{digest}{source.suffix}"
    if not target.is_file() or target.stat().st_size != source.stat().st_size:
        shutil.copyfile(source, target)
    return str(target)


class SFaceFaceEngine:
    """
    YuNet 人脸检测 + SFace 身份嵌入（128 维）。

    这是 P1-2 标定后采用的默认身份特征方案：SFace 是人脸识别专用嵌入，
    实测主人/他人余弦分数间隔约 0.41，远优于几何关键点。
    懒加载，线程安全。
    """

    _instance: "SFaceFaceEngine | None" = None
    _lock = Lock()

    def __init__(self, detector_path: str | Path, recognizer_path: str | Path):
        self._detector_path = str(detector_path)
        self._recognizer_path = str(recognizer_path)
        self._detector = None
        self._recognizer = None
        self._init_lock = Lock()

    @classmethod
    def get(
        cls,
        detector_path: str | Path,
        recognizer_path: str | Path,
    ) -> "SFaceFaceEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(detector_path, recognizer_path)
            return cls._instance

    def _ensure_detector(self) -> None:
        if self._detector is not None and self._recognizer is not None:
            return
        with self._init_lock:
            if self._detector is not None and self._recognizer is not None:
                return
            try:
                import cv2
            except ImportError as exc:
                raise FaceRecognitionError(
                    "OpenCV 未安装，请先 pip install opencv-python"
                ) from exc

            for raw_path in (self._detector_path, self._recognizer_path):
                if not os.path.isfile(raw_path):
                    raise FaceRecognitionError(f"人脸模型文件不存在: {raw_path}")

            detector_model = _stage_model_for_opencv(self._detector_path)
            recognizer_model = _stage_model_for_opencv(self._recognizer_path)
            # score_threshold=0.6：默认 0.9 在普通光照/侧脸照片上会漏检。
            self._detector = cv2.FaceDetectorYN_create(
                detector_model, "", (320, 320), 0.6, 0.3, 5000
            )
            self._recognizer = cv2.FaceRecognizerSF_create(recognizer_model, "")

    def extract_feature_from_image(self, image_data: bytes) -> np.ndarray:
        """从图片字节提取 L2 归一化的 128 维 SFace 身份特征。"""
        self._ensure_detector()
        import cv2

        buffer = np.frombuffer(image_data, dtype=np.uint8)
        img = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if img is None:
            raise FaceRecognitionError("无法解码图片，请确认是 JPEG/PNG 等有效格式")

        height, width = img.shape[:2]
        self._detector.setInputSize((width, height))
        _, faces = self._detector.detect(img)
        if faces is None or len(faces) == 0:
            raise FaceRecognitionError("未检测到人脸")

        face = max(faces, key=lambda row: float(row[-1]))
        aligned = self._recognizer.alignCrop(img, face)
        feature = self._recognizer.feature(aligned).flatten().astype(np.float32)
        norm = np.linalg.norm(feature)
        if norm < 1e-6:
            raise FaceRecognitionError("身份特征向量范数过小")
        return feature / norm

    def close(self) -> None:
        self._detector = None
        self._recognizer = None


class MediaPipeFaceEngine:
    """
    MediaPipe FaceLandmarker 封装。
    懒加载模型，线程安全。
    """

    _instance: "MediaPipeFaceEngine | None" = None
    _lock = Lock()

    def __init__(self, model_path: str | Path):
        self._model_path = str(model_path)
        self._detector = None
        self._init_lock = Lock()

    @classmethod
    def get(cls, model_path: str | Path) -> "MediaPipeFaceEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(model_path)
            return cls._instance

    def _ensure_detector(self):
        if self._detector is not None:
            return
        with self._init_lock:
            if self._detector is not None:
                return
            try:
                import mediapipe as mp
                from mediapipe.tasks import python as mp_python
                from mediapipe.tasks.python import vision as mp_vision
            except ImportError as exc:
                raise FaceRecognitionError(
                    "MediaPipe 未安装，请先 pip install mediapipe opencv-python"
                ) from exc

            # 解析模型路径（兼容 PyInstaller 打包和开发环境）
            raw_model_path = resolve_model_path(self._model_path)
            if not os.path.exists(raw_model_path):
                raise FaceRecognitionError(f"模型文件不存在: {raw_model_path}")

            # 处理路径中可能存在的特殊字符（如 Unicode 破折号）：
            # MediaPipe C++ 底层可能无法读取含特殊字符的路径，统一复制到临时目录
            model_path = raw_model_path

            tmp_dir = tempfile.gettempdir()
            safe_path = os.path.join(tmp_dir, "deskpet_face_landmarker.task")
            # 仅在文件不存在或大小变化时重新复制
            src_size = os.path.getsize(model_path)
            need_copy = True
            if os.path.exists(safe_path):
                try:
                    if os.path.getsize(safe_path) == src_size:
                        need_copy = False
                except OSError:
                    need_copy = True
            if need_copy:
                with open(model_path, "rb") as src, open(safe_path, "wb") as dst:
                    dst.write(src.read())

            base_options = mp_python.BaseOptions(model_asset_path=safe_path)
            options = mp_vision.FaceLandmarkerOptions(
                base_options=base_options,
                running_mode=mp_vision.RunningMode.IMAGE,
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._detector = mp_vision.FaceLandmarker.create_from_options(options)
            self._mp = mp

    def extract_feature_from_image(self, image_data: bytes) -> np.ndarray:
        """
        从图片字节中提取人脸特征向量。
        图片格式：JPEG / PNG 等 OpenCV 支持的格式。
        返回 L2 归一化后的特征向量。
        """
        self._ensure_detector()
        import cv2

        # 用 OpenCV 解码图片
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise FaceRecognitionError("无法解码图片")

        # OpenCV 是 BGR，转成 RGB
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        mp_image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB, data=img_rgb
        )
        result = self._detector.detect(mp_image)

        if not result.face_landmarks or len(result.face_landmarks) == 0:
            raise FaceRecognitionError("未检测到人脸")

        # 取第一张脸的关键点
        landmarks_raw = result.face_landmarks[0]
        landmarks_array = np.array(
            [(lm.x, lm.y, lm.z) for lm in landmarks_raw], dtype=np.float32
        )

        normalized = _normalize_landmarks(landmarks_array)
        feature = _landmarks_to_feature(normalized)
        return feature

    def close(self):
        if self._detector is not None:
            self._detector.close()
            self._detector = None


@dataclass(frozen=True)
class FaceProfile:
    """已注册的人脸档案。"""
    name: str
    features: List[np.ndarray]  # 多张参考特征向量
    created_at: float
    feature_dim: int = SFACE_FEATURE_DIM

    def to_json(self) -> dict:
        actual_dim = int(self.features[0].shape[0]) if self.features else self.feature_dim
        return {
            "name": self.name,
            "features": [base64.b64encode(f.tobytes()).decode("ascii") for f in self.features],
            "created_at": self.created_at,
            "feature_dim": actual_dim,
            "feature_backend": "sface",
        }

    @classmethod
    def from_json(cls, data: dict) -> "FaceProfile":
        features = []
        for f in data.get("features", []):
            raw = base64.b64decode(f)
            feature = np.frombuffer(raw, dtype=np.float32).copy()
            if feature.size == 0:
                raise ValueError("人脸档案中存在空特征")
            features.append(feature)
        if not features:
            raise ValueError("人脸档案没有任何特征")
        expected_dim = int(data.get("feature_dim", SFACE_FEATURE_DIM))
        mismatched = [index for index, feature in enumerate(features) if feature.size != expected_dim]
        if mismatched:
            raise ValueError(
                f"人脸档案特征维度与当前引擎不一致（档案 {expected_dim} 维，"
                f"当前引擎 {SFACE_FEATURE_DIM} 维），需要用当前版本重新注册"
            )
        return cls(
            name=str(data.get("name", "owner")),
            features=features,
            created_at=float(data.get("created_at", 0.0)),
            feature_dim=expected_dim,
        )


class FaceProfileStore:
    """人脸档案本地存储（JSON 文件）。"""

    def __init__(self, storage_path: str | Path):
        self._path = Path(storage_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def load(self) -> FaceProfile | None:
        with self._lock:
            if not self._path.exists():
                return None
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return FaceProfile.from_json(data)
            except (json.JSONDecodeError, KeyError, ValueError):
                return None

    def save(self, profile: FaceProfile) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(profile.to_json(), f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._path)

    def clear(self) -> None:
        with self._lock:
            if self._path.exists():
                self._path.unlink()


class FaceVerificationAdapter:
    """
    引擎无关的人脸验证适配器：默认使用 SFace 身份嵌入，也可注入其它
    实现了 extract_feature_from_image(bytes) -> np.ndarray 的引擎。
    """

    def __init__(
        self,
        engine: SFaceFaceEngine | MediaPipeFaceEngine,
        profile_store: FaceProfileStore,
        similarity_threshold: float = 0.45,
        min_reference_samples: int = 3,
        name: str = "sface-face",
    ):
        self._engine = engine
        self._profile_store = profile_store
        self._similarity_threshold = similarity_threshold
        self._min_reference_samples = min_reference_samples
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    async def verify(self, image_data: bytes) -> bool:
        """验证图片中的人脸是否为已注册的主人。"""
        profile = self._profile_store.load()
        if profile is None or len(profile.features) == 0:
            raise FaceRecognitionError("尚未注册主人人脸，请先录入")

        feature = self._engine.extract_feature_from_image(image_data)

        # 与所有参考特征比对，取最高相似度
        best_score = 0.0
        for ref in profile.features:
            score = cosine_similarity(feature, ref)
            if score > best_score:
                best_score = score

        return best_score >= self._similarity_threshold

    def register_samples(self, name: str, image_samples: Sequence[bytes]) -> FaceProfile:
        """用多张图片注册人脸。"""
        if len(image_samples) < self._min_reference_samples:
            raise FaceRecognitionError(
                f"至少需要 {self._min_reference_samples} 张参考图片"
            )

        features = []
        for img in image_samples:
            feat = self._engine.extract_feature_from_image(img)
            features.append(feat)

        import time
        profile = FaceProfile(
            name=name,
            features=features,
            created_at=time.time(),
            feature_dim=int(features[0].shape[0]),
        )
        self._profile_store.save(profile)
        return profile

    def has_profile(self) -> bool:
        return self._profile_store.load() is not None

    def clear_profile(self) -> None:
        self._profile_store.clear()


# 向后兼容别名（旧代码/测试中可能仍按 MediaPipe 命名引用）
MediaPipeFaceAdapter = FaceVerificationAdapter

