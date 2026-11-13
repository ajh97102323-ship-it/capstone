# Implementation Plan: 잔량 곡선 대리모델 학습과 평가

**Branch**: `002-surrogate-training` | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-surrogate-training/spec.md`

## Summary

001 기본 데이터셋(1만 개)으로 설계 입력 10개 → 0~365일 잔량비 곡선(100개 시점)을 예측하는 MLP 대리모델을 학습한다.
scikit-learn `MLPRegressor`에 물리 특성 k(초기 일일 증발 비율, ODE 없이 배열로 계산)를 더한 11개 입력을 주고,
출력은 `[0,1]` 자르기와 누적 최솟값 후처리로 단조성을 보장한다. 001의 검증 세트로 조기 종료하고, 테스트 세트는 최종
평가에만 쓴다. 모델은 `models/<name>/`에 joblib + meta.json + 평가 보고서로 저장하고, 003·004가 쓸 예측 API
(`load_surrogate`, `predict`, `ratio365`, `check_range`)를 제공한다. 사전 실험에서 R² 0.9995, 365일 평균 오차
0.0046을 얻었고, SC-002 최대 오차(≤ 0.03)는 하이퍼파라미터 탐색과 앙상블로 맞추는 것이 남은 과제다(research R8).

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: scikit-learn(MLPRegressor, StandardScaler, r2_score), joblib, numpy, matplotlib(Agg),
optuna(탐색, **새로 추가**). 신경망 프레임워크는 scikit-learn으로 정했다(헌법 기술 제약, research R1).

**Storage**: 로컬 파일 `models/<name>/` (model.joblib, meta.json, tuning.json, report/). 형식은 [contracts/model-format.md](contracts/model-format.md)

**Testing**: pytest. 학습 테스트는 001 `small_dataset` fixture(300개)나 작은 생성 데이터셋, 작은 은닉층, 적은 epoch로 빠르게 돌린다. 출력은 `tmp_path`

**Target Platform**: 개발자 노트북(Windows 11), CPU

**Project Type**: 단일 Python 프로젝트 안의 라이브러리 + CLI (`python -m surrogate.<명령>`)

**Performance Goals**: 기본 학습 15분 이내(SC-005, 사전 실험 약 15~30초), 1000개 배치 예측이 ODE보다 100배 이상 빠름(SC-003, 사전 실험 약 890배)

**Constraints**: 예측은 항상 0~1·단조 비증가(SC-004), 학습 범위 밖 입력 거부(FR-007), 테스트 세트는 최종 평가에만(FR-004), 경제 변수 미사용

**Scale/Scope**: 학습 7000 / 검증 1500 / 테스트 1500, 입력 11 → 출력 99, 사용자 1명

미결 사항(NEEDS CLARIFICATION)은 없다. 근거는 [research.md](research.md).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 확인 내용 | Phase 0 전 | Phase 1 후 |
|---|---|---|---|
| I. 물리 모델이 기준 | 평가는 데이터셋의 ODE 곡선과 비교한다. 특성 k는 `physics/` 함수·상수로 만들고 ODE를 복제하지 않으며, `BoiloffModel` 기반 값과 같은지 테스트로 고정한다. 모델에 데이터셋 물리 지문을 기록하고 불일치를 경고한다. `physics/`는 고치지 않는다 | ✅ | ✅ |
| II. 테스트 우선 | 모든 FR에 대응하는 pytest를 구현보다 먼저 쓴다(builder/verifier 흐름) | ✅ | ✅ |
| III. 단위·가정 | k는 [1/day], 입력은 물리 단위로 받는다. 후처리 규칙과 범위 검사 규칙을 contracts에 명시했다 | ✅ | ✅ |
| IV. 경제 변수 분리 | 입력 특성·모델 파일에 비용 관련 값이 없다. 비용 환산 오차는 보고서에서만 기본 p_H2로 계산한다 | ✅ | ✅ |
| V. 학습 범위와 재현성 | 범위 밖 입력은 `OutOfRangeError`. 학습 시드·설정·데이터셋 경로·버전을 meta.json에 기록한다 | ✅ | ✅ |
| VI. 단순성 | 이미 설치된 sklearn 사용, 후처리로 단조성 보장, 새 의존성은 optuna 하나. PyTorch·앙상블은 SC-002를 못 맞출 때만 쓴다 | ✅ | ✅ |
| 기술 제약: 구조 | PLAN.md 7장의 `surrogate/` 패키지. `physics/`·`data/`는 `surrogate/`를 import하지 않는다 | ✅ | ✅ |
| 보호 장치 | `models/`는 파일 도구 쓰기가 막혀 있으므로 학습 스크립트만 쓴다. 테스트는 임시 폴더로 출력한다 | ✅ | ✅ |

**결과**: 위반 없음.

## Project Structure

### Documentation (this feature)

```text
specs/002-surrogate-training/
├── spec.md
├── plan.md              # 이 파일
├── research.md          # Phase 0: R0 사전 실험, R1~R10 결정
├── data-model.md        # Phase 1: 특성, 설정, 모델, 보고서, 탐색 기록
├── quickstart.md        # Phase 1: 검증 가이드
├── contracts/
│   └── model-format.md  # 003·004가 의존하는 모델 파일 형식, 예측 API, CLI
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
surrogate/                   # 새 패키지
├── __init__.py              # load_surrogate, Surrogate, OutOfRangeError 공개
├── features.py              # 설계 입력 → 특성 11개 (로그 변환, w 표, k 계산)
├── model.py                 # Surrogate: fit(epoch 루프·조기 종료), predict(후처리), check_range, save/load
├── train.py                 # CLI: python -m surrogate.train
├── evaluate.py              # 지표·그림·report.md, CLI: python -m surrogate.evaluate
└── tune.py                  # Optuna 탐색, CLI: python -m surrogate.tune (US2)

tests/
├── test_surrogate_features.py   # k가 BoiloffModel 값과 상대 1e-3 이내, w 표, 로그 변환, 순서 검사
├── test_surrogate_model.py      # 후처리 보장, 범위 검사, 조기 종료가 검증 세트 사용, 저장·불러오기 왕복, 재현성
├── test_surrogate_train.py      # CLI 종료 코드, 원자적 저장, 테스트 세트 미사용, 물리 지문 경고
├── test_surrogate_evaluate.py   # 지표 계산이 직접 계산과 같음, 보고서 파일, SC 판정
└── test_surrogate_tune.py       # 작은 탐색에서 기록·최적 설정·테스트 세트 미사용

models/                      # 학습 결과 (스크립트만 씀)
requirements.txt             # + optuna
```

**Structure Decision**: PLAN.md 7장의 `surrogate/` 패키지를 새로 만든다. 001의 `data.io.load_dataset`으로 데이터를 읽고, 원자적 저장은 001과 같은 방식(`<name>.partial` → 이름 변경, 대소문자 무시 이름 검사)을 따른다. 모델 결과물은 `models/`에 둔다.

## 구현 순서 (tasks 작성 지침)

1. **기반**: optuna 추가, `surrogate/features.py`(k와 w 표) + 테스트
2. **User Story 1 (P1, MVP)**: model.py(학습 루프·후처리·범위 검사·저장) → train.py → evaluate.py(지표와 SC 판정, 기본 보고서)
3. **User Story 3 (P2)**: 오차 분석 그림(오차 상위 곡선, 입력별 오차, 비용 환산 오차) — US1의 evaluate를 확장
4. **User Story 2 (P2)**: tune.py
5. **User Story 4 (P3)**: 학습 곡선 비교와 비교 모델 — 001 Phase 5(부분 데이터셋)가 보류 중이므로 함께 보류
6. **마무리**: 기본 모델 학습, SC-002 미달이면 research R8 순서로 대응

## Complexity Tracking

위반 없음.
