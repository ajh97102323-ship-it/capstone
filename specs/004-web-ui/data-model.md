# Data Model: 웹 UI (004)

## InputSpec (입력 위젯 정의, `logic.input_specs(sur)`)

| 필드 | 설명 |
|---|---|
| `name` | `DesignParams` 필드 이름 |
| `label` | 한국어 라벨 + `[단위]` |
| `lo`, `hi` | 학습 범위 |
| `log` | 로그 눈금 여부(G_sup, Pv0, G_out, S) |
| `options` | 로그 입력의 격자 값(61개), 선형은 None |
| `step` | N은 1, 나머지는 범위/100 |
| `default` | `DesignParams()` 값(로그는 가장 가까운 격자 값) |

## PredictionSummary (`logic.summarize(sur, design, cost, t_query)`)

| 필드 | 단위 |
|---|---|
| `t`, `curve` | [day], [-] (100,) |
| `Q0` | [W] |
| `ratio_at_query` | [-] |
| `boiloff_rate` | [%/day] |
| `t_empty` | [day] 또는 None |
| `depleted` | bool |
| `annual_mli`, `annual_boiloff`, `annual_total` | [$/yr] |
| `m0` | [kg] |

## ValidationResult (`logic.validate(sur, design, cost)`)

`t`, `curve_ai`, `curve_ode`, `max_abs_err` [-], `err365` [-], `cost_diff` [$/yr], `ms_ai`, `ms_ode` [ms].

## SavedDesign (세션 상태 `saved` 목록의 원소)

`name`(빈 이름·중복 거부), `design`(10개), `summary`(PredictionSummary). `logic.compare_table(saved)` → 이름별 주요 수치 행.

## Session State 키

`saved`(list[SavedDesign]), `verify`(최근 ODE 검증 결과와 그 입력 키), 위젯 key `in_<name>`, `t_query`, `econ_*`.
