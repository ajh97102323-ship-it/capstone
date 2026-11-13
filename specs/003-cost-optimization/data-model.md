# Data Model: 비용 최적화 (003)

## Problem (최적화 문제)

| 필드 | 형식 | 설명 |
|---|---|---|
| `design` | dict[str, float] | 설계 입력 10개(`DesignParams` 필드 이름). `N`은 무시(설계변수) |
| `cost` | `physics.CostParams` | c_layer [$/(m²·layer)], c_fixed [$/m²], p_h2 [$/kg], life_years [yr], discount [-] |
| `n_range` | (int, int) | 기본 (10, 120). 학습 범위 밖이면 `ValueError` |
| `residual` | (t_day, min_ratio) 또는 None | 잔량 목표 제약 [day], [-] |

검증: N 외 입력은 `sur.check_range`(범위 밖 `OutOfRangeError`). 경제 변수 `life_years > 0`, `p_h2 > 0`, `c_layer > 0`,
`c_fixed ≥ 0`, `discount ≥ 0`. `check_variables(names)`는 `{"N", "LD"}` 밖의 이름(N̄·ε 포함)을 `ValueError`로 거부한다.

## LayerResult (대리모델 N 최적화)

| 필드 | 형식 [단위] | 설명 |
|---|---|---|
| `N` | (k,) int | 후보 적층수 |
| `ratio365` | (k,) [-] | 대리모델 365일 잔량비 |
| `curves` | (k, 100) [-] | 잔량비 곡선, `t` (100,) [day] |
| `annual_mli`, `annual_boiloff`, `annual_total` | (k,) [$/yr] | 비용 분해 |
| `capex` | (k,) [$] | MLI 초기 투자비 |
| `m_lost` | (k,) [kg/yr] | 연간 보일오프 질량 |
| `depleted`, `residual_ok`, `feasible` | (k,) bool | 소진, 잔량 제약 만족, 실행 가능 |
| `n_opt`, `total_opt` | int, [$/yr] 또는 None | 대리모델 최적 |
| `flat` | (int, int) 또는 None | 총비용 ≤ 최소×1.01인 N 범위 |
| `n_unconstrained` | int 또는 None | 잔량 제약이 없을 때의 최적 N |
| `warnings` | list[str] | research R5 코드 |
| `elapsed_s` | float [s] | 계산 시간 |

## Verification (ODE 재검증)

| 필드 | 설명 |
|---|---|
| `candidates` | 상위 후보 N 목록(대리모델 총비용 순, 최소 3개, 기본 5) |
| `candidate_totals_ode` | 후보별 ODE 총비용 [$/yr] |
| `n_recommended` | 후보 중 ODE 총비용 최소인 N(최종 보고) |
| `scan` | ODE 전 범위: `N`, `annual_mli`, `annual_boiloff`, `annual_total`, `m_lost`, `depleted` |
| `n_ode`, `total_ode` | ODE 실제 최적 N과 총비용 |
| `total_ode_at_sur` | 대리모델 최적 N의 ODE 총비용 |
| `rel_cost_err` | `(total_ode_at_sur − total_ode)/total_ode` |
| `dN` | `n_opt − n_ode` |
| `n_analytic` | 근사식 N* |

## VolumeResult (체적 고정 N·L/D)

| 필드 | 설명 |
|---|---|
| `V`, `D_max` | 목표 체적 [m³], 최대 직경 [m] 또는 None |
| `LD`, `N` | 격자 축 |
| `R` | (n_LD,) 반경 [m] |
| `total` | (n_LD, n_N) [$/yr], 실행 불가는 NaN |
| `ld_feasible` | (n_LD,) bool (반경 범위·직경 제약) |
| `ld_opt`, `n_opt`, `total_opt`, `R_opt` | 최적점 |
| `ode` | 상위 후보 ODE 재검증(후보별 총비용, 추천 (N, L/D)) |
| `warnings` | 경고 코드 |

## SensitivityResult

| 필드 | 설명 |
|---|---|
| `param` | `p_h2`·`c_layer`·`life_years`·`discount` |
| `values` | 변수 값 |
| `n_sur`, `total_sur` | 각 값의 대리모델 최적 N, 총비용 |
| `n_analytic` | 근사식 N* |
| `n_ode` | ODE 최적 N(계산하지 않은 점은 NaN) |
| `monotone_ok`, `matches_analytic` | SC-004 판정 |

## ParetoResult

`capex` [$], `m_lost` [kg/yr], `N`, `pareto_mask`, `n_cost_opt`.
