"""대리모델 최적화 검증 CLI (specs/003 T014, research R8, SC-001/002/003).

    python -m optimize.validate [--model DIR] [--n 20] [--seed 2026] [--out reports] [--overwrite]

LHS(학습 범위)로 시드 고정 설계를 뽑아 N=10에서 ODE로 소진되지 않는 설계 n개를 고르고, 설계마다
대리모델 최적 N과 ODE 전 범위 최적 N을 비교한다. 결과는 `<out>/opt_validate_<모델 이름>/`.
종료 코드: 0 성공 / 1 설정 오류 / 2 이미 있음 / 3 실패.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from data.config import DEFAULT_INPUTS, _check_name
from data.sampling import sample_inputs
from physics import BoiloffModel, CostParams, DesignParams, evaluate_cost
from surrogate import load_surrogate

from . import report
from .layers import _jsonable, optimize_layers, verify_with_ode
from .problem import DEFAULT_MODEL, Problem
from .run import _ArgError, _Parser, _remove_flat

SC001_DN = 2        # [layers] 대리모델 최적 N과 ODE 최적 N 차이 허용
SC002_REL = 0.01    # [-] 대리모델 N의 ODE 총비용 상대오차 상한
SC003_S = 1.0       # [s] 대리모델 최적화 시간 상한


def _posint(s):
    try:
        v = int(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"정수가 아님: {s!r}") from None
    if v < 1:
        raise argparse.ArgumentTypeError(f"1 이상이어야 함: {s}")
    return v


def build_parser():
    p = _Parser(prog="python -m optimize.validate", description="대리모델 최적화 검증 (SC-001/002/003)")
    p.add_argument("--model", default=DEFAULT_MODEL, help="002 대리모델 디렉터리")
    p.add_argument("--n", type=_posint, default=20, help="검증 설계 개수")
    p.add_argument("--seed", type=int, default=2026, help="LHS 시드")
    p.add_argument("--out", default="reports", help="출력 상위 디렉터리")
    p.add_argument("--overwrite", action="store_true", help="같은 이름의 결과를 교체")
    return p


def pick_designs(n: int, seed: int) -> list:
    """시드 고정 LHS에서 N=10이 ODE로 소진되지 않는 설계 n개 (N 열 제외 입력 dict)."""
    m = max(10 * n, 50)
    X = sample_inputs(DEFAULT_INPUTS, m, np.random.default_rng(seed))
    names = [s.name for s in DEFAULT_INPUTS]
    out = []
    for row in X:
        d = dict(zip(names, map(float, row)))
        if evaluate_cost(DesignParams(**{**d, "N": 10.0})).depleted:
            continue
        out.append({k: v for k, v in d.items() if k != "N"})
        if len(out) == n:
            return out
    raise RuntimeError(f"N=10에서 소진되지 않는 설계가 {len(out)}개뿐 (필요 {n}, 후보 {m}). --n을 줄이거나 시드를 바꿀 것")


def evaluate_design(sur, design: dict, cost: CostParams) -> dict:
    problem = Problem(design, cost)
    res = optimize_layers(sur, problem)
    ver = verify_with_ode(problem, res)
    dN, rel = ver.dN, ver.rel_cost_err
    return {"design": design, "m0": float(BoiloffModel(problem.design_params()).m0),
            "n_sur": res.n_opt, "n_ode": ver.n_ode, "n_recommended": ver.n_recommended,
            "n_analytic": ver.n_analytic, "dN": dN, "rel_cost_err": rel, "elapsed_s": res.elapsed_s,
            "sc001": dN is not None and abs(dN) <= SC001_DN,
            "sc002": rel is not None and rel < SC002_REL,
            "sc003": res.elapsed_s < SC003_S, "warnings": res.warnings}


def _write(d: Path, name: str, model_path: Path, sur, cost, designs, args) -> None:
    n = len(designs)
    summary = {"n": n, "seed": args.seed}
    for k in ("sc001", "sc002", "sc003"):
        summary[f"{k}_pass"] = int(sum(x[k] for x in designs))
        summary[k] = bool(all(x[k] for x in designs))
    m0 = [x["m0"] for x in designs]
    summary["m0_range_kg"] = [min(m0), max(m0)]
    rel = [x["rel_cost_err"] for x in designs if x["rel_cost_err"] is not None]
    summary["rel_cost_err_max"] = max(rel) if rel else None
    summary["dN_abs_max"] = max((abs(x["dN"]) for x in designs if x["dN"] is not None), default=None)
    summary["elapsed_s_max"] = max(x["elapsed_s"] for x in designs)
    prov = report.provenance(sur, model_path)
    doc = {"name": name, "model": model_path.name, "provenance": prov,
           "config": {"n": n, "seed": args.seed, "cost": asdict(cost)},
           "summary": summary, "designs": designs}
    with open(d / "results.json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(_jsonable(doc), fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    rows = [f"| {i} | {x['m0']:.0f} | {x['n_sur']} | {x['n_ode']} | {x['dN']} | "
            f"{'-' if x['rel_cost_err'] is None else format(x['rel_cost_err'], '.3%')} | "
            f"{x['elapsed_s'] * 1000:.1f} | {'O' if x['sc001'] else 'X'}{'O' if x['sc002'] else 'X'}"
            f"{'O' if x['sc003'] else 'X'} |" for i, x in enumerate(designs)]
    lines = [f"# 대리모델 최적화 검증: {name}", "",
             f"- 설계 {n}개, 시드 {args.seed}, 탱크 초기 질량 m0 범위 {min(m0):.0f}~{max(m0):.0f} kg",
             f"- SC-001(|N_sur - N_ode| <= {SC001_DN}): {summary['sc001_pass']}/{n} -> {'통과' if summary['sc001'] else '미달'}",
             f"- SC-002(ODE 총비용 상대오차 < {SC002_REL:.0%}): {summary['sc002_pass']}/{n} -> "
             f"{'통과' if summary['sc002'] else '미달'}",
             f"- SC-003(대리모델 최적화 < {SC003_S:g} s): {summary['sc003_pass']}/{n}, 최대 {summary['elapsed_s_max'] * 1000:.1f} ms",
             f"- 경제 변수: {asdict(cost)}", "",
             "| # | m0 [kg] | N_sur | N_ode | dN | 총비용 상대오차 | 시간 [ms] | SC1/2/3 |",
             "|---|---|---|---|---|---|---|---|", *rows, "", *report.provenance_lines(prov)]
    (d / "report.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 0
    except _ArgError as e:
        print(f"ERROR 설정 오류: {e}", file=sys.stderr)
        return 1
    model_path = Path(args.model)
    name = f"opt_validate_{model_path.name}"
    final = Path(args.out) / name
    partial = final.with_name(final.name + ".partial")
    old = final.with_name(final.name + ".old")
    try:
        _check_name(name)
        sur = load_surrogate(model_path)
    except (ValueError, OSError) as e:
        print(f"ERROR 설정 오류: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if final.exists() and not args.overwrite:
        print(f"ERROR 이미 있음: {final} (--overwrite로 교체)", file=sys.stderr)
        return 2
    for work in (partial, old):
        if work.exists():
            print(f"ERROR 작업 경로가 이미 있음(지우지 않음): {work}", file=sys.stderr)
            return 2
    cost = CostParams()
    try:
        designs = [evaluate_design(sur, d, cost) for d in pick_designs(args.n, args.seed)]
        Path(args.out).mkdir(parents=True, exist_ok=True)
        partial.mkdir()
        try:
            _write(partial, name, model_path, sur, cost, designs, args)
            if final.exists():
                os.replace(final, old)
                try:
                    os.replace(partial, final)
                except BaseException:
                    os.replace(old, final)
                    raise
                _remove_flat(old)
            else:
                os.replace(partial, final)
        except BaseException:
            _remove_flat(partial)
            raise
    except KeyboardInterrupt:
        print("ERROR 중단 (.partial 정리 완료)", file=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001
        print(f"ERROR 검증 실패: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    print(final)
    return 0


if __name__ == "__main__":
    sys.exit(main())
