"""데이터셋 생성 파이프라인과 CLI (specs/001 T019, contracts/cli.md).

    python -m data.generate [--n INT] [--seed INT] [--out DIR] [--name STR] [--overwrite]

LHS 샘플링 → 샘플마다 물리 모델 시뮬레이션·품질 필터 → 70/15/15 분할 → 원자적 저장.
종료 코드: 0 성공(경고 포함) / 1 설정 오류 / 2 대상이 이미 있음 / 3 생성 실패·중단.
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

from data.config import GenerationConfig
from data.io import DatasetExistsError, check_target, write_dataset
from data.sampling import sample_inputs
from data.simulate import AUX_NAMES, Rejection, run_sample
from data.split import split_labels
from data.versioning import physics_fingerprint

SPLIT_NAMES = ("train", "val", "test")
REJECT_WARN_RATE = 0.01   # 제외 비율 경고 기준 [-] (FR-011)
PROGRESS_EVERY = 1000     # 진행 상황 출력 간격 [samples]


def _rate(mask: np.ndarray):
    """bool 배열의 True 비율. 빈 배열이면 None."""
    return float(mask.mean()) if mask.size else None


def _pct(x) -> str:
    return "n/a" if x is None else f"{100.0 * x:.1f}"


def generate(cfg: GenerationConfig, out_dir, overwrite: bool = False) -> Path:
    """cfg로 데이터셋을 만들어 `out_dir/cfg.name/`에 저장하고 그 경로를 돌려준다."""
    out_dir = Path(out_dir)
    final_dir = out_dir / cfg.name
    check_target(final_dir, overwrite)  # 시작 전에 멈춘다 (research R10, T014⑪)

    t0 = time.perf_counter()
    fp = physics_fingerprint()
    n = cfg.n_requested
    print(f"[generate] {cfg.name}: {n} samples, physics {fp['version']} ({fp['sha256'][:6]}...)",
          flush=True)

    ss_lhs, ss_split, _ss_subset = np.random.SeedSequence(cfg.seed).spawn(3)
    X_all = sample_inputs(cfg.inputs, n, np.random.default_rng(ss_lhs))
    names = [s.name for s in cfg.inputs]

    keep_ids, Ys, auxs, depl, rejected = [], [], [], [], []
    for i in range(n):
        res = run_sample(X_all[i], cfg.inputs, cfg)
        if isinstance(res, Rejection):
            rejected.append({"sample_id": i, "x": X_all[i].tolist(), "reason": res.reason,
                             "detail": res.detail})
        else:
            keep_ids.append(i)
            Ys.append(res.Y)
            auxs.append(res.aux)
            depl.append(bool(res.depleted))
        done = i + 1
        if done % PROGRESS_EVERY == 0 or (done == n and n >= PROGRESS_EVERY):
            tail = f" ({time.perf_counter() - t0:.1f} s)" if done == n else ""
            print(f"[generate] {done}/{n}{tail}", flush=True)

    n_valid = len(keep_ids)
    ids = np.asarray(keep_ids, dtype=np.int64)
    X = X_all[ids] if n_valid else np.empty((0, len(names)), dtype=np.float64)
    Y = np.vstack(Ys) if n_valid else np.empty((0, cfg.n_points), dtype=np.float64)
    aux = np.vstack(auxs) if n_valid else np.empty((0, len(AUX_NAMES)), dtype=np.float64)
    depleted = np.asarray(depl, dtype=bool)
    split = split_labels(n_valid, cfg.split, np.random.default_rng(ss_split))

    n_rejected = len(rejected)
    reject_rate = n_rejected / n
    by_reason = dict(sorted(Counter(r["reason"] for r in rejected).items()))
    warnings = []
    if reject_rate > REJECT_WARN_RATE:
        msg = (f"제외 비율 {100 * reject_rate:.2f}%가 {100 * REJECT_WARN_RATE:.0f}%를 넘음 "
               f"({by_reason}). 물리 모델이나 입력 범위를 확인하라")
        warnings.append({"code": "REJECT_HIGH", "message": msg})
        print(f"WARNING [REJECT_HIGH] {msg}", file=sys.stderr, flush=True)

    split_counts = {nm: int((split == k).sum()) for k, nm in enumerate(SPLIT_NAMES)}
    depleted_rate = _rate(depleted)
    depleted_by_split = {nm: _rate(depleted[split == k]) for k, nm in enumerate(SPLIT_NAMES)}
    summary = {
        "n_requested": n,
        "n_valid": n_valid,
        "n_rejected": n_rejected,
        "reject_rate": reject_rate,
        "rejected_by_reason": by_reason,
        "split_counts": split_counts,
        "depleted_rate": depleted_rate,
        "depleted_rate_by_split": depleted_by_split,
        "elapsed_sec": round(time.perf_counter() - t0, 3),
        "warnings": warnings,
    }

    full_cfg = dataclasses.replace(
        cfg, physics=fp, n_valid=n_valid,
        created_at=datetime.now().astimezone().isoformat(timespec="seconds"))
    arrays = {
        "X": X,
        "Y": Y,
        "t": np.linspace(0.0, cfg.days, cfg.n_points),   # [day]
        "aux": aux,
        "depleted": depleted,
        "split": split,
        "sample_id": ids,
        "input_names": np.array(names, dtype=str),
        "input_scales": np.array([s.scale for s in cfg.inputs], dtype=str),
        "input_lo": np.array([s.lo for s in cfg.inputs], dtype=np.float64),
        "input_hi": np.array([s.hi for s in cfg.inputs], dtype=np.float64),
        "aux_names": np.array(AUX_NAMES, dtype=str),
    }

    reasons = ", ".join(f"{k} {v}" for k, v in by_reason.items())
    rej_txt = f"rejected {n_rejected} ({reasons})" if n_rejected else f"rejected {n_rejected}"
    print(f"[generate] valid {n_valid} / requested {n} ({rej_txt}, {100 * reject_rate:.2f}%)", flush=True)
    print(f"[generate] split train {split_counts['train']} / val {split_counts['val']} / "
          f"test {split_counts['test']}, depleted {_pct(depleted_rate)}% "
          f"(train {_pct(depleted_by_split['train'])} / val {_pct(depleted_by_split['val'])} / "
          f"test {_pct(depleted_by_split['test'])})", flush=True)

    return write_dataset(final_dir, arrays, full_cfg.to_json_dict(), summary, rejected,
                         overwrite=overwrite)


class _ArgError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse 기본(종료 코드 2)은 "이미 있음"과 겹치므로 설정 오류(1)로 바꾼다
        raise _ArgError(message)


def _build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="python -m data.generate", description="대리모델 학습용 데이터셋 생성 (specs/001)")
    p.add_argument("--n", type=int, default=10000, help="요청 샘플 수 (기본 10000)")
    p.add_argument("--seed", type=int, default=42, help="마스터 시드 (기본 42)")
    p.add_argument("--out", default="data/datasets", help="출력 상위 디렉터리 (기본 data/datasets)")
    p.add_argument("--name", default=None, help="데이터셋 이름 (기본 lhs_n{n}_seed{seed})")
    p.add_argument("--overwrite", action="store_true", help="같은 이름이 있으면 완성 후 교체")
    return p


def main(argv=None) -> int:
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as e:  # --help 등: argparse가 도움말을 출력한 뒤 던짐 (T014⑫)
        return e.code if isinstance(e.code, int) else 0
    except _ArgError as e:
        print(f"ERROR 설정 오류: {e}", file=sys.stderr)
        return 1
    try:
        cfg = GenerationConfig(n_requested=args.n, seed=args.seed, name=args.name)
    except ValueError as e:
        print(f"ERROR 설정 오류: {e}", file=sys.stderr)
        return 1

    try:
        path = generate(cfg, Path(args.out), overwrite=args.overwrite)
    except DatasetExistsError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("ERROR 생성 중단 (.partial 정리 완료)", file=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001
        print(f"ERROR 생성 실패: {type(e).__name__}: {e} (.partial 정리 완료)", file=sys.stderr)
        return 3
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
