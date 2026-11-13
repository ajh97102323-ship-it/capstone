# Implementation Plan: MLI 적층 비용 ↔ 보일오프 손실 설계 최적화

**Branch**: `003-cost-optimization` | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-cost-optimization/spec.md`

## Summary

002 대리모델(`surrogate.load_surrogate`)로 적층수 N = 10~120 정수 전체를 한 번의 배치 예측으로 평가해 연간 총비용
최소 N을 찾고(1차원 전수 탐색), 상위 후보 5개를 `physics.evaluate_cost`(ODE)로 재계산해 최종 결과로 보고한다.
비용은 `physics.cost`의 `mli_capex`·`CostParams.crf`와 잔량비로 후처리 계산한다(경제 변수는 모델 입력 아님).
체적 고정 문제는 L/D 격자(0~3, 61점) × N 격자에서 반경을 체적으로부터 계산하고 학습 범위·직경 제약을 건다.
민감도(p_H2, c_layer, Y, r), Pareto(투자비–연간 손실 질량), 잔량 목표 제약을 제공하고, 결과는 `reports/opt_*`에
report.md와 그림으로 남긴다. 004 UI는 ODE 재검증과 분리된 `optimize_layers()`를 직접 호출한다(FR-015).

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: numpy, matplotlib(Agg), 기존 `physics/`, `surrogate/`. 새 의존성 없음. N은 정수 1차원,
N·L/D는 61×111 격자라 전수 탐색이 1초 안에 끝나므로 Optuna는 쓰지 않는다(research R2).

**Storage**: 결과는 `reports/opt_<이름>/` (report.md, results.json, 그림). `reports/`는 스크립트만 쓴다

**Testing**: pytest. 대리모델이 필요한 테스트는 ODE를 그대로 감싼 **가짜 대리모델**(`ODESurrogate`, 같은 API)로 돌려
최적화 로직을 학습 결과와 분리해 검증한다. 실제 모델 정확도(SC-001/002)는 `python -m optimize.validate`로 측정한다

**Target Platform**: 개발자 노트북(Windows 11), CPU

**Project Type**: 단일 Python 프로젝트 안의 라이브러리 + CLI (`python -m optimize.<명령>`)

**Performance Goals**: 대리모델 기반 N 최적화 1초 이내(SC-003, 예상 수 ms), ODE 전 범위 스캔 설계당 약 0.3초(측정 2.8 ms/회)

**Constraints**: 소진 설계 제외(헌법 IV), 학습 범위 밖 입력 거부(헌법 V), N̄·ε 최적화 금지(헌법 IV), 최종 보고는 ODE 재검증 값(헌법 I)

**Scale/Scope**: 설계 1개당 후보 111개(N) 또는 6771개(N×L/D), 검증 설계 20개

미결 사항(NEEDS CLARIFICATION)은 없다. 근거는 [research.md](research.md).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 확인 내용 | Phase 0 전 | Phase 1 후 |
|---|---|---|---|
| I. 물리 모델이 기준 | 대리모델 최적화 후 상위 후보 5개와 ODE 전 범위 스캔으로 재검증한다. 보고서의 최종 값은 ODE 값이다 | ✅ | ✅ |
| II. 테스트 우선 | 각 FR에 대응하는 pytest를 먼저 쓴다. U자형·민감도 방향·L/D 구형 수렴 같은 경향을 테스트한다 | ✅ | ✅ |
| III. 단위·가정 | 모든 결과 필드에 단위([$/yr], [kg/yr], [$])를 data-model에 적는다. MLI 면적=내벽 면적 가정은 physics를 그대로 쓴다 | ✅ | ✅ |
| IV. 경제 변수 분리 | 경제 변수는 `CostParams`로 후처리에만 쓴다. 소진 후보는 제외. 최적화 변수는 N, L/D만 허용하고 N̄·ε는 `ValueError` | ✅ | ✅ |
| V. 학습 범위와 재현성 | 대리모델 입력은 `check_range`로 검사, 체적 고정 시 범위 밖 반경은 실행 불가. 경계 최적해 경고. 검증 설계 20개는 시드 고정 | ✅ | ✅ |
| VI. 단순성 | 격자 전수 탐색, 새 의존성 없음 | ✅ | ✅ |
| 기술 제약: 구조 | PLAN.md 7장의 `optimize/` 패키지. `physics/`·`surrogate/`는 `optimize/`를 import하지 않는다. `physics/`는 고치지 않는다 | ✅ | ✅ |
| 보호 장치 | `reports/`는 CLI만 쓰고 테스트는 `tmp_path`로 출력한다 | ✅ | ✅ |

**결과**: 위반 없음. 헌법 기술 제약은 "대리모델 최적화는 Optuna 기본"이라고 하지만, 1~2차원 정수 격자는 전수 탐색이
더 단순하고 정확해(전역 최적 보장) 기본값을 쓰지 않는다. 이는 "기본으로 한다"의 범위 안의 선택이라 위반으로 보지 않는다.

## Project Structure

### Documentation (this feature)

```text
specs/003-cost-optimization/
├── spec.md
├── plan.md              # 이 파일
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── optimize-api.md  # 004가 의존하는 Python API와 CLI
└── tasks.md             # Phase 2
```

### Source Code (repository root)

```text
optimize/
├── __init__.py          # 공개 API
├── problem.py           # Problem(고정 설계·경제 변수·제약), 변수 검사, 비용 후처리(cost_arrays)
├── layers.py            # optimize_layers(대리모델), ode_scan, verify_with_ode, analytic N*
├── volume.py            # 체적 고정 N·L/D 격자 최적화, 반경 계산, 직경 제약
├── analysis.py          # sensitivity, pareto
├── report.py            # 그림·report.md·results.json
├── run.py               # CLI: python -m optimize.run
└── validate.py          # CLI: python -m optimize.validate (SC-001/002, 설계 20개)

tests/
├── conftest.py              # + ODESurrogate fixture (ODE를 대리모델 API로 감쌈)
├── test_optimize_problem.py
├── test_optimize_layers.py
├── test_optimize_volume.py
├── test_optimize_analysis.py
└── test_optimize_cli.py
```

**Structure Decision**: PLAN.md 7장의 `optimize/` 패키지를 새로 만든다. 대리모델은 002 계약(`predict`, `check_range`,
`t`, `train_range`)만 쓰므로 단일 모델·앙상블 어느 쪽이든 같은 API면 동작한다.

## 구현 순서 (tasks 작성 지침)

1. **기반**: problem.py(변수 검사, 비용 후처리) + ODESurrogate fixture
2. **US1 (P1, MVP)**: layers.py(대리모델 전수 탐색, 소진 제외, 평평한 구간, 경계 경고, ODE 스캔·상위 후보 재검증, N*) → report.py 비용 분해 그래프 → run.py
3. **US2 (P2)**: analysis.sensitivity + 그래프
4. **US3 (P2)**: volume.py + 등고선 그래프
5. **US4 (P3)**: 잔량 목표 제약(layers에 옵션), analysis.pareto
6. **마무리**: validate.py로 SC-001/002, SC-003 시간 측정, 기본 보고서 생성

## Complexity Tracking

위반 없음.
