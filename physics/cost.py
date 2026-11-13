"""MLI 적층 비용 ↔ 수소 보일오프 손실 비용 트레이드오프 모델.

연간 환산 총비용 [$/yr]
    C_total = C_MLI · CRF(r, Y) + p_H2 · m_lost(1년)

    C_MLI   = (c_layer · N + c_fixed) · A_MLI           적층수에 비례하는 설치비(초기 투자)
    CRF     = r(1+r)^Y / ((1+r)^Y − 1)  (r = 0이면 1/Y)  자본회수계수: 초기 투자를 연간 비용으로 환산
    m_lost  = m0 − m(365일)                              ODE로 계산한 1년 보일오프 질량

MLI 열유속은 모든 항이 1/N에 비례하므로(Lockheed 식), 손실 비용 ≈ B/N + 상수이고
적층 비용 = a·N 이다. 따라서 총비용은 U자형이며 근사 최적 적층수는
    N* ≈ sqrt(B / a),   a = c_layer · A_MLI · CRF,   B = p_H2 · (MLI 기인 연간 손실 질량 × N)
로, 탱크 크기와 거의 무관하고 sqrt(p_H2 / c_layer)에 비례한다.
"""
from dataclasses import dataclass, field, replace

import numpy as np

from .model import DAY, H_FG, T_C, BoiloffModel, DesignParams


@dataclass
class CostParams:
    c_layer: float = 10.0       # MLI 1층당 재료+시공비 [$/(m²·layer)]
    c_fixed: float = 50.0       # 적층수와 무관한 MLI 고정비(커버, 봉합, 기본 인건비) [$/m²]
    p_h2: float = 5.0           # 액화수소 가격(손실 가치) [$/kg]
    life_years: float = 20.0    # 단열 시스템 수명 [yr]
    discount: float = 0.05      # 할인율 [-]

    @property
    def crf(self) -> float:
        r, Y = self.discount, self.life_years
        if r == 0:
            return 1.0 / Y
        g = (1 + r) ** Y
        return r * g / (g - 1)


@dataclass
class CostResult:
    N: float
    A_mli: float                 # MLI 시공 면적 [m²]
    m0: float                    # 초기 액체 질량 [kg]
    m_lost: float                # 1년 보일오프 질량 [kg]
    t_empty: float               # 소진 시점 [day] (소진되지 않으면 inf)
    capex_mli: float             # MLI 초기 비용 [$]
    annual_mli: float            # MLI 연간 환산 비용 [$/yr]
    annual_boiloff: float        # 보일오프 손실 비용 [$/yr]
    t: np.ndarray = field(repr=False)
    ratio: np.ndarray = field(repr=False)

    @property
    def annual_total(self) -> float:
        return self.annual_mli + self.annual_boiloff

    @property
    def depleted(self) -> bool:
        """1년 안에 소진되면 손실량이 m0에서 잘려 손실 비용이 과소평가된다 → 최적화에서 제약 위반으로 처리."""
        return np.isfinite(self.t_empty)


def mli_area(model: BoiloffModel) -> float:
    """MLI 시공 면적. 현재 모델은 외곽 면적 증가를 무시하므로 내벽 전체 면적을 쓴다."""
    return model.tank.A_tot


def mli_capex(N, A_mli, cost: CostParams):
    return (cost.c_layer * N + cost.c_fixed) * A_mli


def evaluate_cost(p: DesignParams, cost: CostParams = CostParams(), n_points: int = 366) -> CostResult:
    """설계 p에 대해 1년 ODE를 풀고 MLI 비용과 보일오프 비용을 함께 계산한다."""
    model = BoiloffModel(p)
    t, ratio = model.simulate(days=365.0, n_points=n_points)
    m_lost = model.m0 * (1.0 - ratio[-1])
    zero = np.nonzero(ratio <= 0.0)[0]
    t_empty = t[zero[0]] if zero.size else np.inf

    A = mli_area(model)
    capex = mli_capex(p.N, A, cost)
    return CostResult(
        N=p.N, A_mli=A, m0=model.m0, m_lost=m_lost, t_empty=t_empty,
        capex_mli=capex, annual_mli=capex * cost.crf, annual_boiloff=cost.p_h2 * m_lost,
        t=t, ratio=ratio,
    )


def cost_from_curve(p: DesignParams, ratio_end, cost: CostParams = CostParams()):
    """대리모델 출력(365일 잔량비)으로 연간 총비용을 계산한다. ODE 없이 형상만 사용.

    경제 변수(c_layer, p_h2 등)는 대리모델 입력이 아니라 이 후처리에서만 쓰이므로,
    UI에서 가격을 바꿔도 재학습이 필요 없다.
    """
    model = BoiloffModel(p)
    A = mli_area(model)
    annual_mli = mli_capex(p.N, A, cost) * cost.crf
    annual_boiloff = cost.p_h2 * model.m0 * (1.0 - np.asarray(ratio_end))
    return annual_mli + annual_boiloff, annual_mli, annual_boiloff


def analytic_optimal_layers(p: DesignParams, cost: CostParams = CostParams()) -> float:
    """1/N 법칙에 기반한 근사 최적 적층수 N* = sqrt(B/a). 소진이 없는 설계에서만 유효.

    현재 N에서 1년 ODE를 한 번 풀어 연간 손실을 구하고, 지지부 열(N과 무관)을 뺀 나머지를
    MLI 경유 손실로 본다. 그 손실이 1/N에 비례한다고 가정한다. 액위 변화에 따른 젖음 면적
    감소가 반영되므로 초기 열유입만 쓰는 방식보다 정확하다(그래도 N 의존성은 1차 근사).
    """
    res = evaluate_cost(p, cost)
    m_support = p.G_sup * (p.Th - T_C) * 365 * DAY / H_FG          # 지지부 경유 손실 [kg/yr]
    m_mli = max(res.m_lost - m_support, 0.0)                        # MLI 경유 손실 [kg/yr] (현재 N 기준)
    B = cost.p_h2 * m_mli * p.N                                     # 손실 비용 ≈ B / N
    a = cost.c_layer * res.A_mli * cost.crf                         # 적층 비용 = a · N
    return float(np.sqrt(B / a))


def cost_vs_layers(p: DesignParams, cost: CostParams = CostParams(), Ns=range(10, 81)):
    """적층수를 바꿔 가며 ODE로 비용을 계산한다 (최적화 결과의 기준값, 그래프용)."""
    results = [evaluate_cost(replace(p, N=float(N)), cost) for N in Ns]
    return {
        "N": np.array([r.N for r in results]),
        "annual_mli": np.array([r.annual_mli for r in results]),
        "annual_boiloff": np.array([r.annual_boiloff for r in results]),
        "annual_total": np.array([r.annual_total for r in results]),
        "m_lost": np.array([r.m_lost for r in results]),
        "depleted": np.array([r.depleted for r in results]),
    }

