"""잔량 곡선 대리모델 (specs/002). 공개 API: `load_surrogate`, `Surrogate`, `OutOfRangeError`."""
from .model import OutOfRangeError, Surrogate, load_surrogate

__all__ = ["load_surrogate", "Surrogate", "OutOfRangeError"]
