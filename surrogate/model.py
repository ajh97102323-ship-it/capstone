"""대리모델 `Surrogate` (specs/002 T005, research R3~R6, contracts/model-format.md).

설계 입력 10개 → 0~365일 잔량비 곡선 100점. 입력은 특성 11개로 바꿔 표준화한 뒤 MLP가 시점 1~99를 출력하고
(시점 0은 항상 1), 후처리(`[0,1]` 자르기 → 앞에 1 추가 → 누적 최솟값)로 0~1·단조 비증가를 보장한다.
"""
from __future__ import annotations

import copy
import json
import os
import platform
import shutil
import warnings
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from data.config import _check_name  # 이름 규칙은 001과 같다
from data.versioning import physics_fingerprint
from surrogate import features as F

FORMAT_VERSION = 1
_RANGE_RTOL = 1e-9  # 범위 검사 부동소수점 여유: 폭의 1e-9 배 (샘플러가 경계를 1 ulp 넘는 경우 대비)


class OutOfRangeError(ValueError):
    """입력이 학습 범위 밖 (외삽 금지, 헌법 원칙 V)."""

    def __init__(self, name: str, value: float, lo: float, hi: float):
        self.name, self.value, self.lo, self.hi = name, value, lo, hi
        super().__init__(f"{name}={value!r}이 학습 범위 [{lo}, {hi}] 밖")


class ModelExistsError(FileExistsError):
    """대상 모델 디렉터리 또는 작업용 `.partial`/`.old` 경로가 이미 있음."""


def postprocess(raw: np.ndarray) -> np.ndarray:
    """MLP 출력 (n, 99) → 곡선 (n, 100). [0,1] 자르기, 맨 앞에 1, 누적 최솟값 (research R3)."""
    Y = np.clip(np.asarray(raw, dtype=np.float64), 0.0, 1.0)
    Y = np.concatenate([np.ones((Y.shape[0], 1)), Y], axis=1)
    return np.minimum.accumulate(Y, axis=1)


def _mse(mlp, S, Y) -> float:
    """후처리 후 시점 1~99의 평균제곱오차 (조기 종료·탐색의 기준)."""
    P = postprocess(mlp.predict(S))
    return float(np.mean((P[:, 1:] - Y[:, 1:]) ** 2))


def _partial(final: Path) -> Path:
    return final.with_name(final.name + ".partial")


def _old(final: Path) -> Path:
    return final.with_name(final.name + ".old")


def check_model_target(final, overwrite: bool = False) -> None:
    """저장 전에 이름과 대상·작업 경로를 확인한다. 아무것도 만들거나 지우지 않는다."""
    final = Path(final)
    _check_name(final.name)
    if final.exists() and not overwrite:
        raise ModelExistsError(f"모델이 이미 있음: {final} (--overwrite로 교체)")
    for work in (_partial(final), _old(final)):
        if work.exists():
            raise ModelExistsError(f"작업 경로가 이미 있음(지우지 않음): {work}. 확인 후 직접 옮기거나 지우라")


def _json_default(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"JSON으로 쓸 수 없음: {type(o)}")


class Surrogate:
    """잔량비 곡선 대리모델. `fit`으로 학습하거나 `load_surrogate`로 불러온다."""

    def __init__(self, hidden=(128, 128, 128), learning_rate: float = 1e-3, batch_size: int = 128,
                 alpha: float = 1e-4, max_epochs: int = 400, patience: int = 20, seed: int = 0):
        self.hidden = tuple(int(h) for h in hidden)
        self.learning_rate = float(learning_rate)
        self.batch_size = int(batch_size)
        self.alpha = float(alpha)
        self.max_epochs = int(max_epochs)
        self.patience = int(patience)
        self.seed = int(seed)
        if not self.hidden or min(self.hidden) < 1:
            raise ValueError(f"hidden은 양의 정수 1개 이상이어야 함: {hidden!r}")
        if not self.learning_rate > 0 or self.batch_size < 1 or self.alpha < 0:
            raise ValueError("learning_rate > 0, batch_size >= 1, alpha >= 0 이어야 함")
        if self.max_epochs < 1 or self.patience < 1 or self.seed < 0:
            raise ValueError("max_epochs >= 1, patience >= 1, seed >= 0 이어야 함")
        self.mlp = None
        self.scaler = None
        self.history = None
        self.best_epoch = None

    # ---------- 속성 ----------

    @property
    def training(self) -> dict:
        """학습 설정과 결과 epoch (meta.json의 training)."""
        return {"hidden": list(self.hidden), "learning_rate": self.learning_rate,
                "batch_size": self.batch_size, "alpha": self.alpha, "max_epochs": self.max_epochs,
                "patience": self.patience, "seed": self.seed, "best_epoch": self.best_epoch}

    @property
    def t(self) -> np.ndarray:
        """시간 격자 [day] (100,)."""
        return self._t

    @property
    def train_range(self) -> dict:
        """학습 범위 {"names", "lo", "hi"} (UI 슬라이더 범위)."""
        return {"names": list(self.input_names), "lo": self._lo.tolist(), "hi": self._hi.tolist()}

    # ---------- 학습 ----------

    def fit(self, ds, dataset_path=None, log=None) -> "Surrogate":
        """데이터셋의 train 세트로 학습하고 val 세트로 조기 종료·모델 선택을 한다. test 세트는 쓰지 않는다.

        매 epoch `partial_fit`을 한 번 호출하고(학습 세트는 시드 고정으로 섞음), 후처리 후 검증 MSE가
        `patience` epoch 동안 갱신되지 않으면 멈춘다. 가장 좋았던 epoch의 가중치를 최종 모델로 쓴다(R4).
        `log(epoch, train_mse, val_mse)`가 있으면 epoch마다 부른다.
        """
        names = list(ds.input_names)
        Xtr, Ytr, _ = ds.part("train")
        Xva, Yva, _ = ds.part("val")
        if len(Xtr) == 0 or len(Xva) == 0:
            raise ValueError(f"train({len(Xtr)})과 val({len(Xva)}) 세트가 모두 비어 있지 않아야 함")
        Th = float(ds.config.get("fixed", {}).get("Th", F.TH_DEFAULT))  # [K]
        log_inputs = [n for n, s in zip(names, ds.input_scales) if s == "log"]
        Ftr = F.build_features(Xtr, names, Th, log_inputs)
        Fva = F.build_features(Xva, names, Th, log_inputs)
        scaler = StandardScaler().fit(Ftr)
        Str, Sva = scaler.transform(Ftr), scaler.transform(Fva)

        mlp = MLPRegressor(hidden_layer_sizes=self.hidden, activation="relu", solver="adam", alpha=self.alpha,
                           batch_size=min(self.batch_size, len(Xtr)), learning_rate_init=self.learning_rate,
                           shuffle=False, random_state=self.seed)  # 섞기는 아래에서 직접 한다
        rng = np.random.default_rng(self.seed)
        train_hist, val_hist = [], []
        best_val, best_epoch, best_w = np.inf, 0, None
        for epoch in range(1, self.max_epochs + 1):
            perm = rng.permutation(len(Str))
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # partial_fit 반복 호출 시 수렴 경고 등
                mlp.partial_fit(Str[perm], Ytr[perm, 1:])
            tr_mse, va_mse = _mse(mlp, Str, Ytr), _mse(mlp, Sva, Yva)
            train_hist.append(tr_mse)
            val_hist.append(va_mse)
            if log is not None:
                log(epoch, tr_mse, va_mse)
            if va_mse < best_val:
                best_val, best_epoch = va_mse, epoch
                best_w = ([c.copy() for c in mlp.coefs_], [b.copy() for b in mlp.intercepts_])
            elif epoch - best_epoch >= self.patience:
                break
        mlp.coefs_, mlp.intercepts_ = best_w

        self.mlp, self.scaler = mlp, scaler
        self.history = {"train_mse": train_hist, "val_mse": val_hist}
        self.best_epoch = best_epoch
        self.input_names = names
        self.log_inputs = log_inputs
        self.Th = Th
        self._lo = np.asarray(ds.input_lo, dtype=np.float64).copy()
        self._hi = np.asarray(ds.input_hi, dtype=np.float64).copy()
        self._t = np.asarray(ds.t, dtype=np.float64).copy()
        self.dataset_info = {
            "path": None if dataset_path is None else str(dataset_path),
            "name": ds.config.get("name"),
            "physics": copy.deepcopy(ds.config.get("physics")),
        }
        return self

    # ---------- 예측 ----------

    def _check_fitted(self):
        if self.mlp is None:
            raise RuntimeError("학습되지 않은 모델 (fit 또는 load_surrogate 먼저)")

    def _as_2d(self, X) -> np.ndarray:
        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1:
            X = X[None, :]
        if X.ndim != 2 or X.shape[1] != len(self.input_names):
            raise ValueError(f"X는 (n, {len(self.input_names)}) 이어야 함 ({self.input_names}): shape {X.shape}")
        return X

    def check_range(self, X) -> None:
        """학습 범위 밖 입력이 있으면 첫 위반에 대해 `OutOfRangeError`. N의 실수값은 허용한다."""
        self._check_fitted()
        X = self._as_2d(X)
        tol = _RANGE_RTOL * (self._hi - self._lo)
        ok = (X >= self._lo - tol) & (X <= self._hi + tol)  # NaN은 False
        if not ok.all():
            i, j = np.argwhere(~ok)[0]
            raise OutOfRangeError(self.input_names[j], float(X[i, j]), float(self._lo[j]), float(self._hi[j]))

    def predict(self, X) -> np.ndarray:
        """잔량비 곡선 (n, 100). X는 (n, 10) 물리 단위, `input_names` 순서. 후처리 포함."""
        self._check_fitted()
        X = self._as_2d(X)
        self.check_range(X)
        Z = F.build_features(X, self.input_names, self.Th, self.log_inputs)
        return postprocess(self.mlp.predict(self.scaler.transform(Z)))

    def predict_one(self, **inputs) -> np.ndarray:
        """곡선 하나 (100,). 키워드는 `DesignParams` 필드 이름(input_names 전부, 외부 온도는 받지 않는다)."""
        self._check_fitted()
        missing = [n for n in self.input_names if n not in inputs]
        extra = sorted(set(inputs) - set(self.input_names))
        if missing or extra:
            raise ValueError(f"입력 이름이 맞지 않음: 빠짐 {missing}, 남음 {extra}")
        return self.predict(np.array([[float(inputs[n]) for n in self.input_names]]))[0]

    def ratio365(self, X) -> np.ndarray:
        """365일 잔량비 (n,) = predict(X)[:, -1] (`cost_from_curve`에 바로 넘긴다)."""
        return self.predict(X)[:, -1]

    def physics_matches(self) -> bool:
        """학습 데이터셋의 물리 모델 지문이 현재 `physics_fingerprint()`와 같은지."""
        stored = self.dataset_info.get("physics")
        cur = physics_fingerprint()
        return bool(stored) and stored.get("version") == cur["version"] and stored.get("sha256") == cur["sha256"]

    # ---------- 저장 ----------

    def _meta(self, name: str, metrics) -> dict:
        return {
            "format_version": FORMAT_VERSION,
            "name": name,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "dataset": copy.deepcopy(self.dataset_info),
            "training": self.training,
            "features": {"names": list(F.FEATURE_NAMES), "log_inputs": list(self.log_inputs), "Th": self.Th,
                         "w_table": {"fill": [float(F.W_FILL_GRID[0]), float(F.W_FILL_GRID[-1]), len(F.W_FILL_GRID)],
                                     "LD": [float(F.W_LD_GRID[0]), float(F.W_LD_GRID[-1]), len(F.W_LD_GRID)]}},
            "train_range": self.train_range,
            "t_days": self._t.tolist(),
            "versions": {"python": platform.python_version(), "numpy": np.__version__,
                         "sklearn": sklearn.__version__, "joblib": joblib.__version__},
            "metrics": dict(metrics) if metrics else {},
        }

    def _payload(self) -> dict:
        return {"format_version": FORMAT_VERSION, "scaler": self.scaler, "mlp": self.mlp,
                "input_names": list(self.input_names), "log_inputs": list(self.log_inputs), "Th": self.Th,
                "lo": self._lo, "hi": self._hi, "t": self._t, "training": self.training,
                "history": self.history, "dataset_info": self.dataset_info,
                "sklearn_version": sklearn.__version__}

    def save(self, path, overwrite: bool = False, metrics=None, write_extra=None) -> Path:
        """`<path>.partial/`에 쓴 뒤 이름을 바꿔 원자적으로 저장한다 (research R6). 반환: 최종 경로.

        write_extra(partial_dir)가 있으면 model.joblib·meta.json을 쓴 뒤 호출한다(보고서 등).
        실패·중단(KeyboardInterrupt 포함) 시 `.partial`을 지우고 기존 모델은 그대로 둔다.
        """
        self._check_fitted()
        final = Path(path)
        check_model_target(final, overwrite)
        partial, old = _partial(final), _old(final)
        final.parent.mkdir(parents=True, exist_ok=True)
        partial.mkdir()  # 이 시점 이후에 만든 .partial만 우리가 지운다
        try:
            joblib.dump(self._payload(), partial / "model.joblib")
            with open(partial / "meta.json", "w", encoding="utf-8", newline="\n") as fh:
                json.dump(self._meta(final.name, metrics), fh, ensure_ascii=False, indent=2,
                          default=_json_default)
                fh.write("\n")
            if write_extra is not None:
                write_extra(partial)
            if final.exists():  # overwrite: 새 모델이 완성된 뒤에만 교체
                os.replace(final, old)
                try:
                    os.replace(partial, final)
                except BaseException:
                    os.replace(old, final)  # 기존 모델 복구
                    raise
                shutil.rmtree(old, ignore_errors=True)
            else:
                os.replace(partial, final)
        except BaseException:
            shutil.rmtree(partial, ignore_errors=True)
            raise
        return final


def load_surrogate(path) -> Surrogate:
    """저장된 모델을 읽는다. `.partial` 경로와 모르는 format_version은 거부한다.
    joblib(pickle)이므로 신뢰할 수 있는 로컬 파일만 불러올 것. sklearn 버전이 다르면 경고한다."""
    path = Path(path)
    if path.name.lower().endswith(".partial"):
        raise ValueError(f"완성되지 않은 모델(.partial)은 읽을 수 없음: {path}")
    meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
    if meta.get("format_version") != FORMAT_VERSION:
        raise ValueError(f"지원하지 않는 format_version {meta.get('format_version')!r} "
                         f"(지원: {FORMAT_VERSION}): {path}")
    saved_ver = meta.get("versions", {}).get("sklearn")
    if saved_ver != sklearn.__version__:
        warnings.warn(f"scikit-learn 버전이 저장 때({saved_ver})와 다름({sklearn.__version__}): {path}",
                      stacklevel=2)
    p = joblib.load(path / "model.joblib")
    if p.get("format_version") != FORMAT_VERSION:
        raise ValueError(f"model.joblib의 format_version이 맞지 않음: {p.get('format_version')!r}")
    tr = p["training"]
    s = Surrogate(hidden=tr["hidden"], learning_rate=tr["learning_rate"], batch_size=tr["batch_size"],
                  alpha=tr["alpha"], max_epochs=tr["max_epochs"], patience=tr["patience"], seed=tr["seed"])
    s.best_epoch = tr["best_epoch"]
    s.mlp, s.scaler, s.history = p["mlp"], p["scaler"], p["history"]
    s.input_names, s.log_inputs, s.Th = list(p["input_names"]), list(p["log_inputs"]), float(p["Th"])
    s._lo, s._hi, s._t = p["lo"], p["hi"], p["t"]
    s.dataset_info = p["dataset_info"]
    return s
