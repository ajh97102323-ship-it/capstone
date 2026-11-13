# Data Model: 잔량 곡선 대리모델 학습과 평가

입력 데이터셋 형식은 001의 [dataset-format 계약](../001-dataset-generation/contracts/dataset-format.md)을 따른다.
모델 파일 배치는 [contracts/model-format.md](contracts/model-format.md)를 참고한다.

## 1. FeatureSpec (입력 특성)

| # | 이름 | 계산 | 비고 |
|---|---|---|---|
| 0~9 | 설계 입력 10개 | 데이터셋 `input_names` 순서. `input_scales == "log"`이면 log10 | 001 data-model 1절 |
| 10 | `log10_k` | `log10(k)`, k는 research R2의 초기 일일 증발 비율 [1/day] | `physics/` 함수·상수로 계산 |

**검증 규칙**
- 입력 순서와 이름은 데이터셋 `input_names`와 같아야 한다(다르면 ValueError).
- k > 0이어야 한다(물리적으로 항상 양수. 0 이하면 계산 오류로 보고 ValueError).
- k는 같은 설계에서 `BoiloffModel(p).heat_to_liquid(0, m0) / (h_fg · m0) × 86400`과 상대 1e-3 이내로 같아야 한다(테스트로 고정).
- 외부 온도는 데이터셋 config의 `fixed.Th`를 쓴다(기본 300 K).

## 2. TrainingConfig (학습 설정)

| 필드 | 형식 | 기본값 | 비고 |
|---|---|---|---|
| `dataset` | 경로 | `data/datasets/lhs_n10000_seed42` | 001 데이터셋 |
| `name` | str | `mlp_<데이터셋 이름>_seed<seed>` | 001과 같은 이름 규칙(영문·숫자·`_-.`, `.partial`/`.old`로 끝나지 않음) |
| `hidden` | tuple[int] | (128, 128, 128) | 층 3~4개, 노드 64~256 (FR-001, FR-010) |
| `learning_rate` | float | 1e-3 | |
| `batch_size` | int | 128 | |
| `alpha` | float | 1e-4 | L2 가중치 감쇠 |
| `max_epochs` | int | 400 | |
| `patience` | int | 20 | 검증 MSE가 갱신되지 않는 epoch 수 |
| `seed` | int | 0 | sklearn `random_state`, 섞기 순서 |

## 3. TrainedSurrogate (학습된 모델)

| 구성요소 | 내용 |
|---|---|
| `scaler` | 학습 세트 특성 11개로 맞춘 StandardScaler |
| `mlp` | 가장 좋았던 epoch의 가중치를 가진 MLPRegressor (출력 99개, 시점 1~99) |
| `feature_spec` | 입력 이름·스케일, k 계산에 쓴 고정값(Th), w 표 격자 설정 |
| `train_range` | `input_names`, `input_lo`, `input_hi` (데이터셋에서 복사) |
| `t` | 시간 격자 [day] (데이터셋 `t`, 100개) |

**예측 규칙 (FR-006~FR-009)**
1. 범위 검사: 입력이 `train_range` 밖이면 `OutOfRangeError(변수, 값, lo, hi)`. N은 실수도 허용.
2. 특성 계산 → 표준화 → MLP 출력 99개
3. 후처리: `[0,1]`로 자름 → 앞에 1 추가 → 누적 최솟값. 결과는 (n, 100), `Y[:,0] == 1`, 0 ≤ Y ≤ 1, 단조 비증가
4. `ratio365(Y) = Y[:, -1]` (000의 `cost_from_curve`에 바로 넘김)

## 4. EvaluationReport (평가 보고서)

| 필드 | 비고 |
|---|---|
| `test_r2`, `test_rmse` | 테스트 세트 곡선 전체(100개 시점) 기준 |
| `ratio365_mae`, `ratio365_max` | 365일 잔량비 절대오차 평균·최대 |
| `near_depletion_mae` | 소진 샘플의 소진 시점 ±10일 구간 시점 오차 평균 |
| `speedup` | 1000개 배치 기준 ODE 대비 배수(research R9) |
| `monotonic_violations`, `range_violations` | 후처리 후 위반 수(항상 0이어야 함) |
| `sc_pass` | `{"SC-001": bool, "SC-002": bool, "SC-003": bool, "SC-004": bool}` |
| `worst` | 365일 오차 상위 12개 샘플의 sample_id, 입력, 오차 |
| `cost_error` | m0 구간별 `p_H2·m0·|δ|` [$/yr] 분포(기본 p_H2 = 5 $/kg) |
| `history` | epoch별 학습·검증 MSE |

## 5. TuningStudy (탐색 기록, User Story 2)

| 필드 | 비고 |
|---|---|
| `trials` | 시도별 하이퍼파라미터, 검증 MSE, epoch 수 |
| `best` | 검증 MSE가 가장 작은 설정 |
| `seed`, `n_trials` | 탐색 재현용 |

## 상태 전이

```
(없음) → 학습 중(models/<name>.partial/) → 완성(models/<name>/: model.joblib + meta.json) → [평가 보고서 추가(report/)]
             └─ 실패·중단 → .partial 삭제, 아무것도 남지 않음
```
