# Data Model: 대리모델 학습용 데이터셋 생성

spec의 Key Entities를 필드, 형식, 검증 규칙으로 구체화한다. 파일 배치는 [contracts/dataset-format.md](contracts/dataset-format.md)를 참고한다.

## 1. InputSpec (입력 변수 정의)

변수 하나의 이름, 범위, 스케일. 순서가 곧 `X` 배열의 열 순서다.

| # | name | `DesignParams` 필드 | 단위 | lo | hi | scale |
|---|---|---|---|---|---|---|
| 0 | `N` | `N` | layers | 10 | 120 | int |
| 1 | `Nbar` | `Nbar` | layers/cm | 10 | 30 | linear |
| 2 | `eps` | `eps` | - | 0.02 | 0.06 | linear |
| 3 | `G_sup` | `G_sup` | W/K | 1e-4 | 1e-2 | log |
| 4 | `Pv0` | `Pv0` | Pa | 1e-4 | 1e-1 | log |
| 5 | `G_out` | `G_out` | Pa·m³/s | 1e-9 | 1e-6 | log |
| 6 | `S` | `S` | m³/s | 1e-4 | 1e-2 | log |
| 7 | `R` | `R` | m | 0.3 | 2.5 | linear |
| 8 | `LD` | `LD` | - | 0 | 3 | linear |
| 9 | `fill` | `fill` | - | 0.5 | 0.95 | linear |

**검증 규칙**
- `lo < hi`. 로그 변수는 `lo > 0`. 정수 변수는 `lo`, `hi`가 정수.
- 이름은 `DesignParams` 필드와 일치해야 하며 중복될 수 없다. 생성 설정의 입력 목록은 위 표의 10개 이름을 빠짐없이 가져야 한다.
- 물리적 하한: `R`, `Nbar`, `G_sup`, `Pv0`, `G_out`, `S`는 `lo > 0`, `N`은 `lo ≥ 1`, `LD`는 `lo ≥ 0`, `eps`·`fill`은 `0 < lo < hi ≤ 1`.
- 범위를 기본값에서 바꾸는 것은 허용한다(FR-005). 다만 PLAN.md 3.1과 다르다는 사실을 요약에 표시한다.

## 2. GenerationConfig (생성 설정)

| 필드 | 형식 | 기본값 | 비고 |
|---|---|---|---|
| `name` | str | `lhs_n{n_requested}_seed{seed}` | 출력 디렉터리 이름 |
| `n_requested` | int ≥ 1 | 10000 | FR-002 |
| `seed` | int ≥ 0 | 42 | 마스터 시드. LHS·분할·부분 데이터셋 시드는 여기서 파생 |
| `inputs` | list[InputSpec] | 위 표 | FR-005 |
| `fixed` | dict | `{"Th": 300.0}` | 고정값 [K] |
| `days` | float | 365.0 | 시간 격자 끝 [day] |
| `n_points` | int | 100 | 시간 격자 점 개수, 등간격, 0일 포함 |
| `split` | (float, float, float) | (0.70, 0.15, 0.15) | 합 = 1 |
| `physics` | dict | 자동 | `{"version": "0.1.0", "sha256": "..."}` (FR-014) |
| `created_at` | str (ISO 8601) | 자동 | 생성 일시 |
| `n_valid` | int | 자동 | 저장 시 기록. 요청 수와 함께 남김(Clarification 3) |
| `defaults_modified` | list[str] | 자동 | PLAN.md 기본 범위와 다른 입력 이름 |

## 3. Sample (샘플)

배열 기반으로 저장하며, 행 하나가 샘플 하나다.

| 필드 | 형식 | 단위 | 규칙 |
|---|---|---|---|
| `sample_id` | int | - | LHS에서 생성된 원래 순번(0 … n_requested−1). 제외된 샘플이 있으면 번호가 건너뛴다 |
| `X[i, :]` | float64[10] | 물리 단위(위 표) | 범위 안. N은 정수값 |
| `Y[i, :]` | float64[100] | - | 잔량비. Y[i,0] = 1, 0 ≤ Y ≤ 1, 단조 비증가. 소진 이후 0 |
| `aux[i, 0]` `Q0` | float64 | W | 초기 열유입 Q_L(0) > 0 |
| `aux[i, 1]` `m0` | float64 | kg | 초기 액체 질량 > 0 |
| `aux[i, 2]` `m_lost` | float64 | kg | m0 · (1 − Y[i, −1]), 0 ≤ m_lost ≤ m0 |
| `aux[i, 3]` `A_mli` | float64 | m² | MLI 면적(= 내벽 면적) |
| `aux[i, 4]` `t_empty` | float64 | day | 소진 시각. 소진되지 않으면 `+inf` |
| `depleted[i]` | bool | - | `isfinite(t_empty)`. "소진 없음"을 숫자와 혼동하지 않게 따로 둠 |
| `split[i]` | int8 | - | 0 = train, 1 = val, 2 = test |

**검증 규칙 (FR-010, research R6)**: 하나라도 어기면 Sample이 되지 못하고 RejectionRecord가 된다.
- 소진 샘플: `depleted = True`이면 `Y[i, t > t_empty]`는 모두 0이고 `m_lost = m0`(FR-007).

## 4. RejectionRecord (제외 기록)

| 필드 | 형식 | 비고 |
|---|---|---|
| `sample_id` | int | |
| 입력 10개 | float | InputSpec 순서, 물리 단위 |
| `reason` | str | `solver_error` / `nan` / `negative` / `above_one` / `increasing` / `initial_not_one` |
| `detail` | str | 예외 메시지 또는 위반 위치(시점 인덱스) |

## 5. Dataset (데이터셋)

GenerationConfig 1 : Sample n_valid : RejectionRecord (n_requested − n_valid) : Summary 1 : InspectionReport 0..1 : Subset 0..*

**Summary (생성 요약)**

| 필드 | 비고 |
|---|---|
| `n_requested`, `n_valid`, `n_rejected`, `reject_rate` | Clarification 3 |
| `rejected_by_reason` | 사유별 건수 |
| `split_counts` | `{"train": .., "val": .., "test": ..}` |
| `depleted_rate`, `depleted_rate_by_split` | 전체·세트별 소진 비율 |
| `elapsed_sec` | 생성에 걸린 시간 (SC-001) |
| `warnings` | 제외 비율이 1%를 넘을 때 등 |

**상태 전이**

```
(없음) → 생성 중(<name>.partial/) → 완성(<name>/) → [점검 완료(report/ 추가)] → [부분 데이터셋 추가(subsets/)]
             └─ 실패 또는 중단 → (.partial 삭제, 아무것도 남지 않음)
```
- 완성된 데이터셋의 `dataset.npz`, `config.json`은 이후 바뀌지 않는다. 점검과 부분 데이터셋 생성은 파일을
  추가만 한다.

## 6. InspectionReport (점검 보고서)

| 필드 | 비고 |
|---|---|
| `depleted_rate`, `depleted_rate_by_split` | FR-018 |
| `ratio365_quantiles` | 0, 10, 25, 50, 75, 90, 100% |
| `ratio365_low_share`, `ratio365_high_share` | [0, 0.1], [0.9, 1.0] 구간 비율 (FR-019) |
| `spearman` | 입력 이름 → 365일 잔량비와의 순위상관 |
| `warnings` | 코드와 메시지 목록: `DEPLETED_HIGH`, `RATIO365_SKEWED`, `REJECT_HIGH`, `SPLIT_IMBALANCE` |
| `figures` | `curves.png`, `ratio365_hist.png`, `sensitivity.png`, `scatter.png` |
| `physics_match` | 점검 시점의 물리 모델 해시가 데이터셋과 같은지 |

## 7. Subset (부분 데이터셋)

| 필드 | 형식 | 비고 |
|---|---|---|
| `size` | int | 요청 크기 k ≤ n_valid |
| `subset_seed` | int | 마스터 시드에서 파생: `int(SeedSequence(seed).spawn(3)[2].generate_state(1)[0])`. 크기 k의 분할 시드는 `SeedSequence([subset_seed, k])` |
| `rows` | int[k] | 부모 데이터셋 배열의 행 번호(sample_id가 아님) |
| `split` | int8[k] | 부분 데이터셋 자체의 70/15/15 분할 |

**규칙**: k1 < k2이면 `rows(k1) ⊂ rows(k2)`이며, 앞 k1개가 정확히 같다(FR-020).
