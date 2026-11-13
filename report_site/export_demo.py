"""브라우저 시연용 데이터: 학습된 대리모델 가중치, w 표, 물리 상수를 JSON 하나로 내보낸다.

물리 상수와 계수는 `physics/`에서, 모델은 `surrogate`의 저장 파일에서 그대로 읽는다(값을 손으로 옮겨 적지 않는다).
가중치는 float32 리틀엔디언을 base64로 넣는다. 경제 변수는 넣지 않는다(헌법 IV, 화면에서 후처리).
"""
import base64
import json
from pathlib import Path

import joblib
import numpy as np

from data.versioning import physics_fingerprint
from optimize.layers import FLAT_TOL
from optimize.problem import DEPLETION_TOL
from physics import heat as H
from physics import model as PM
from surrogate import features as F


def _b64(a) -> str:
    return base64.b64encode(np.ascontiguousarray(a, dtype="<f4").tobytes()).decode("ascii")


def payload(model_dir) -> dict:
    model_dir = Path(model_dir)
    d = joblib.load(model_dir / "model.joblib")
    meta = json.loads((model_dir / "meta.json").read_text(encoding="utf-8"))
    mlp, scaler = d["mlp"], d["scaler"]
    if mlp.activation != "relu" or mlp.out_activation_ != "identity":
        raise ValueError(f"지원하지 않는 활성화 함수: {mlp.activation}/{mlp.out_activation_}")
    layers = [{"nin": int(W.shape[0]), "nout": int(W.shape[1]), "W": _b64(W), "b": _b64(b)}
              for W, b in zip(mlp.coefs_, mlp.intercepts_)]
    return {
        "format": 1,
        "meta": {"name": model_dir.name, "dataset": meta["dataset"]["name"],
                 "test_r2": meta.get("metrics", {}).get("test_r2"), "physics": physics_fingerprint()},
        "model": {
            "input_names": list(d["input_names"]), "log_inputs": list(d["log_inputs"]), "Th": float(d["Th"]),
            "lo": [float(x) for x in d["lo"]], "hi": [float(x) for x in d["hi"]],
            "t": [float(x) for x in d["t"]],
            "scaler_mean": [float(x) for x in scaler.mean_], "scaler_scale": [float(x) for x in scaler.scale_],
            "layers": layers,
        },
        "wtable": {"fill": [float(F.W_FILL_GRID[0]), float(F.W_FILL_GRID[-1]), len(F.W_FILL_GRID)],
                   "ld": [float(F.W_LD_GRID[0]), float(F.W_LD_GRID[-1]), len(F.W_LD_GRID)],
                   "values": _b64(F._W_TABLE)},   # [fill i, LD j] 행 우선
        "physics": {"H_FG": PM.H_FG, "T_C": PM.T_C, "RHO_L": PM.RHO_L, "ETA": PM.ETA, "GAP_EXTRA": PM.GAP_EXTRA,
                    "DAY": PM.DAY, "SIM_DAYS": PM.SIM_DAYS, "PA_TO_TORR": H.PA_TO_TORR,
                    "C_S": H.C_S, "EXP_S": H.EXP_S, "C_R": H.C_R, "C_G": H.C_G},
        "optimize": {"DEPLETION_TOL": DEPLETION_TOL, "FLAT_TOL": FLAT_TOL, "N_RANGE": [10, 120]},
    }
