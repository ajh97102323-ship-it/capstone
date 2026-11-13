"""웹 UI의 순수 계산 (specs/004 data-model). Streamlit에 의존하지 않는다.

사용자 데이터를 담는 전역 가변 객체를 두지 않는다(저장 설계안은 호출자가 넘기는 list).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import optimize
from optimize import DEPLETION_TOL, Problem, cost_arrays, optimize_layers
from physics import BoiloffModel, CostParams, DesignParams, simulate
from physics.model import H_FG
from surrogate import load_surrogate

LOG_INPUTS = ("G_sup", "Pv0", "G_out", "S")
N_LOG_OPTIONS = 61
# 이름 -> (한국어 라벨, 단위). 단위가 없으면 [-]
_LABELS = {
    "N": ("MLI 적층수 N", "layer"),
    "Nbar": ("적층밀도 N̄", "layer/cm"),
    "eps": ("실드 방사율 ε", "-"),
    "G_sup": ("지지구조 컨덕턴스 G_sup", "W/K"),
    "Pv0": ("초기 진공압 Pv0", "Pa"),
    "G_out": ("아웃개싱 G_out", "Pa·m³/s"),
    "S": ("게터 배기속도 S", "m³/s"),
    "R": ("탱크 반경 R", "m"),
    "LD": ("실린더 길이비 L/D", "-"),
    "fill": ("초기 충전율", "-"),
}


@dataclass
class InputSpec:
    name: str
    label: str
    lo: float
    hi: float
    log: bool
    options: list | None
    step: float
    default: float


def input_specs(sur) -> list[InputSpec]:
    tr = sur.train_range
    base = DesignParams()
    specs = []
    for name, lo, hi in zip(tr["names"], tr["lo"], tr["hi"]):
        title, unit = _LABELS[name]
        log = name in LOG_INPUTS
        default = float(getattr(base, name))
        options = None
        if log:
            options = [float(v) for v in np.logspace(np.log10(lo), np.log10(hi), N_LOG_OPTIONS)]
            default = min(options, key=lambda v: abs(np.log10(v) - np.log10(default)))
        step = 1.0 if name == "N" else (hi - lo) / 100.0
        specs.append(InputSpec(name, f"{title} [{unit}]", float(lo), float(hi), log, options, step,
                               default if log else min(max(default, lo), hi)))
    return specs


def _design_x(sur, design: dict) -> np.ndarray:
    return np.array([[float(design[n]) for n in sur.input_names]])


def _problem(design: dict, cost: CostParams, residual=None) -> Problem:
    return Problem(dict(design), cost, residual=residual)


@dataclass
class PredictionSummary:
    t: np.ndarray
    curve: np.ndarray
    Q0: float                # [W]
    ratio_at_query: float    # [-]
    boiloff_rate: float      # [%/day]
    t_empty: float | None    # [day]
    depleted: bool
    annual_mli: float        # [$/yr]
    annual_boiloff: float    # [$/yr]
    annual_total: float      # [$/yr]
    m0: float                # [kg]


def _t_empty(t, curve):
    below = np.flatnonzero(curve < DEPLETION_TOL)
    if below.size == 0:
        return None
    i = int(below[0])
    if i == 0:
        return float(t[0])
    y0, y1 = curve[i - 1], curve[i]
    return float(t[i - 1] + (y0 - DEPLETION_TOL) / (y0 - y1) * (t[i] - t[i - 1]))


def summarize(sur, design: dict, cost: CostParams, t_query: float = 180.0) -> PredictionSummary:
    curve = np.asarray(sur.predict(_design_x(sur, design))[0], dtype=float)  # 범위 밖이면 OutOfRangeError
    t = np.asarray(sur.t, dtype=float)
    p = DesignParams(**design)
    model = BoiloffModel(p)
    q0 = float(model.heat_to_liquid(0, model.m0))
    c = cost_arrays(_problem(design, cost), [design["N"]], [curve[-1]])
    te = _t_empty(t, curve)
    return PredictionSummary(
        t=t, curve=curve, Q0=q0, ratio_at_query=float(np.interp(t_query, t, curve)),
        boiloff_rate=q0 / H_FG / model.m0 * 86400.0 * 100.0, t_empty=te, depleted=te is not None,
        annual_mli=float(c["annual_mli"][0]), annual_boiloff=float(c["annual_boiloff"][0]),
        annual_total=float(c["annual_total"][0]), m0=float(model.m0))


@dataclass
class ValidationResult:
    t: np.ndarray
    curve_ai: np.ndarray
    curve_ode: np.ndarray
    max_abs_err: float   # [-]
    err365: float        # [-] (AI - ODE)
    cost_diff: float     # [$/yr]
    ms_ai: float         # [ms]
    ms_ode: float        # [ms]


def validate(sur, design: dict, cost: CostParams) -> ValidationResult:
    x = _design_x(sur, design)
    t0 = time.perf_counter()
    ai = np.asarray(sur.predict(x)[0], dtype=float)
    ms_ai = (time.perf_counter() - t0) * 1e3
    p = DesignParams(**design)
    t0 = time.perf_counter()
    t, ode = simulate(p)
    ms_ode = (time.perf_counter() - t0) * 1e3
    err = ai - ode
    m0 = BoiloffModel(p).m0
    return ValidationResult(t=np.asarray(t), curve_ai=ai, curve_ode=np.asarray(ode),
                            max_abs_err=float(np.max(np.abs(err))), err365=float(err[-1]),
                            cost_diff=float(cost.p_h2 * m0 * abs(err[-1])), ms_ai=ms_ai, ms_ode=ms_ode)


@dataclass
class OptimizeView:
    problem: Problem
    result: object        # optimize.LayerResult
    n_opt: int | None
    total_opt: float | None
    flat: tuple | None
    warnings: list
    volume: object = None  # optimize.VolumeResult 또는 None


def optimize_view(sur, design: dict, cost: CostParams, residual=None, volume=None) -> OptimizeView:
    """residual=(기간 [day], 최소 잔량비 [-]), volume=(체적 [m³], 최대 직경 [m] 또는 None)."""
    problem = _problem(design, cost, residual)
    res = optimize_layers(sur, problem)
    vol = None
    if volume is not None:
        V, dmax = volume
        vol = optimize.optimize_volume(sur, dict(design), cost, V, D_max=dmax, verify=False)
    return OptimizeView(problem, res, res.n_opt, res.total_opt, res.flat, list(res.warnings), vol)


# ---------- 저장 설계안 (호출자가 세션별 list를 넘긴다) ----------
def add_saved(saved: list, name: str, design: dict, summary: PredictionSummary) -> list:
    name = (name or "").strip()
    if not name:
        raise ValueError("설계안 이름이 비어 있음")
    if any(s["name"] == name for s in saved):
        raise ValueError(f"이미 있는 설계안 이름: {name}")
    saved.append({"name": name, "design": dict(design), "summary": summary})
    return saved


def remove_saved(saved: list, name: str) -> list:
    saved[:] = [s for s in saved if s["name"] != name]
    return saved


def compare_table(saved: list) -> list[dict]:
    rows = []
    for s in saved:
        d, m = s["design"], s["summary"]
        rows.append({
            "이름": s["name"], "N [layer]": int(d["N"]), "R [m]": d["R"], "L/D [-]": d["LD"],
            "365일 잔량비 [-]": float(m.curve[-1]), "초기 열유입 [W]": m.Q0,
            "소진 시점 [day]": m.t_empty,
            "MLI 비용 [$/yr]": m.annual_mli, "보일오프 비용 [$/yr]": m.annual_boiloff,
            "총비용 [$/yr]": m.annual_total,
        })
    return rows


def load_model(path):
    """대리모델 불러오기. 실패하면 경로와 원인을 담은 예외(ODE로 대체하지 않는다)."""
    path = Path(path)
    try:
        if path.name.lower().endswith(".partial"):
            raise ValueError("완성되지 않은 모델(.partial)")
        if not path.is_dir():
            raise FileNotFoundError("모델 폴더가 없음")
        return load_surrogate(path)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"모델을 불러올 수 없음: {path} ({type(e).__name__}: {e})") from e
