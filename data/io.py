"""데이터셋 원자적 저장과 읽기 (specs/001 T018, research R10, contracts/dataset-format.md).

쓰기: `<final_dir>.partial/`에 모든 파일을 쓴 뒤 `os.replace`로 최종 이름으로 바꾼다. 실패하거나 중단되면
(KeyboardInterrupt 포함) `.partial`을 지우고 예외를 다시 던진다. 덮어쓰기는 새 데이터셋이 완성된 뒤에만
기존 디렉터리를 `<name>.old`로 옮겼다가 지운다.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

FORMAT_VERSION = 1
PART_INDEX = {"train": 0, "val": 1, "test": 2}
NPZ_KEYS = ("X", "Y", "t", "aux", "depleted", "split", "sample_id", "input_names", "input_scales",
            "input_lo", "input_hi", "aux_names")


class DatasetExistsError(FileExistsError):
    """대상 데이터셋 디렉터리가 이미 있고 overwrite가 아님."""


class WorkDirExistsError(FileExistsError):
    """작업용 `<name>.partial`/`<name>.old` 경로가 이미 있음. 사용자 데이터일 수 있으므로 지우지 않고 멈춘다
    (Windows는 대소문자를 구분하지 않아 `foo.PARTIAL`도 `foo.partial`과 같은 경로다, T014⑪)."""


def check_target(final_dir, overwrite: bool = False) -> None:
    """쓰기 전에 대상과 작업 경로를 확인한다. 아무것도 만들거나 지우지 않는다."""
    final_dir = Path(final_dir)
    if final_dir.exists() and not overwrite:
        raise DatasetExistsError(f"데이터셋이 이미 있음: {final_dir} (--overwrite로 교체)")
    for work in (_partial_dir(final_dir), _old_dir(final_dir)):
        if work.exists():
            raise WorkDirExistsError(f"작업 경로가 이미 있음(지우지 않음): {work}. 확인 후 직접 옮기거나 지우라")


def _partial_dir(final_dir: Path) -> Path:
    return final_dir.with_name(final_dir.name + ".partial")


def _old_dir(final_dir: Path) -> Path:
    return final_dir.with_name(final_dir.name + ".old")


def _write_json(path: Path, obj: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def _write_rejected(path: Path, input_names: Sequence[str], rows: Iterable[dict]) -> None:
    """rejected.csv: sample_id, 입력 10개(repr 정밀도), reason, detail. 0건이어도 헤더를 쓴다."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sample_id", *input_names, "reason", "detail"])
        for r in rows:
            w.writerow([int(r["sample_id"]), *(repr(float(v)) for v in r["x"]), r["reason"], r["detail"]])


def _normalize_arrays(arrays: dict) -> dict:
    out = {}
    for k in NPZ_KEYS:
        if k not in arrays:
            raise KeyError(f"dataset.npz 키 누락: {k}")
        v = np.asarray(arrays[k])
        if v.dtype.kind in ("U", "S", "O"):
            v = np.asarray([str(s) for s in v.tolist()], dtype=str)  # 고정 길이 유니코드
        out[k] = v
    extra = sorted(set(arrays) - set(NPZ_KEYS))
    if extra:
        raise KeyError(f"계약에 없는 dataset.npz 키: {extra}")
    return out


def write_dataset(final_dir, arrays: dict, config: dict, summary: dict, rejected_rows,
                  overwrite: bool = False) -> Path:
    """데이터셋 디렉터리를 원자적으로 쓴다. 반환: 최종 디렉터리 경로."""
    final_dir = Path(final_dir)
    check_target(final_dir, overwrite)  # 미리 있는 .partial/.old는 지우지 않고 멈춘다
    partial = _partial_dir(final_dir)
    old = _old_dir(final_dir)
    arrays = _normalize_arrays(arrays)
    config = {**config, "format_version": FORMAT_VERSION}
    rejected_rows = list(rejected_rows)
    input_names = [str(s) for s in arrays["input_names"].tolist()]

    final_dir.parent.mkdir(parents=True, exist_ok=True)
    partial.mkdir()  # 이 시점 이후에 만든 .partial만 우리가 지운다
    try:
        np.savez(partial / "dataset.npz", **arrays)  # 비압축
        _write_json(partial / "config.json", config)
        _write_json(partial / "summary.json", summary)
        _write_rejected(partial / "rejected.csv", input_names, rejected_rows)

        if final_dir.exists():  # overwrite: 새 데이터셋이 완성된 뒤에만 교체
            if old.exists():  # check_target 이후에 생겼다면 지우지 않고 멈춘다
                raise WorkDirExistsError(f"작업 경로가 이미 있음(지우지 않음): {old}")
            os.replace(final_dir, old)
            try:
                os.replace(partial, final_dir)
            except BaseException:
                os.replace(old, final_dir)  # 기존 데이터셋 복구
                raise
            shutil.rmtree(old, ignore_errors=True)
        else:
            os.replace(partial, final_dir)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    return final_dir


@dataclass
class Dataset:
    X: np.ndarray
    Y: np.ndarray
    t: np.ndarray
    aux: np.ndarray
    depleted: np.ndarray
    split: np.ndarray
    sample_id: np.ndarray
    input_names: list
    input_scales: list
    input_lo: np.ndarray
    input_hi: np.ndarray
    aux_names: list
    config: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)

    def part(self, name: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """세트 하나의 (X, Y, aux). name: "train" | "val" | "test"."""
        if name not in PART_INDEX:
            raise ValueError(f"알 수 없는 세트 {name!r} (허용: {list(PART_INDEX)})")
        m = self.split == PART_INDEX[name]
        return self.X[m], self.Y[m], self.aux[m]


def load_dataset(path) -> Dataset:
    """완성된 데이터셋 디렉터리를 읽는다. `.partial` 경로와 모르는 format_version은 거부한다."""
    path = Path(path)
    if path.name.lower().endswith(".partial"):  # 대소문자 무시 (T014⑪)
        raise ValueError(f"완성되지 않은 데이터셋(.partial)은 읽을 수 없음: {path}")
    config = json.loads((path / "config.json").read_text(encoding="utf-8"))
    if config.get("format_version") != FORMAT_VERSION:
        raise ValueError(f"지원하지 않는 format_version {config.get('format_version')!r} "
                         f"(지원: {FORMAT_VERSION}): {path}")
    summary_path = path / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    with np.load(path / "dataset.npz", allow_pickle=False) as z:
        a = {k: z[k] for k in z.files}
    return Dataset(
        X=a["X"], Y=a["Y"], t=a["t"], aux=a["aux"], depleted=a["depleted"], split=a["split"],
        sample_id=a["sample_id"],
        input_names=[str(s) for s in a["input_names"].tolist()],
        input_scales=[str(s) for s in a["input_scales"].tolist()],
        input_lo=a["input_lo"], input_hi=a["input_hi"],
        aux_names=[str(s) for s in a["aux_names"].tolist()],
        config=config, summary=summary,
    )
