from __future__ import annotations

import numpy as np
import pytest

from backend.app.face_calibration import calibrate_similarity


def unit_vector(values: tuple[float, float]) -> np.ndarray:
    vector = np.array([values[0], values[1]], dtype=np.float32)
    return vector / np.linalg.norm(vector)


def test_calibration_reports_gap_and_recommended_midpoint() -> None:
    # 主人样本聚集在 x 轴附近；他人样本与主人有明显夹角。
    owner = [
        unit_vector((1.0, 0.01)),
        unit_vector((1.0, 0.02)),
        unit_vector((1.0, -0.01)),
    ]
    impostors = [
        unit_vector((0.0, 1.0)),
        unit_vector((0.1, 1.0)),
    ]

    result = calibrate_similarity(owner, impostors)
    payload = result.to_dict()

    assert payload["owner"]["count"] == 3
    assert payload["impostor"]["count"] == 2
    assert result.gap > 0.02
    assert result.separable is True
    assert result.recommended_threshold is not None
    assert payload["impostor"]["max"] < result.recommended_threshold < payload["owner"]["min"]


def test_calibration_detects_overlapping_distributions() -> None:
    owner = [unit_vector((1.0, 0.0)), unit_vector((0.8, 0.6))]
    impostors = [unit_vector((0.95, 0.05))]

    result = calibrate_similarity(owner, impostors)

    assert result.gap < 0
    assert result.separable is False
    assert result.recommended_threshold is None


def test_calibration_rejects_insufficient_samples() -> None:
    feature = unit_vector((1.0, 0.0))

    with pytest.raises(ValueError, match="主人样本"):
        calibrate_similarity([feature], [feature])

    with pytest.raises(ValueError, match="他人样本"):
        calibrate_similarity([feature, feature], [])
