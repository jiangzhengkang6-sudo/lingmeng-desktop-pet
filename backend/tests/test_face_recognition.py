from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from dataclasses import replace
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app import main

from backend.app.face_recognition import (
    FACE_MODEL_FILENAME,
    FaceProfile,
    FaceProfileStore,
    FaceRecognitionError,
    LANDMARKER_FEATURE_DIM,
    MediaPipeFaceAdapter,
    SFACE_FEATURE_DIM,
    SFACE_MODEL_FILENAME,
    YUNET_MODEL_FILENAME,
    cosine_similarity,
    face_runtime_diagnostics,
    inspect_face_model_candidates,
    resolve_model_path,
    _landmarks_to_feature,
    _normalize_landmarks,
)


def make_landmarks() -> np.ndarray:
    """构造 478 个稳定的 3D 关键点，并保证点 33/263 是左右眼。"""
    landmarks = np.zeros((478, 3), dtype=np.float32)
    for index in range(478):
        landmarks[index] = (
            (index % 7) - 3,
            ((index // 7) % 5) - 2,
            (((index // 35) % 9) - 4) / 2,
        )
    landmarks[33] = (-1.0, 0.0, 0.0)
    landmarks[263] = (1.0, 0.0, 0.0)
    return landmarks


def test_landmark_feature_is_normalized_and_rigid_transform_invariant() -> None:
    base = make_landmarks()
    shifted = base * 2.5 + np.array([18.0, -31.0, 7.0], dtype=np.float32)

    base_feature = _landmarks_to_feature(_normalize_landmarks(base))
    shifted_feature = _landmarks_to_feature(_normalize_landmarks(shifted))

    assert base_feature.shape == (478 * 3,)
    assert base_feature.dtype == np.float32
    assert pytest.approx(float(np.linalg.norm(base_feature)), rel=1e-6) == 1.0
    assert pytest.approx(float(np.linalg.norm(shifted_feature)), rel=1e-6) == 1.0
    assert cosine_similarity(base_feature, shifted_feature) == pytest.approx(1.0, abs=1e-6)


def test_landmark_normalization_rejects_too_few_points() -> None:
    with pytest.raises(FaceRecognitionError):
        _normalize_landmarks(np.zeros((3, 3), dtype=np.float32))


def test_face_profile_store_round_trip_and_rejects_corrupt_json(tmp_path) -> None:
    profile_path = tmp_path / "face_profile.json"
    store = FaceProfileStore(profile_path)
    feature = np.full(6, 0.25, dtype=np.float32)

    assert store.load() is None

    store.save(FaceProfile(name="owner", features=[feature], created_at=123.0))
    loaded = store.load()

    assert loaded is not None
    assert loaded.name == "owner"
    assert loaded.created_at == 123.0
    assert len(loaded.features) == 1
    np.testing.assert_allclose(loaded.features[0], feature)

    profile_path.write_text("{not-json", encoding="utf-8")
    assert store.load() is None

    store.clear()
    assert not profile_path.exists()


class ProgrammedFaceEngine:
    def __init__(
        self,
        enrollment_feature: np.ndarray,
        verification_feature: np.ndarray,
        other_feature: np.ndarray,
    ) -> None:
        self.enrollment_feature = enrollment_feature
        self.verification_feature = verification_feature
        self.other_feature = other_feature

    def extract_feature_from_image(self, image_data: bytes) -> np.ndarray:
        if image_data == b"other":
            return self.other_feature
        if image_data == b"verify-owner":
            return self.verification_feature
        return self.enrollment_feature


@pytest.mark.asyncio
async def test_face_adapter_registers_samples_and_compares_best_score(tmp_path) -> None:
    owner = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    other = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    near_owner = np.array([0.95, 0.05, 0.0], dtype=np.float32)
    near_owner /= np.linalg.norm(near_owner)

    store = FaceProfileStore(tmp_path / "face_profile.json")
    engine = ProgrammedFaceEngine(owner, near_owner, other)
    adapter = MediaPipeFaceAdapter(
        engine=engine,
        profile_store=store,
        similarity_threshold=0.999,
        min_reference_samples=3,
    )

    profile = adapter.register_samples("owner", [b"enroll", b"enroll", b"enroll"])
    assert profile.name == "owner"
    assert len(profile.features) == 3
    assert await adapter.verify(b"verify-owner") is False

    adapter._similarity_threshold = 0.9
    assert await adapter.verify(b"verify-owner") is True
    assert await adapter.verify(b"other") is False


def test_face_status_endpoint_exposes_path_and_dependency_diagnostics(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        main,
        "settings",
        replace(main.settings, face_recognition_profile_path=tmp_path / "face_profile.json"),
    )

    response = TestClient(main.app).get("/api/face/status")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["configured"] is True
    assert body["has_profile"] is False
    assert body["diagnostics"]["backend"] == "sface"
    models = body["diagnostics"]["models"]
    assert set(models) == {"detector_yunet", "recognizer_sface", "landmarker_mediapipe"}
    assert models["detector_yunet"]["path"].endswith(YUNET_MODEL_FILENAME)
    assert models["recognizer_sface"]["path"].endswith(SFACE_MODEL_FILENAME)
    assert isinstance(models["detector_yunet"]["size_bytes"], int)
    assert models["detector_yunet"]["candidates"]
    assert set(body["diagnostics"]["dependencies"]) == {"mediapipe", "cv2"}
    assert "runtime" in body["diagnostics"]
    assert body["similarity_threshold"] == pytest.approx(0.45)


def test_face_engine_missing_model_503_contains_candidate_diagnostics(monkeypatch, tmp_path) -> None:
    exe_dir = tmp_path / "gateway"
    work_dir = tmp_path / "work"
    exe_dir.mkdir()
    work_dir.mkdir()
    monkeypatch.setattr(
        main,
        "settings",
        replace(
            main.settings,
            face_detection_model_path=tmp_path / "missing" / YUNET_MODEL_FILENAME,
            face_recognizer_model_path=tmp_path / "missing" / SFACE_MODEL_FILENAME,
        ),
    )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "desktop-pet-gateway.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "meipass"), raising=False)
    monkeypatch.chdir(work_dir)

    with pytest.raises(HTTPException) as exc_info:
        main._face_engine()

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    assert detail["code"] == "FACE_MODEL_MISSING"
    assert detail["diagnostics"]["models"]["detector_yunet"]["path"] is None
    assert detail["diagnostics"]["models"]["recognizer_sface"]["path"] is None
    candidates = detail["diagnostics"]["models"]["recognizer_sface"]["candidates"]
    assert candidates
    assert all(item["exists"] is False for item in candidates)


def test_packaged_model_resolution_prefers_exe_directory(monkeypatch, tmp_path) -> None:
    config_dir = tmp_path / "LocalAppData" / "LingMengDesktopPet"
    work_dir = tmp_path / "work"
    exe_dir = tmp_path / "install" / "gateway"
    meipass_dir = tmp_path / "meipass"
    exe_dir.joinpath("models").mkdir(parents=True)
    meipass_dir.joinpath("models").mkdir(parents=True)
    work_dir.mkdir(parents=True)

    exe_model = exe_dir / "models" / FACE_MODEL_FILENAME
    meipass_model = meipass_dir / "models" / FACE_MODEL_FILENAME
    exe_model.write_bytes(b"exe-model")
    meipass_model.write_bytes(b"meipass-model")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "desktop-pet-gateway.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass_dir), raising=False)
    monkeypatch.chdir(work_dir)

    requested = config_dir / "backend" / "models" / FACE_MODEL_FILENAME

    assert Path(resolve_model_path(requested, config_dir)) == exe_model.resolve()
    candidates = inspect_face_model_candidates(requested, config_dir)
    existing = [item for item in candidates if item["exists"]]
    assert existing[0]["path"] == str(exe_model.resolve())
    assert existing[0]["size_bytes"] == len(b"exe-model")


def test_packaged_model_diagnostics_reports_all_missing_paths(monkeypatch, tmp_path) -> None:
    config_dir = tmp_path / "config"
    exe_dir = tmp_path / "gateway"
    work_dir = tmp_path / "work"
    exe_dir.mkdir()
    work_dir.mkdir()
    requested = config_dir / "backend" / "models" / YUNET_MODEL_FILENAME

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "desktop-pet-gateway.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "meipass"), raising=False)
    monkeypatch.chdir(work_dir)

    diagnostics = face_runtime_diagnostics({"detector_yunet": requested}, config_dir)

    assert resolve_model_path(requested, config_dir) == str(requested)
    assert diagnostics["models"]["detector_yunet"]["path"] is None
    assert diagnostics["models"]["detector_yunet"]["size_bytes"] is None
    assert all(
        item["exists"] is False
        for item in diagnostics["models"]["detector_yunet"]["candidates"]
    )
    assert set(diagnostics["dependencies"]) == {"mediapipe", "cv2"}
    assert diagnostics["runtime"]["frozen"] is True


def test_face_profile_rejects_legacy_landmarker_dimensions(tmp_path) -> None:
    """旧的 1434 维几何关键点档案不能被 SFace 引擎误用，应要求重新注册。"""
    import base64
    import json

    profile_path = tmp_path / "face_profile.json"
    legacy_feature = np.zeros(LANDMARKER_FEATURE_DIM, dtype=np.float32)
    # 旧版本写盘格式没有 feature_dim/feature_backend 字段
    profile_path.write_text(json.dumps({
        "name": "owner",
        "features": [base64.b64encode(legacy_feature.tobytes()).decode("ascii")],
        "created_at": 1.0,
    }), encoding="utf-8")
    store = FaceProfileStore(profile_path)

    assert store.load() is None


def test_face_profile_records_sface_feature_dimension(tmp_path) -> None:
    store = FaceProfileStore(tmp_path / "face_profile.json")
    feature = np.full(
        SFACE_FEATURE_DIM,
        1.0 / np.sqrt(SFACE_FEATURE_DIM),
        dtype=np.float32,
    )
    store.save(FaceProfile(name="owner", features=[feature], created_at=2.0))

    loaded = store.load()
    assert loaded is not None
    assert loaded.feature_dim == SFACE_FEATURE_DIM
    assert loaded.features[0].shape == (SFACE_FEATURE_DIM,)
