"""Optuna 하이퍼파라미터 탐색 (specs/002 T011, research R7).

    python -m surrogate.tune [--dataset DIR] [--trials 30] [--seed 0] [--name NAME] [--out models]
        [--overwrite] [--no-report]

TPE(시드 고정)로 은닉층 수·노드 수·학습률·배치 크기·alpha를 탐색한다. 목적함수는 **검증 세트** MSE이며 테스트
세트는 탐색 중에 쓰지 않는다(FR-004). 시도마다 학습 시드는 같다(`--seed`). 가장 좋았던 시도의 모델을 저장하고
탐색 기록을 `<name>/tuning.json`에 남긴다. 같은 설정·시드로 `surrogate.train`을 돌려도 같은 모델이 나온다.
종료 코드는 train과 같다: 0 / 1 설정 오류 / 2 이미 있음 / 3 실패·중단.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import optuna

from data.config import _check_name
from data.io import load_dataset
from surrogate import evaluate
from surrogate.model import ModelExistsError, Surrogate, check_model_target
from surrogate.train import _ArgError, _Parser, _int_min, warn_if_physics_mismatch

DEFAULT_SPACE = {
    "n_layers": (3, 4),            # 은닉층 수
    "width": (64, 256),            # 층당 노드 수
    "lr": (1e-4, 3e-3),            # 학습률 (log)
    "batch": (64, 128, 256),       # 미니배치 크기 (범주)
    "alpha": (1e-6, 1e-2),         # L2 가중치 감쇠 (log)
}
DEFAULT_MAX_EPOCHS = 400
DEFAULT_PATIENCE = 20


def _space_json(space: dict) -> dict:
    return {k: list(v) for k, v in space.items()}


def tune(ds, n_trials: int = 30, seed: int = 0, space: dict | None = None, max_epochs: int | None = None,
         patience: int | None = None, dataset_path=None):
    """탐색을 돌려 (가장 좋은 시도의 학습된 Surrogate, 탐색 기록 dict)를 돌려준다. 파일은 쓰지 않는다.

    테스트 세트는 읽지 않는다(`Surrogate.fit`은 train·val만 쓴다)."""
    if n_trials < 1:
        raise ValueError(f"n_trials는 1 이상이어야 함: {n_trials}")
    space = DEFAULT_SPACE if space is None else space
    max_epochs = DEFAULT_MAX_EPOCHS if max_epochs is None else max_epochs
    patience = DEFAULT_PATIENCE if patience is None else patience
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    trials, best = [], {"mse": float("inf"), "model": None}

    def objective(trial: optuna.Trial) -> float:
        n_layers = trial.suggest_int("n_layers", *space["n_layers"])
        width = trial.suggest_int("width", *space["width"])
        lr = trial.suggest_float("lr", *space["lr"], log=True)
        batch = trial.suggest_categorical("batch", list(space["batch"]))
        alpha = trial.suggest_float("alpha", *space["alpha"], log=True)
        sur = Surrogate(hidden=(width,) * n_layers, learning_rate=lr, batch_size=batch, alpha=alpha,
                        max_epochs=max_epochs, patience=patience, seed=seed)
        sur.fit(ds, dataset_path=dataset_path)
        val = min(sur.history["val_mse"])
        trials.append({"number": trial.number, "val_mse": val, "epochs": len(sur.history["val_mse"]),
                       "best_epoch": sur.best_epoch,
                       "params": {"hidden": list(sur.hidden), "learning_rate": sur.learning_rate,
                                  "batch_size": sur.batch_size, "alpha": sur.alpha}})
        if val < best["mse"]:
            best["mse"], best["model"] = val, sur
        return val

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=n_trials)
    best_trial = min(trials, key=lambda t: (t["val_mse"], t["number"]))
    record = {"seed": seed, "n_trials": n_trials, "sampler": "TPE", "objective": "val_mse",
              "space": _space_json(space), "max_epochs": max_epochs, "patience": patience,
              "trials": trials,
              "best": {"number": best_trial["number"], "val_mse": best_trial["val_mse"],
                       "params": best_trial["params"]}}
    return best["model"], record


def tune_and_save(dataset, out, name: str, n_trials: int = 30, seed: int = 0, space: dict | None = None,
                  max_epochs: int | None = None, patience: int | None = None, overwrite: bool = False,
                  report: bool = True) -> Path:
    """탐색 후 최적 모델과 tuning.json(그리고 report/)을 `<out>/<name>/`에 원자적으로 저장한다."""
    final = Path(out) / name
    _check_name(name)
    check_model_target(final, overwrite)  # 탐색 전에 멈춘다
    ds = load_dataset(dataset)
    warn_if_physics_mismatch(ds)
    sur, record = tune(ds, n_trials, seed, space, max_epochs, patience, dataset_path=str(dataset))
    metrics = evaluate.evaluate_model(sur, ds)  # 테스트 세트는 여기서(탐색이 끝난 뒤) 처음 쓴다

    def extra(partial_dir: Path):
        with open(partial_dir / "tuning.json", "w", encoding="utf-8", newline="\n") as fh:
            json.dump(record, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        if report:
            evaluate.write_report(sur, ds, metrics, partial_dir / "report")

    return sur.save(final, overwrite=overwrite, metrics=evaluate.meta_metrics(metrics), write_extra=extra)


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="python -m surrogate.tune", description="대리모델 하이퍼파라미터 탐색 (specs/002 US2)")
    p.add_argument("--dataset", default="data/datasets/lhs_n10000_seed42", help="데이터셋 디렉터리")
    p.add_argument("--trials", type=_int_min(1), default=30, help="시도 횟수 (기본 30)")
    p.add_argument("--seed", type=_int_min(0), default=0, help="탐색·학습 시드 (기본 0)")
    p.add_argument("--name", default=None, help="모델 이름 (기본 mlp_<데이터셋 이름>_seed<seed>_tuned)")
    p.add_argument("--out", default="models", help="출력 상위 디렉터리 (기본 models)")
    p.add_argument("--overwrite", action="store_true", help="같은 이름이 있으면 완성 후 교체")
    p.add_argument("--no-report", action="store_true", help="평가 보고서(report/)를 만들지 않는다")
    return p


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 0
    except _ArgError as e:
        print(f"ERROR 설정 오류: {e}", file=sys.stderr)
        return 1
    name = args.name if args.name is not None else f"mlp_{Path(args.dataset).name}_seed{args.seed}_tuned"
    try:
        _check_name(name)
        check_model_target(Path(args.out) / name, args.overwrite)
    except ModelExistsError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"ERROR 설정 오류: {e}", file=sys.stderr)
        return 1
    try:
        load_dataset(args.dataset)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR 설정 오류: 데이터셋을 읽을 수 없음: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    try:
        path = tune_and_save(args.dataset, args.out, name, args.trials, args.seed, overwrite=args.overwrite,
                             report=not args.no_report)
    except ModelExistsError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("ERROR 탐색 중단 (.partial 정리 완료)", file=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001
        print(f"ERROR 탐색 실패: {type(e).__name__}: {e} (.partial 정리 완료)", file=sys.stderr)
        return 3
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
