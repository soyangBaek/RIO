from __future__ import annotations


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalized_center_to_eye_offset(
    center: tuple[float, float] | None,
    *,
    max_x: int = 12,
    max_y: int = 8,
) -> tuple[int, int]:
    """Convert normalized face-center coordinates into simple eye offsets."""

    if center is None:
        return (0, 0)
    x, y = center
    norm_x = _clamp((x - 0.5) * 2.0, -1.0, 1.0)
    norm_y = _clamp((y - 0.5) * 2.0, -1.0, 1.0)
    return (round(norm_x * max_x), round(norm_y * max_y))

