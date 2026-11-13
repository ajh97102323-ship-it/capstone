"""대리모델 학습 CLI (specs/002 T009, contracts/model-format.md).

    python -m surrogate.train [--dataset DIR] [--out models] [--name NAME] [--seed 0] [--hidden 128,128,128]
        [--lr 1e-3] [--batch 128] [--alpha 1e-4] [--max-epochs 400] [--patience 20] [--overwrite] [--no-report]

학습 후 `<out>/<name>/`에 model.joblib, meta.json, report/를 원자적으로 저장하고 마지막 줄에 모델 경로를 출력한다.
종료 코드: 0 성공 / 1 설정 오류 / 2 이미 있음 / 3 학습 실패·중단.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from data.config import _check_name
from data.io import load_dataset
from data.versioning import physics_fingerprint
from surrogate import evaluate
from surrogate.model import ModelExistsError, Surrogate, check_model_target

DEFAULT_DATASET = "data/datasets/lhs_n10000_seed42"
LOG_EVERY = 10  # 진행 출력 간격 [epoch]


class _ArgError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse 기본(종료 코드 2)은 "이미 있음"과 겹치므로 설정 오류(1)로 바꾼다
        raise _ArgError(message)


def _hidden(s: str) -> tuple:
    try:
        h = tuple(int(v) for v in s.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(f"--hidden은 쉼표로 구분한 양의 정수여야 함: {s!r}") from None
    if not h or min(h) < 1:
        raise argparse.ArgumentTypeError(f"--hidden의 각 층은 1 이상이어야 함: {s!r}")
    return h


def _positive_float(s: str) -> float:
    v = float(s)
    if not v > 0:
        raise argparse.ArgumentTypeError(f"0보다 커야 함: {s!r}")
    return v


def _nonneg_float(s: str) -> float:
    v = float(s)
    if not v >= 0:
        raise argparse.ArgumentTypeError(f"0 이상이어야 함: {s!r}")
    return v


def _int_min(minimum: int):
    def conv(s: str) -> int:
        v = int(s)
        if v < minimum:
            raise argparse.ArgumentTypeError(f"{minimum} 이상이어야 함: {s!r}")
        return v
    return conv


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="python -m surrogate.train", description="잔량 곡선 대리모델 학습 (specs/002)")
    p.add_argument("--dataset", default=DEFAULT_DATASET, help=f"데이터셋 디렉터리 (기본 {DEFAULT_DATASET})")
    p.add_argument("--out", default="models", help="출력 상위 디렉터리 (기본 models)")
    p.add_argument("--name", default=None, help="모델 이름 (기본 mlp_<데이터셋 이름>_seed<seed>)")
    p.add_argument("--seed", type=_int_min(0), default=0, help="학습 시드 (기본 0)")
    p.add_argument("--hidden", type=_hidden, default=(128, 128, 128), help="은닉층 노드 수, 쉼표 구분 (기본 128,128,128)")
    p.add_argument("--lr", type=_positive_float, default=1e-3, help="학습률 (기본 1e-3)")
    p.add_argument("--batch", type=_int_min(1), default=128, help="미니배치 크기 (기본 128)")
    p.add_argument("--alpha", type=_nonneg_float, default=1e-4, help="L2 가중치 감쇠 (기본 1e-4)")
    p.add_argument("--max-epochs", type=_int_min(1), default=400, help="최대 epoch (기본 400)")
    p.add_argument("--patience", type=_int_min(1), default=20, help="검증 MSE 비갱신 허용 epoch (기본 20)")
    p.add_argument("--overwrite", action="store_true", help="같은 이름이 있으면 완성 후 교체")
    p.add_argument("--no-report", action="store_true", help="평가 보고서(report/)를 만들지 않는다")
    return p


def warn_if_physics_mismatch(ds) -> bool:
    """데이터셋의 물리 모델 지문이 현재와 다르면 stderr에 경고한다 (001 FR-014a). 다르면 True."""
    stored, cur = ds.config.get("physics"), physics_fingerprint()
    if stored and stored.get("version") == cur["version"] and stored.get("sha256") == cur["sha256"]:
        return False
    print(f"WARNING [PHYSICS_MISMATCH] 데이터셋 물리 모델 {stored}이(가) 현재 {cur}와 다름. "
          "옛 데이터로 학습한 모델이므로 데이터 재생성·재학습 여부를 판단하라", file=sys.stderr, flush=True)
    return True


def _progress(epoch, tr_mse, va_mse):
    if epoch == 1 or epoch % LOG_EVERY == 0:
        print(f"[train] epoch {epoch}: train MSE {tr_mse:.3e}, val MSE {va_mse:.3e}", flush=True)


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:  # --help
        return e.code if isinstance(e.code, int) else 0
    except _ArgError as e:
        print(f"ERROR 설정 오류: {e}", file=sys.stderr)
        return 1

    ds_path = Path(args.dataset)
    name = args.name if args.name is not None else f"mlp_{ds_path.name}_seed{args.seed}"
    final = Path(args.out) / name
    try:
        _check_name(name)
        check_model_target(final, args.overwrite)
    except ModelExistsError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"ERROR 설정 오류: {e}", file=sys.stderr)
        return 1
    try:
        ds = load_dataset(ds_path)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR 설정 오류: 데이터셋을 읽을 수 없음: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    try:
        warn_if_physics_mismatch(ds)
        print(f"[train] {name}: dataset {ds_path}, hidden {list(args.hidden)}, seed {args.seed}", flush=True)
        sur = Surrogate(hidden=args.hidden, learning_rate=args.lr, batch_size=args.batch, alpha=args.alpha,
                        max_epochs=args.max_epochs, patience=args.patience, seed=args.seed)
        sur.fit(ds, dataset_path=args.dataset, log=_progress)
        print(f"[train] best epoch {sur.best_epoch} / {len(sur.history['val_mse'])}, "
              f"val MSE {min(sur.history['val_mse']):.3e}", flush=True)
        metrics = evaluate.evaluate_model(sur, ds)
        print("[train] " + ", ".join(f"{k} {'PASS' if v else 'FAIL'}" for k, v in metrics["sc_pass"].items())
              + f" (R2 {metrics['test_r2']:.5f}, 365d MAE {metrics['ratio365_mae']:.4f}, "
              f"max {metrics['ratio365_max']:.4f}, speedup {metrics['speedup']:.0f}x)", flush=True)

        def extra(partial_dir):
            if not args.no_report:
                evaluate.write_report(sur, ds, metrics, partial_dir / "report")

        path = sur.save(final, overwrite=args.overwrite, metrics=evaluate.meta_metrics(metrics),
                        write_extra=extra)
    except ModelExistsError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("ERROR 학습 중단 (.partial 정리 완료)", file=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001
        print(f"ERROR 학습 실패: {type(e).__name__}: {e} (.partial 정리 완료)", file=sys.stderr)
        return 3
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
