# Research: 비용 최적화 (003)

## R0. 사전 측정

- `physics.evaluate_cost` 1회(기본 설계, 366점) 2.8 ms → N 10~120 전 범위 ODE 스캔이 설계당 약 0.3 s.
- 기본 설계·기본 경제 조건의 근사식 N* = 65.1 (범위 10~120 안).
- 002 대리모델 1000개 배치 예측 1.5 ms → N 111개 평가는 1 ms 수준. SC-003(1초)은 여유가 크다.
- 002 학습 범위: N 10~120, N̄ 10~30, ε 0.02~0.06, G_sup 1e-4~1e-2, Pv0 1e-4~0.1, G_out 1e-9~1e-6, S 1e-4~1e-2,
  R 0.3~2.5, L/D 0~3, fill 0.5~0.95.

## R1. 비용 후처리

- **Decision**: 설계의 형상(R, L/D, fill)은 N과 무관하므로 `BoiloffModel(p)`를 한 번 만들어 `A_mli = mli_area(model)`,
  `m0 = model.m0`를 얻고, N 배열에 대해 `mli_capex(N, A, cost) · cost.crf`와 `cost.p_h2 · m0 · (1 − ratio365)`를
  배열로 계산한다. 식은 `physics.cost`의 함수·속성을 그대로 쓴다(복제 금지). 결과는 `cost_from_curve`와 같아야 한다(테스트).
- **Rationale**: `cost_from_curve`를 N마다 부르면 탱크 테이블을 111번 만든다. 같은 식을 배열로 쓰면 빠르다.
- **Alternatives**: `cost_from_curve` 반복 호출(느림), 비용 식 재구현(헌법 I 위반 위험).

## R2. 탐색 방법

- **Decision**: N은 10~120 정수 전수 탐색(111점), 체적 고정 문제는 L/D 0~3 간격 0.05(61점) × N 정수 격자 전수 탐색.
- **Rationale**: 대리모델 배치 예측 한 번이면 전역 최적이 보장되고 1초 안에 끝난다. Optuna(헌법 기본 도구)는 연속·고차원
  문제에 맞고 여기서는 무작위성만 더한다.
- **Alternatives**: Optuna TPE(재현성·전역성 불리), scipy 연속 최적화(N이 정수).

## R3. 대리모델 기반 소진 판정

- **Decision**: 대리모델 예측 365일 잔량비가 `DEPLETION_TOL = 0.03` 미만이면 소진(후보 제외)으로 본다. ODE 재검증에서는
  `CostResult.depleted`(소진 이벤트)로 판정한다.
- **Rationale**: 002의 365일 잔량비 최대 오차가 0.03 수준이므로, 소진 직전 설계를 보수적으로 제외한다. 소진 설계는 비용이
  과소평가되어 최적점으로 잘못 뽑히기 쉬우므로 놓치는 것보다 보수적으로 빼는 편이 안전하다.
- **Alternatives**: 잔량비 0 기준(후처리 클리핑 탓에 소진 직전을 놓침).

## R4. ODE 재검증 (FR-005, FR-007)

- **Decision**: `verify_with_ode`는 (1) 대리모델 총비용 상위 5개 후보를 ODE로 재계산하고 그중 ODE 총비용 최소를 최종
  추천 N으로 하며, (2) N 전 범위 ODE 스캔으로 실제 최적 N을 구해 대리모델 최적 N과의 차이, 대리모델 최적 N의 ODE 총비용
  상대오차 `(C_ode(N_sur) − C_ode_opt) / C_ode_opt`를 보고한다. 전 범위 스캔은 설계당 0.3 s라 항상 함께 한다.
- **Rationale**: 헌법 I(최종 값은 ODE). 평평한 구간에서 N이 흔들려도 총비용 오차가 주 지표(spec Edge Case).

## R5. 평평한 구간과 경고

- 평평한 구간: 실행 가능 후보 중 총비용 ≤ 최소 × 1.01인 N의 최소~최대.
- 경고 코드(문자열): `BOUNDARY_LOW`/`BOUNDARY_HIGH`(최적 N이 10/120, 범위 확장 검토 안내), `DEPLETED_EXCLUDED`(소진 후보
  제외, 개수 포함), `NO_FEASIBLE`(실행 가능한 N 없음), `RESIDUAL_ACTIVE`(잔량 제약 때문에 무제약 최적과 다름),
  `RESIDUAL_INFEASIBLE`(제약 만족 N 없음, 가장 가까운 N 안내), 체적 고정에서 `LD_BOUNDARY`(최적 L/D가 3).

## R6. 체적 고정 (US3)

- 캡슐 체적 `V = πR²L + 4/3πR³`, `L = 2R·LD` → `R = (V / (π(4/3 + 2·LD)))^(1/3)`. `CapsuleTank(R, 2R·LD).V_tot`와 같아야 한다(테스트).
- 직경 제약: `2R ≤ D_max`. 반경이 학습 범위 [0.3, 2.5] 밖이면 그 L/D는 실행 불가.
- 각 실행 가능 L/D마다 N 111개를 한 번에 예측(최대 6771개 배치). 등고선은 실행 불가 칸을 NaN으로 둔다.
- 최종 후보(최적 (N, L/D) 상위 5개)를 ODE로 재검증한다.

## R7. 민감도 (US2)

- 기본 격자: p_H2 2~15 $/kg 14점, c_layer 5~30 $/(m²·layer) 11점, 수명 10~40 yr 7점, 할인율 0~0.10 6점.
- 각 점에서 대리모델 최적 N, 근사식 N*(`physics.analytic_optimal_layers`), 그리고 `ode_every`점마다 ODE 전 범위 스캔 최적 N.
- SC-004 판정: 대리모델 최적 N 수열이 p_H2에 대해 비감소, c_layer에 대해 비증가이고 처음과 끝이 다르면 통과
  (정수 N이라 인접 점이 같을 수 있음). 근사식과 같은 방향인지도 함께 판정.

## R8. 검증 설계 20개 (SC-001/002)

- `data.sampling`의 LHS(학습 범위, 로그 스케일 입력 포함)로 시드 2026에서 후보를 뽑고, N=10에서 ODE로 소진되지 않는
  설계만 앞에서부터 20개 고른다(전 범위 N이 실행 가능). 탱크 크기 다양성은 m0 범위를 보고서에 적는다.
- SC-001은 **대리모델 최적 N(ODE 재검증 전)**과 ODE 최적 N 차이로 판정한다(엄격한 쪽). 재검증 후 추천 N도 함께 보고한다.

## R9. 잔량 목표 제약 (US4)

- `residual=(t_day, min_ratio)`. 대리모델 곡선을 `np.interp(t_day, sur.t, curve)`로 보간해 `≥ min_ratio`인 N만 실행 가능.
  만족 N이 없으면 `RESIDUAL_INFEASIBLE`과 함께 그 시점 잔량비가 가장 큰 N을 알려 준다. ODE 재검증 시 같은 방식으로 확인.

## R10. Pareto (US4)

- x = MLI 초기 투자비 `capex [$]`, y = 연간 보일오프 질량 `m_lost [kg/yr]`, 소진되지 않은 N에 대해 비지배 집합을 계산한다
  (N ↑ → capex ↑, m_lost ↓라 보통 전부 비지배). 총비용 최적점을 표시한다.

## R11. 테스트용 가짜 대리모델

- `ODESurrogate`: `predict(X)`가 각 행을 `physics.simulate`로 풀어 (n,100) 곡선을 반환하고 `t`, `train_range`, `check_range`를
  002 계약과 같게 제공한다. 최적화 로직 테스트가 학습된 모델 정확도에 좌우되지 않게 한다. 실제 모델은 `validate`에서 쓴다.
