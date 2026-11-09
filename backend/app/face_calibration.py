"""
人脸相似度阈值标定工具。

实验方法（对应迭代方案 P1-1）：
- 主人样本：同一人 5 张以上，不同表情、角度、光照；
- 他人样本：至少 5 个非主人样本；
- 主人分布采用“留一法”：每张样本与其余主人样本比，取最高相似度；
- 他人分布：每张他人样本与全部主人样本比，取最高相似度。

两类分布之间的间隔（gap）为正且足够明显时，才允许把中间值作为线上阈值。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .face_recognition import cosine_similarity


@dataclass(frozen=True)
class CalibrationDistribution:
    """一组相似度分数的统计分布。"""

    scores: tuple[float, ...]

    @property
    def count(self) -> int:
        return len(self.scores)

    @property
    def minimum(self) -> float:
        return float(min(self.scores))

    @property
    def maximum(self) -> float:
        return float(max(self.scores))

    @property
    def mean(self) -> float:
        return float(np.mean(self.scores))

    @property
    def std(self) -> float:
        return float(np.std(self.scores))

    def to_dict(self) -> dict[str, float | int | list[float]]:
        return {
            "count": self.count,
            "min": self.minimum,
            "max": self.maximum,
            "mean": self.mean,
            "std": self.std,
            "scores": [round(score, 6) for score in self.scores],
        }


@dataclass(frozen=True)
class CalibrationResult:
    """阈值标定结果。"""

    owner_distribution: CalibrationDistribution
    impostor_distribution: CalibrationDistribution

    @property
    def gap(self) -> float:
        """主人最低分与他人最高分之间的间隔；越大越安全。"""
        return self.owner_distribution.minimum - self.impostor_distribution.maximum

    @property
    def separable(self) -> bool:
        """两类样本完全可分，且间隔达到可上线的最低要求。"""
        return self.gap >= 0.02

    @property
    def recommended_threshold(self) -> float | None:
        """可分时取两类边界的中点并保留 6 位小数。"""
        if self.gap <= 0:
            return None
        return round(
            (self.owner_distribution.minimum + self.impostor_distribution.maximum) / 2.0,
            6,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "owner": self.owner_distribution.to_dict(),
            "impostor": self.impostor_distribution.to_dict(),
            "gap": round(self.gap, 6),
            "separable": self.separable,
            "recommended_threshold": self.recommended_threshold,
        }


def _best_similarity(feature: np.ndarray, references: list[np.ndarray]) -> float:
    return max(cosine_similarity(feature, reference) for reference in references)


def calibrate_similarity(
    owner_features: list[np.ndarray],
    impostor_features: list[np.ndarray],
) -> CalibrationResult:
    """
    计算主人/他人相似度分布。

    主人样本至少 2 张才能做留一法；主人或他人样本不足时抛出 ValueError，
    避免用单一样本得出没有统计意义的阈值。
    """
    if len(owner_features) < 2:
        raise ValueError("主人样本至少需要 2 张，建议 5 张以上")
    if not impostor_features:
        raise ValueError("他人样本至少需要 1 张，建议 5 张以上")

    owner_scores: list[float] = []
    for index, feature in enumerate(owner_features):
        references = owner_features[:index] + owner_features[index + 1:]
        owner_scores.append(_best_similarity(feature, references))

    impostor_scores = [
        _best_similarity(feature, owner_features)
        for feature in impostor_features
    ]

    return CalibrationResult(
        owner_distribution=CalibrationDistribution(tuple(owner_scores)),
        impostor_distribution=CalibrationDistribution(tuple(impostor_scores)),
    )
