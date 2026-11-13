# Contract: 최적화 Python API와 CLI

004(웹 UI)는 이 계약에 의존한다. 필드 의미는 [data-model.md](../data-model.md).

## Python API (`optimize`)

| 함수 | 반환 | 비고 |
|---|---|---|
| `Problem(design, cost=CostParams(), n_range=(10, 120), residual=None)` | 문제 | dataclass. 경제 변수 검사 |
| `check_variables(names)` | 없음 / `ValueError` | 허용: `N`, `LD`. N̄·ε는 "비용이 정의되지 않음" 메시지로 거부 |
| `optimize_layers(sur, problem) -> LayerResult` | 대리모델만 사용, ODE 없음 | 1초 이내(FR-015, SC-003) |
| `verify_with_ode(problem, result, top_k=5) -> Verification` | 상위 후보 + 전 범위 ODE | |
| `ode_scan(problem) -> dict` | ODE 전 범위 비용 | `physics.cost_vs_layers`와 같은 키 |
| `analytic_n(problem) -> float` | 근사식 N* | `physics.analytic_optimal_layers` |
| `radius_for_volume(V, LD)` | 반경 [m] | 배열 가능 |
| `optimize_volume(sur, design, cost, V, D_max=None, ld_step=0.05, verify=True) -> VolumeResult` | N·L/D | design의 R·LD·N은 무시 |
| `sensitivity(sur, problem, param, values, ode_every=3) -> SensitivityResult` | 민감도 | |
| `pareto(sur, problem) -> ParetoResult` | Pareto | |
| `DEFAULT_MODEL` | str | 002 최종 모델 경로 |
| `DEPLETION_TOL` | float | 0.03 |

- `sur`는 002 계약의 대리모델 객체(`predict`, `check_range`, `t`, `train_range`).
- 결과 객체는 dataclass이고 `to_dict()`로 JSON 직렬화 가능한 dict를 돌려준다.

## 명령줄

| 명령 | 설명 | 종료 코드 |
|---|---|---|
| `python -m optimize.run [--model DIR] [--out reports] [--name NAME] [--p-h2 5] [--c-layer 10] [--c-fixed 50] [--life 20] [--discount 0.05] [--volume V] [--dmax D] [--residual-day T --residual-min X] [--overwrite]` | 기본 설계(`DesignParams()`)로 N 최적화+ODE 재검증, 민감도(p_H2, c_layer), Pareto, `--volume`이 있으면 N·L/D 최적화. `reports/<name>/`에 report.md, results.json, 그림. 마지막 줄에 출력 경로 | 0 성공 / 1 설정 오류 / 2 이미 있음 / 3 실패 |
| `python -m optimize.validate [--model DIR] [--n 20] [--seed 2026] [--out reports] [--overwrite]` | 검증 설계 n개로 SC-001/002/003 측정, `reports/opt_validate_<모델 이름>/` | 0 / 1 / 2 / 3 |

기본 이름: run은 `opt_<모델 이름>`. 출력은 `<name>.partial`에 쓰고 완성 후 이름을 바꾼다.

### report.md 그림

- `cost_breakdown.png`: MLI·보일오프·총비용(ODE 실선, 대리모델 점선), 최적점, 평평한 구간 음영
- `sensitivity.png`: p_H2–N*, c_layer–N* (대리모델, ODE, 근사식)
- `pareto.png`: 투자비–연간 손실 질량, 총비용 최적점
- `ld_tradeoff.png`: (`--volume` 시) L/D–N 총비용 등고선, 최적점, 직경 제약 경계
