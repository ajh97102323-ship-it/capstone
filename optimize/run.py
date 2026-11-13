"""비용 최적화 CLI (specs/003 T006, contracts/optimize-api.md).

    python -m optimize.run [--model DIR] [--out reports] [--name NAME] [--p-h2 5] [--c-layer 10] [--c-fixed 50]
        [--life 20] [--discount 0.05] [--volume V] [--dmax D] [--residual-day T --residual-min X] [--overwrite]

기본 설계(DesignParams())로 N 최적화 + ODE 재검증 후 `<out>/<name>/`에 report.md, results.json, 그림을 쓴다.
출력은 `<name>.partial`에 쓰고 완성 후 이름을 바꾼다. 마지막 줄은 출력 경로.
종료 코드: 0 성공 / 1 설정 오류 / 2 이미 있음 / 3 실패.
민감도(p_H2, c_layer)·Pareto는 항상, --volume이 있으면 N·L/D 최적화와 ld_tradeoff.png도 만든다.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from data.config import _check_name
from physics import CostParams, DesignParams
from surrogate import load_surrogate

from . import report
from .analysis import DEFAULT_GRIDS, pareto, sensitivity
from .layers import optimize_layers, verify_with_ode
from .problem import DEFAULT_MODEL, Problem
from .volume import optimize_volume


class _ArgError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse 기본 종료 코드 2는 "이미 있음"과 겹치므로 1로 바꾼다
        raise _ArgError(message)


def _float(pred, desc):
    def conv(s: str) -> float:
        try:
            v = float(s)
        except ValueError:
            raise argparse.ArgumentTypeError(f"숫자가 아님: {s!r}") from None
        if not pred(v):
            raise argparse.ArgumentTypeError(f"{desc} 이어야 함: {s}")
        return v
    return conv


_positive = _float(lambda v: 0 < v < float("inf"), "양수")
_nonneg = _float(lambda v: 0 <= v < float("inf"), "0 이상")


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="python -m optimize.run", description="MLI 적층 비용 vs 보일오프 손실 비용 최적화")
    p.add_argument("--model", default=DEFAULT_MODEL, help="002 대리모델 디렉터리")
    p.add_argument("--out", default="reports", help="출력 상위 디렉터리")
    p.add_argument("--name", default=None, help="출력 이름 (기본 opt_<모델 이름>)")
    p.add_argument("--p-h2", type=_positive, default=5.0, help="액화수소 가격 [$/kg]")
    p.add_argument("--c-layer", type=_positive, default=10.0, help="MLI 1층당 비용 [$/(m2*layer)]")
    p.add_argument("--c-fixed", type=_nonneg, default=50.0, help="MLI 고정비 [$/m2]")
    p.add_argument("--life", type=_positive, default=20.0, help="수명 [yr]")
    p.add_argument("--discount", type=_nonneg, default=0.05, help="할인율 [-]")
    p.add_argument("--volume", type=_positive, default=None, help="체적 고정 N·L/D 최적화의 목표 체적 [m3]")
    p.add_argument("--dmax", type=_positive, default=None, help="최대 직경 [m] (--volume과 함께)")
    p.add_argument("--residual-day", type=_positive, default=None, help="잔량 목표 시점 [day]")
    p.add_argument("--residual-min", type=_nonneg, default=None, help="그 시점의 최소 잔량비 [-]")
    p.add_argument("--overwrite", action="store_true", help="같은 이름의 결과를 교체")
    return p


def _remove_flat(d: Path) -> None:
    """평평한 출력 디렉터리(파일만)를 지운다. 재귀 삭제는 쓰지 않는다."""
    if not d.exists():
        return
    for f in d.iterdir():
        if f.is_file():
            f.unlink()
    d.rmdir()


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:  # --help
        return e.code if isinstance(e.code, int) else 0
    except _ArgError as e:
        print(f"ERROR 설정 오류: {e}", file=sys.stderr)
        return 1
    if (args.residual_day is None) != (args.residual_min is None):
        print("ERROR 설정 오류: --residual-day와 --residual-min은 함께 줘야 함", file=sys.stderr)
        return 1
    if args.dmax is not None and args.volume is None:
        print("ERROR 설정 오류: --dmax는 --volume과 함께 줘야 함", file=sys.stderr)
        return 1

    model_path = Path(args.model)
    name = args.name if args.name is not None else f"opt_{model_path.name}"
    final = Path(args.out) / name
    partial = final.with_name(final.name + ".partial")
    old = final.with_name(final.name + ".old")
    try:
        _check_name(name)
        design = {k: v for k, v in vars(DesignParams()).items() if k != "Th"}
        residual = None if args.residual_day is None else (args.residual_day, args.residual_min)
        cost = CostParams(c_layer=args.c_layer, c_fixed=args.c_fixed, p_h2=args.p_h2,
                          life_years=args.life, discount=args.discount)
        problem = Problem(design, cost, residual=residual)
        sur = load_surrogate(model_path)
        problem.check(sur)
    except (ValueError, OSError) as e:  # OutOfRangeError는 ValueError
        print(f"ERROR 설정 오류: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if final.exists() and not args.overwrite:
        print(f"ERROR 이미 있음: {final} (--overwrite로 교체)", file=sys.stderr)
        return 2
    for work in (partial, old):
        if work.exists():
            print(f"ERROR 작업 경로가 이미 있음(지우지 않음): {work}", file=sys.stderr)
            return 2

    notes = []
    try:
        result = optimize_layers(sur, problem)
        ver = verify_with_ode(problem, result)
        sens = [sensitivity(sur, problem, k, DEFAULT_GRIDS[k]) for k in ("p_h2", "c_layer")]
        par = pareto(sur, problem)
        vol = None
        if args.volume is not None:
            vol = optimize_volume(sur, problem.design, cost, args.volume, D_max=args.dmax)
        Path(args.out).mkdir(parents=True, exist_ok=True)
        partial.mkdir()
        try:
            report.write_outputs(partial, name, model_path.name, problem, result, ver, notes, vol, sens, par,
                                report.provenance(sur, model_path))
            if final.exists():  # --overwrite: 새 결과가 완성된 뒤에만 교체
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
    except NotImplementedError as e:
        print(f"ERROR 설정 오류: 아직 지원하지 않음: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ERROR 중단 (.partial 정리 완료)", file=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001
        print(f"ERROR 최적화 실패: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    for w in [*result.warnings, *(vol.warnings if vol else [])]:
        print(f"WARNING {w}", file=sys.stderr)
    print(final)
    return 0


if __name__ == "__main__":
    sys.exit(main())
