"""보고서 그림·report.md·results.json (specs/003 T006, contracts/optimize-api.md).

이 모듈은 파일을 쓰기만 한다. 출력 디렉터리(`<name>.partial`)는 run.py가 만든다.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .layers import LayerResult, Verification  # noqa: E402
from .problem import Problem  # noqa: E402


def _set_korean_font() -> None:
    from matplotlib import font_manager
    have = {f.name for f in font_manager.fontManager.ttflist}
    for cand in ("Malgun Gothic", "NanumGothic", "AppleGothic"):
        if cand in have:
            plt.rcParams["font.family"] = cand
            break
    plt.rcParams["axes.unicode_minus"] = False


def provenance(sur, model_path) -> dict:
    """물리 모델 버전·소스 해시와 대리모델 메타 (헌법 V). 지문은 data.versioning을 재사용한다."""
    from data.versioning import physics_fingerprint
    info = getattr(sur, "dataset_info", None) or {}
    try:
        matches = bool(sur.physics_matches())
    except Exception:  # noqa: BLE001  (physics_matches가 없는 대역 등)
        matches = False
    return {"physics": physics_fingerprint(),
            "model": {"path": str(model_path), "name": Path(model_path).name,
                      "dataset_physics": info.get("physics"), "physics_matches": matches}}


def provenance_lines(pv: dict) -> list:
    m = pv["model"]
    return ["## 출처", "",
            f"- 물리 모델 버전: {pv['physics']['version']}, 소스 해시(sha256): {pv['physics']['sha256']}",
            f"- 대리모델: `{m['path']}` (이름 {m['name']}), 학습 데이터셋 물리 지문: {m['dataset_physics']}",
            f"- physics_matches: {m['physics_matches']}", ""]


def problem_dict(problem: Problem) -> dict:
    return {"design": dict(problem.design), "cost": asdict(problem.cost), "n_range": list(problem.n_range),
            "residual": None if problem.residual is None else list(problem.residual)}


def plot_cost_breakdown(path, result: LayerResult, ver: Verification) -> None:
    """MLI·보일오프·총비용: ODE 실선, 대리모델 점선, 최적점, 평평한 구간 음영. 소진 N은 그리지 않는다."""
    _set_korean_font()
    fig, ax = plt.subplots(figsize=(8, 5))
    scan = ver.scan
    ok = ~scan["depleted"]
    f = result.feasible
    for key, label, color in (("annual_mli", "MLI", "tab:blue"), ("annual_boiloff", "보일오프", "tab:orange"),
                              ("annual_total", "총비용", "tab:green")):
        ax.plot(scan["N"][ok], scan[key][ok], color=color, lw=2, label=f"{label} (ODE)")
        ax.plot(result.N[f], getattr(result, key)[f], color=color, ls="--", lw=1.2, label=f"{label} (대리모델)")
    if result.flat is not None:
        ax.axvspan(result.flat[0], result.flat[1], color="gray", alpha=0.15, label="평평한 구간(최소x1.01 이내)")
    if result.n_opt is not None:
        ax.axvline(result.n_opt, color="red", ls=":", label=f"대리모델 최적 N={result.n_opt}")
    if ver.n_ode is not None:
        ax.plot([ver.n_ode], [ver.total_ode], "r*", ms=14, label=f"ODE 최적 N={ver.n_ode}")
    ax.set_xlabel("적층수 N [layers]")
    ax.set_ylabel("연간 환산 비용 [$/yr]")
    ax.set_title("MLI 비용 vs 보일오프 손실 비용")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_sensitivity(path, sens: list) -> None:
    """경제 변수 -> 최적 N: 대리모델, ODE(계산한 점), 근사식. sens는 SensitivityResult 목록."""
    _set_korean_font()
    labels = {"p_h2": "p_H2 [$/kg]", "c_layer": "c_layer [$/(m²·layer)]", "life_years": "수명 [yr]",
              "discount": "할인율 [-]"}
    fig, axes = plt.subplots(1, len(sens), figsize=(5.5 * len(sens), 4.5), squeeze=False)
    for ax, s in zip(axes[0], sens):
        ax.plot(s.values, s.n_sur, "o-", color="tab:green", label="대리모델")
        ax.plot(s.values, s.n_ode, "r*", ms=11, label="ODE")
        ax.plot(s.values, s.n_analytic, "k--", label="근사식 N*")
        ax.set_xlabel(labels.get(s.param, s.param))
        ax.set_ylabel("최적 적층수 N [layers]")
        ax.set_title(f"{s.param} - N* (방향 일치: {s.monotone_ok})")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_pareto(path, par) -> None:
    _set_korean_font()
    fig, ax = plt.subplots(figsize=(6.5, 5))
    m = par.pareto_mask
    ax.plot(par.capex[~m], par.m_lost[~m], "x", color="gray", label="지배됨")
    ax.plot(par.capex[m], par.m_lost[m], "o", color="tab:blue", ms=4, label="Pareto")
    if par.n_cost_opt is not None:
        i = list(par.N).index(par.n_cost_opt)
        ax.plot([par.capex[i]], [par.m_lost[i]], "r*", ms=15, label=f"총비용 최적 N={par.n_cost_opt}")
    ax.set_xlabel("MLI 초기 투자비 [$]")
    ax.set_ylabel("연간 보일오프 질량 [kg/yr]")
    ax.set_title("투자비 - 연간 손실 질량 Pareto")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_ld_tradeoff(path, vol) -> None:
    """L/D-N 총비용 등고선(실행 불가 칸은 비움), 최적점, 직경 제약 경계."""
    import numpy as np
    _set_korean_font()
    fig, ax = plt.subplots(figsize=(8, 5.5))
    if np.isfinite(vol.total).any():
        cs = ax.contourf(vol.N, vol.LD, vol.total, levels=20, cmap="viridis")
        fig.colorbar(cs, ax=ax, label="연간 총비용 [$/yr]")
    if vol.D_max is not None:
        bad = ~vol.ld_feasible & (2 * vol.R > vol.D_max)
        if bad.any() and (~bad).any():
            ax.axhline(vol.LD[~bad].min() - 0.5 * (vol.LD[1] - vol.LD[0]), color="red", ls="--",
                       label=f"직경 제약 2R <= {vol.D_max:g} m 경계")
    if vol.n_opt is not None:
        ax.plot([vol.n_opt], [vol.ld_opt], "r*", ms=15, label=f"최적 N={vol.n_opt}, L/D={vol.ld_opt:.2f}")
    ax.set_xlabel("적층수 N [layers]")
    ax.set_ylabel("L/D [-]")
    ax.set_title(f"체적 고정 V={vol.V:g} m³: L/D - N 총비용")
    ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def _fmt(x, spec="{:.1f}") -> str:
    return "-" if x is None else spec.format(x)


def write_report_md(path, name: str, model_name: str, problem: Problem, result: LayerResult,
                    ver: Verification, notes: list, vol=None, sens=None, par=None, prov=None) -> None:
    lo = problem.n_range[0]
    n_rec = ver.n_recommended
    total_rec = m_rec = None
    if n_rec is not None:  # 최종 보고 값은 ODE 값 (헌법 I)
        total_rec = float(ver.scan["annual_total"][n_rec - lo])
        m_rec = float(ver.scan["m_lost"][n_rec - lo])
    c = problem.cost
    rows = [
        ("대리모델 최적 N", _fmt(result.n_opt, "{}")),
        ("ODE 최적 N", _fmt(ver.n_ode, "{}")),
        ("근사식 N*", _fmt(ver.n_analytic)),
        (f"총비용 [$/yr] (ODE, 추천 N={_fmt(n_rec, '{}')})", _fmt(total_rec, "{:,.0f}")),
        ("연간 손실 질량 [kg/yr] (ODE, 추천 N)", _fmt(m_rec, "{:,.1f}")),
    ]
    lines = [f"# 비용 최적화 보고서: {name}", "",
             "| 항목 | 값 |", "|---|---|", *[f"| {a} | {b} |" for a, b in rows], "",
             f"- 대리모델: `{model_name}`. 보고 값은 ODE 재검증 값이다(헌법 I).",
             f"- 평평한 구간(총비용 <= 최소x1.01): {result.flat if result.flat else '-'}",
             f"- 대리모델 최적 N의 ODE 총비용 상대오차: {_fmt(ver.rel_cost_err, '{:.4%}')}, "
             f"N 차이(대리모델-ODE): {_fmt(ver.dN, '{}')}",
             f"- 재검증 후보 N: {ver.candidates}, 후보 ODE 총비용 [$/yr]: "
             f"{[round(x, 1) for x in ver.candidate_totals_ode]}",
             f"- 대리모델 최적화 시간: {result.elapsed_s * 1000:.1f} ms", "",
             "## 조건", "",
             f"- 설계 입력(N은 설계변수라 무시): {problem.design}",
             f"- 경제 변수: c_layer={c.c_layer} [$/(m²·layer)], c_fixed={c.c_fixed} [$/m²], p_H2={c.p_h2} [$/kg], "
             f"수명={c.life_years} [yr], 할인율={c.discount} [-] (CRF={c.crf:.5f})",
             f"- N 범위: {problem.n_range}", ""]
    if result.warnings:
        lines += ["## 경고", "", *[f"- {w}" for w in result.warnings], ""]
    if notes:
        lines += ["## 참고", "", *[f"- {n}" for n in notes], ""]
    if prov is not None:
        lines += provenance_lines(prov)
    lines += ["## 그림", "", "![비용 분해](cost_breakdown.png)", ""]
    if sens:
        lines += ["![민감도](sensitivity.png)", "",
                  *[f"- {s.param}: 대리모델 N 방향 일치 {s.monotone_ok}, 근사식과 같은 방향 {s.matches_analytic}" for s in sens], ""]
    if par is not None:
        lines += ["![Pareto](pareto.png)", ""]
    if vol is not None:
        rec = (vol.ode or {}).get("recommended")
        lines += ["## 체적 고정 N·L/D", "", f"- V={vol.V:g} m³, D_max={vol.D_max}",
                  f"- 대리모델 최적: N={vol.n_opt}, L/D={_fmt(vol.ld_opt, '{:.2f}')}, R={_fmt(vol.R_opt, '{:.3f}')} m, "
                  f"총비용 {_fmt(vol.total_opt, '{:,.0f}')} $/yr",
                  f"- ODE 재검증 추천: {rec}", *[f"- 경고: {w}" for w in vol.warnings],
                  "", "![ld_tradeoff](ld_tradeoff.png)", ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8", newline="\n")


def write_results_json(path, name: str, model_name: str, problem: Problem, result: LayerResult,
                       ver: Verification, vol=None, sens=None, par=None, prov=None) -> None:
    doc = {"name": name, "model": model_name, "problem": problem_dict(problem),
           "layers": result.to_dict(), "verification": ver.to_dict()}
    if prov is not None:
        doc["provenance"] = prov
    if sens is not None:
        doc["sensitivity"] = [s.to_dict() for s in sens]
    if par is not None:
        doc["pareto"] = par.to_dict()
    if vol is not None:
        doc["volume"] = vol.to_dict()
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def write_outputs(out_dir, name: str, model_name: str, problem: Problem, result: LayerResult,
                  ver: Verification, notes: list, vol=None, sens=None, par=None, prov=None) -> None:
    out_dir = Path(out_dir)
    plot_cost_breakdown(out_dir / "cost_breakdown.png", result, ver)
    if sens:
        plot_sensitivity(out_dir / "sensitivity.png", sens)
    if par is not None:
        plot_pareto(out_dir / "pareto.png", par)
    if vol is not None:
        plot_ld_tradeoff(out_dir / "ld_tradeoff.png", vol)
    write_results_json(out_dir / "results.json", name, model_name, problem, result, ver, vol, sens, par, prov)
    write_report_md(out_dir / "report.md", name, model_name, problem, result, ver, notes, vol, sens, par, prov)
