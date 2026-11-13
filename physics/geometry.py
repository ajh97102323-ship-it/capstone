"""횡형 캡슐 탱크(반구 2개 + 직선 실린더) 형상 관계식."""
import numpy as np


class CapsuleTank:
    """반경 R, 실린더 길이 L인 횡형 캡슐 탱크. L = 0이면 구형 탱크."""

    def __init__(self, R: float, L: float, n_grid: int = 2001):
        if R <= 0 or L < 0:
            raise ValueError("R > 0, L >= 0 이어야 합니다.")
        self.R, self.L = R, L
        self.A_tot = 2 * np.pi * R * L + 4 * np.pi * R**2
        self.V_tot = np.pi * R**2 * L + 4 / 3 * np.pi * R**3
        # 액위 역산용 테이블 (V(h)는 단조증가)
        self._h_grid = np.linspace(0.0, 2 * R, n_grid)
        self._V_grid = self.volume(self._h_grid)

    def _theta(self, h):
        return np.arccos(np.clip((self.R - h) / self.R, -1.0, 1.0))

    def volume(self, h):
        """액위 h에서의 액체 체적 [m³]."""
        R, L = self.R, self.L
        h = np.clip(h, 0.0, 2 * R)
        seg = R**2 * self._theta(h) - (R - h) * np.sqrt(np.clip(2 * R * h - h**2, 0.0, None))
        return L * seg + np.pi * h**2 * (3 * R - h) / 3

    def wetted_area(self, h):
        """액위 h에서 액체가 닿은 내벽 면적 [m²]."""
        h = np.clip(h, 0.0, 2 * self.R)
        return 2 * self.R * self.L * self._theta(h) + 2 * np.pi * self.R * h

    def level(self, V_liq):
        """액체 체적 → 액위 h (테이블 보간)."""
        return np.interp(V_liq, self._V_grid, self._h_grid)
