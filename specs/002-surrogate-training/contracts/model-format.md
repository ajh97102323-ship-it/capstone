# Contract: 학습된 대리모델 파일과 예측 API

003(비용 최적화)과 004(웹 UI)는 이 계약에 의존한다. 필드 의미는 [data-model.md](../data-model.md)를 참고한다.

## 디렉터리 배치

```text
models/<name>/
├── model.joblib     # scaler + MLP + 특성 정의 (joblib, 신뢰할 수 있는 로컬 파일만 불러올 것)
├── meta.json        # 학습 설정·범위·버전·지표
├── tuning.json      # (선택) 하이퍼파라미터 탐색 기록
└── report/          # 평가 보고서
    ├── report.md
    ├── metrics.json
    ├── loss_history.png
    ├── worst_curves.png
    ├── error_by_input.png
    └── cost_error.png
```

학습 중에는 `models/<name>.partial/`을 쓴다. 이 이름의 디렉터리는 완성된 모델이 아니며 불러오지 않는다.

## `meta.json`

```json
{
  "format_version": 1,
  "name": "mlp_lhs_n10000_seed42_seed0",
  "created_at": "2026-11-13T16:00:00+09:00",
  "dataset": {"path": "data/datasets/lhs_n10000_seed42", "name": "lhs_n10000_seed42",
              "physics": {"version": "0.1.0", "sha256": "30fca2..."}},
  "training": {"hidden": [128, 128, 128], "learning_rate": 0.001, "batch_size": 128,
               "alpha": 0.0001, "max_epochs": 400, "patience": 20, "seed": 0, "best_epoch": 123},
  "features": {"names": ["N", "Nbar", "eps", "G_sup", "Pv0", "G_out", "S", "R", "LD", "fill", "log10_k"],
               "log_inputs": ["G_sup", "Pv0", "G_out", "S"], "Th": 300.0},
  "train_range": {"names": ["N", "..."], "lo": [10, "..."], "hi": [120, "..."]},
  "t_days": [0.0, "...", 365.0],
  "versions": {"python": "3.13.14", "numpy": "2.4.6", "sklearn": "..."},
  "metrics": {"test_r2": 0.9995, "ratio365_mae": 0.0046, "ratio365_max": 0.04, "speedup": 800,
              "sc_pass": {"SC-001": true, "SC-002": false, "SC-003": true, "SC-004": true}}
}
```

- 비용·경제 변수 관련 키는 없다(헌법 원칙 IV).
- 읽는 쪽은 모르는 `format_version`이면 오류를 낸다.

## Python API (`surrogate`)

| 함수 / 메서드 | 반환 | 비고 |
|---|---|---|
| `load_surrogate(path) -> Surrogate` | 모델 객체 | `.partial` 경로 거부. sklearn 버전이 저장 때와 다르면 경고 |
| `Surrogate.predict(X) -> np.ndarray (n, 100)` | 잔량비 곡선 | X는 (n, 10) 물리 단위, `input_names` 순서. 후처리 포함. 범위 밖이면 `OutOfRangeError` |
| `Surrogate.predict_one(**inputs) -> np.ndarray (100,)` | 곡선 하나 | 키워드는 `DesignParams` 필드 이름 |
| `Surrogate.ratio365(X) -> np.ndarray (n,)` | 365일 잔량비 | `cost_from_curve`에 바로 넘김 (FR-009) |
| `Surrogate.check_range(X)` | 없음 / `OutOfRangeError` | UI 입력 검사에 재사용 |
| `Surrogate.t` | (100,) [day] | 시간 격자 |
| `Surrogate.train_range` | dict | UI 슬라이더 범위 |
| `Surrogate.physics_matches() -> bool` | 데이터셋 물리 지문이 현재 `physics_fingerprint()`와 같은지 | |
| `OutOfRangeError` | `ValueError` 하위 클래스 | 속성: `name`, `value`, `lo`, `hi` |

## 명령줄

| 명령 | 설명 | 종료 코드 |
|---|---|---|
| `python -m surrogate.train [--dataset DIR] [--out models] [--name NAME] [--seed 0] [--hidden 128,128,128] [--lr 1e-3] [--batch 128] [--alpha 1e-4] [--max-epochs 400] [--patience 20] [--overwrite] [--no-report]` | 학습 후 모델과 평가 보고서 저장. 마지막 줄에 모델 경로 | 0 성공 / 1 설정 오류 / 2 이미 있음 / 3 실패·중단 |
| `python -m surrogate.evaluate MODEL_DIR` | 평가 보고서를 다시 만든다 | 0 / 1 |
| `python -m surrogate.tune [--dataset DIR] [--trials 30] [--seed 0] [--name NAME]` | Optuna 탐색 후 최적 설정으로 학습·저장 (US2) | train과 같음 |

데이터셋의 물리 모델 지문이 현재와 다르면 `train`은 stderr에 `WARNING [PHYSICS_MISMATCH]`를 출력하고 계속한다(001 FR-014a).
