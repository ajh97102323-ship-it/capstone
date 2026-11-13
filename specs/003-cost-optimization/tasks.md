# Tasks: MLI 적층 비용 ↔ 보일오프 손실 설계 최적화 (003)

**Input**: plan.md, research.md, data-model.md, contracts/optimize-api.md, quickstart.md
**Tests**: 포함(헌법 원칙 II). 각 Phase에서 테스트를 먼저 쓰고 실패를 확인한 뒤 구현한다.
**공통 규약**: `physics/`·`data/`·`surrogate/`는 고치지 않는다. 테스트 출력은 `tmp_path`(`reports/`·`models/`는 파일 도구 쓰기 금지).
최적화 로직 테스트는 ODE를 002 대리모델 API로 감싼 `ODESurrogate` fixture로 돌린다(research R11). API·CLI는 `contracts/optimize-api.md`를 글자 그대로 따른다.

## Phase 1: Foundational

- [X] T001 [P] `tests/conftest.py`에 `ODESurrogate`(predict/check_range/t/train_range, 002 계약과 같음)와 fixture `ode_sur`를 추가하고, `tests/test_optimize_problem.py`: ① `cost_arrays`(N 배열, ratio365 배열)가 N마다 `physics.cost_from_curve`와 상대 1e-12 이내. ② `check_variables(["N","LD"])` 통과, `["Nbar"]`·`["eps"]`·`["foo"]`는 ValueError이고 N̄·ε 메시지에 "비용" 포함. ③ 경제 변수 life_years ≤ 0, p_h2 ≤ 0, c_layer ≤ 0, discount < 0은 ValueError, discount = 0 허용. ④ 설계 입력이 학습 범위 밖이면 `OutOfRangeError`. ⑤ n_range가 학습 범위 밖이면 ValueError
- [X] T002 `optimize/__init__.py`, `optimize/problem.py`: `Problem`, `check_variables`, `cost_arrays`(research R1), `DEPLETION_TOL`, `DEFAULT_MODEL`

## Phase 2: User Story 1 — 적층수 최적화와 ODE 재검증 (P1, MVP)

- [X] T003 [P] `tests/test_optimize_layers.py` (ode_sur 사용): ① 기본 설계에서 `optimize_layers`의 N은 10~120 정수 111개, `n_opt`가 실행 가능 후보의 총비용 argmin, 총비용 U자(최적이 내부, 양 끝보다 작음). ② MLI 비용 N에 대해 증가, 보일오프 비용 감소. ③ `flat`이 총비용 ≤ 최소×1.01인 N의 최소~최대. ④ 소진 설계(작은 R·나쁜 진공·낮은 N)에서 ratio365 < DEPLETION_TOL인 N은 `feasible=False`, `DEPLETED_EXCLUDED` 경고, n_opt가 그 N이 아님. 모든 N 소진이면 n_opt None + `NO_FEASIBLE`. ⑤ 최적이 경계인 경우(p_h2 매우 큼 → 120, 매우 작음 → 10)에 `BOUNDARY_HIGH`/`BOUNDARY_LOW`. ⑥ `verify_with_ode`: 후보 ≥3개, `n_recommended`는 후보 중 ODE 총비용 최소, scan이 `physics.cost_vs_layers(p, cost, range(10,121))`와 같음, `rel_cost_err`·`dN` 정의대로, ode_sur에서는 dN == 0, rel_cost_err == 0. ⑦ `analytic_n`이 `physics.analytic_optimal_layers`와 같고 기본 설계에서 ODE 최적 N과 12% 이내. ⑧ `optimize_layers`는 ODE를 부르지 않는다(physics.model.solve_ivp를 실패하게 바꾸고 일반 대리모델 대역으로 호출해도 동작). ⑨ `to_dict()`가 `json.dumps` 가능
- [X] T004 `optimize/layers.py`: research R2~R5
- [X] T005 [P] `tests/test_optimize_cli.py`: ① `optimize.run.main([...,"--model",<tmp 모델>,"--out",tmp])` 0, 출력 디렉터리에 report.md·results.json·cost_breakdown.png·sensitivity.png·pareto.png, `.partial` 없음, 마지막 줄이 출력 경로. ② 같은 이름 2, `--overwrite` 0. ③ 잘못된 인자(음수 수명 등) 1, `--help` 0. ④ report.md 맨 위 표에 대리모델 최적 N, ODE 최적 N, 근사식 N*, 총비용 [$/yr], 연간 손실 질량 [kg/yr]. ⑤ `--volume`이 있으면 ld_tradeoff.png. 테스트용 모델은 001 `small_dataset`으로 작게 학습한 002 모델을 `tmp_path`에 저장해 쓴다(session fixture)
- [X] T006 `optimize/report.py`, `optimize/run.py`: contracts CLI와 그림. `analysis`·`volume` 미구현 부분은 이후 Phase에서 채운다(이 Phase는 cost_breakdown·표만 필수, 나머지 그림 테스트는 해당 Phase 완료 후 통과)

## Phase 3: User Story 2 — 경제 변수 민감도 (P2)

- [X] T007 [P] `tests/test_optimize_analysis.py`(민감도, ode_sur): ① p_h2 2~15에서 n_sur 비감소이고 처음<끝, c_layer 5~30에서 비증가이고 처음>끝, `monotone_ok` True. ② n_analytic이 각 점의 `physics.analytic_optimal_layers`와 같고 같은 방향. ③ `ode_every=3`이면 0,3,6..번째 점만 n_ode가 숫자, 나머지 NaN. ④ 잘못된 param 이름은 ValueError, `Nbar`는 check_variables와 같은 이유로 거부
- [X] T008 `optimize/analysis.py` `sensitivity` + `sensitivity.png`

## Phase 4: User Story 3 — 체적 고정 N·L/D (P2)

- [X] T009 [P] `tests/test_optimize_volume.py`(ode_sur): ① `radius_for_volume(V, LD)`로 만든 `CapsuleTank(R, 2R·LD).V_tot`가 V와 상대 1e-9. ② 직경 제약 없음(V=30)에서 ld_opt ≤ 0.2. ③ V=30, D_max=3.0에서 최적이 2R ≤ 3.0, ld_opt가 제약을 만족하는 최소 L/D + 0.3 이내. ④ 반경이 0.3~2.5 밖인 L/D는 `ld_feasible=False`, total NaN. 모든 L/D 불가면 `NO_FEASIBLE`. ⑤ 최적 칸의 total이 그 (R, L/D, N) 설계로 `cost_arrays`를 직접 계산한 값과 같다. ⑥ ODE 재검증 결과가 있다
- [X] T010 `optimize/volume.py` + `ld_tradeoff.png`

## Phase 5: User Story 4 — 잔량 목표 제약과 Pareto (P3)

- [X] T011 [P] `tests/test_optimize_analysis.py`에 추가: ① residual=(180, r)로 무제약 최적 N의 180일 잔량비보다 높은 r을 주면 n_opt가 무제약보다 크고 `RESIDUAL_ACTIVE`, 선택된 N의 180일 잔량비 ≥ r. ② 만족 불가 r(0.9999)이면 n_opt None, `RESIDUAL_INFEASIBLE`, 가장 가까운 N이 경고/필드에 있음. ③ pareto: 비지배 판정이 직접 계산과 같고 n_cost_opt가 n_opt와 같으며 Pareto 위에 있다
- [X] T012 `layers.py` residual 옵션, `analysis.pareto` + `pareto.png`

## Phase 6: 마무리

- [X] T013 [P] `tests/test_optimize_cli.py`에 validate 테스트: 작은 모델·`--n 3`으로 0, `results.json`에 설계별 n_sur, n_ode, rel_cost_err, elapsed_s, SC 판정
- [X] T014 `optimize/validate.py`(research R8). 전체 테스트 통과 후 실제 002 최종 모델로 `python -m optimize.run`, `--volume 30 --dmax 3.0`, `python -m optimize.validate`를 실행하고 SC-001~005를 보고한다

## 의존성

Foundational → US1 → (US2, US3, US4 병렬 가능하나 같은 builder가 순서대로) → 마무리.


**마무리 결과 (2026-11-13)**: T001~T006은 verifier 검증(반려 1회: 출처 기록·NaN·inf → 보완 완료). T007~T014는 사용자 지시로 verifier를 생략하고 메인 세션이 pytest(전체 459 통과)와 실제 실행으로 확인. 실제 모델(500개 데이터 탐색 모델) 결과: 기본 설계 대리모델 N 66 / ODE N 63 / 근사식 65.1, 총비용 오차 0.06%. validate 20개: SC-001 3/20(미달), SC-002 14/20(미달), SC-003 20/20(최대 2 ms). 체적 30 m³·D_max 3 m → L/D 0.75(제약 경계 0.748). 대리모델 정확도(002 SC 미달)가 원인이며, 사용자 지시로 UI 완성을 우선함.
