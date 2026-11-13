# Implementation Plan: 대리모델 학습용 데이터셋 생성

**Branch**: `001-dataset-generation` | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-dataset-generation/spec.md`

## Summary

검증된 보일오프 물리 모델(`physics/`)로 설계 입력 10개 조합 1만 개를 Latin Hypercube로 뽑아 시뮬레이션하고,
0~365일 잔량비 곡선(100개 시점)과 보조 출력 5개를 학습/검증/테스트(70/15/15)로 나눠 저장한다. 구현은
`data/` 패키지(샘플링 → 시뮬레이션·필터 → 분할 → 원자적 저장)와 명령줄 진입점 4개(`generate`, `report`,
`subset`, `check_physics`)로 이루어진다. 숫자 배열은 `.npz`, 설정·요약은 JSON으로 저장하고, 물리 모델
소스 해시와 버전 문자열을 함께 기록해 재현성과 물리 모델 변경 감지를 보장한다. 물리 모델에는 정확한
소진 시각을 돌려주는 메서드 하나만 추가하며, 기존 동작은 바꾸지 않는다(research R4).

## Technical Context

**Language/Version**: Python 3.13 (현재 환경 3.13.14)

**Primary Dependencies**: numpy 2.4, scipy 1.17(`solve_ivp` 기존 사용, `qmc.LatinHypercube`, `spearmanr`),
matplotlib(점검 그림, Agg 백엔드, 새로 추가)

**Storage**: 로컬 파일. `data/datasets/<name>/` 아래 `dataset.npz` + `config.json` + `summary.json` +
`rejected.csv` (+ `report/`, `subsets/`). 형식은 [contracts/dataset-format.md](contracts/dataset-format.md)

**Testing**: pytest. 기존 `tests/test_physics.py`, `tests/test_cost.py`에 더해 `tests/test_data_*.py`를 추가한다.
생성 테스트는 작은 n(200~500)과 임시 디렉터리(`tmp_path`)를 쓴다.

**Target Platform**: 개발자 노트북(Windows 11, PowerShell), 단일 프로세스

**Project Type**: 단일 Python 프로젝트 안의 라이브러리 + CLI (`python -m data.<명령>`)

**Performance Goals**: 1만 개 생성 10분 이내(SC-001). 샘플당 실측 약 2.4 ms이므로 예상 1분 이내

**Constraints**: 같은 설정과 시드면 결과가 비트 단위로 같아야 함(SC-004). 재계산 차이 1e-6 이하(SC-003).
`physics/`는 `data/`에 의존하지 않음(헌법 기술 제약)

**Scale/Scope**: 샘플 1만 개 × 115개 값, 데이터셋 약 9 MB. 사용자 1명(개발자)

미결 사항(NEEDS CLARIFICATION)은 없다. 기술 선택의 근거는 [research.md](research.md)에 있다.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 확인 내용 | Phase 0 전 | Phase 1 후 |
|---|---|---|---|
| I. 물리 모델이 기준 | 곡선과 보조 출력을 모두 `physics/`로 계산하고 ODE 코드를 복제하지 않는다. 물리 모델 변경(소진 시각 메서드 추가)은 추가만 하며 기존 테스트로 동작 유지를 확인한다. 재생성 영향: 기존 데이터셋 없음(R4) | ✅ | ✅ |
| II. 물리 경향 테스트 우선 | 모든 FR에 대응하는 pytest를 구현보다 먼저 작성한다. 물리 모델 추가 메서드에도 테스트를 붙인다. 테스트 44개가 통과하는 상태에서 시작한다 | ✅ | ✅ |
| III. 단위·가정·출처 | `InputSpec`에 단위 필드를 두고 config.json에 기록한다. 보조 출력 이름과 단위는 data-model에 명시했다 | ✅ | ✅ |
| IV. 경제 변수 분리 | 데이터셋에 비용 키가 없다(dataset-format 계약). 테스트로 키 목록을 고정한다 | ✅ | ✅ |
| V. 학습 범위와 재현성 | `input_lo/hi`를 데이터셋에 저장해 002·004의 외삽 방지에 쓴다. 마스터 시드에서 용도별 시드를 파생한다. 설정, 시드, 물리 모델 해시를 기록한다 | ✅ | ✅ |
| VI. 단순성 | 순차 실행, `.npz`+JSON, 새 의존성은 matplotlib 하나. 적응적 샘플링·층화 분할·병렬화는 넣지 않는다 | ✅ | ✅ |
| 기술 제약: 구조 | PLAN.md 7장의 `data/` 디렉터리를 쓴다. `physics/`는 `data/`를 import하지 않는다 | ✅ | ✅ |
| 기술 제약: 보안 | 공개 문헌 수준 모델만 쓴다. 외부 전송이 없다 | ✅ | ✅ |

**결과**: 위반 없음. Complexity Tracking 불필요.

## Project Structure

### Documentation (this feature)

```text
specs/001-dataset-generation/
├── spec.md
├── plan.md              # 이 파일
├── research.md          # Phase 0: 기술 결정 R1~R11
├── data-model.md        # Phase 1: 엔티티, 필드, 검증 규칙
├── quickstart.md        # Phase 1: 끝까지 실행해 보는 검증 가이드
├── contracts/
│   ├── dataset-format.md   # 002·003·004가 의존하는 파일 형식과 읽기 API
│   └── cli.md              # 명령줄 옵션, 종료 코드, 출력
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks에서 생성)
```

### Source Code (repository root)

```text
physics/                     # 기존 (변경 최소화)
├── __init__.py              # + PHYSICS_VERSION = "0.1.0"
└── model.py                 # + BoiloffModel.simulate_detailed() → (t, ratio, t_empty)
                             #   simulate()는 이를 호출하도록 바꾸되 반환값은 그대로

data/                        # 새 패키지
├── __init__.py
├── config.py                # InputSpec, GenerationConfig, DEFAULT_INPUTS(PLAN.md 3.1), 범위 파싱
├── sampling.py              # LHS 단위 샘플 → 물리 단위 변환 (linear / log / int)
├── simulate.py              # 샘플 하나 → (Y, aux) 또는 RejectionRecord, 품질 필터(R6)
├── split.py                 # 70/15/15 분할, 부분 데이터셋의 행 순서·분할
├── versioning.py            # physics_fingerprint(): 버전 문자열 + 소스 SHA-256
├── io.py                    # 원자적 저장(.partial → 이름 변경), load_dataset, load_subset, check_physics
├── generate.py              # 파이프라인 + CLI: python -m data.generate
├── report.py                # 점검 보고서 + CLI: python -m data.report
├── subset.py                # CLI: python -m data.subset
├── check_physics.py         # CLI: python -m data.check_physics
└── datasets/                # 생성 결과 (코드 아님)

tests/
├── test_physics.py          # 기존 (+ simulate_detailed 소진 시각 테스트)
├── test_cost.py             # 기존
├── test_data_sampling.py    # 범위, 10구간 커버리지(SC-005), 로그 분포, N 정수·끝값
├── test_data_generate.py    # 필터, 분할 비율(SC-006), 재현성(SC-004), 재계산 일치(SC-003),
│                            # 소진 샘플 규칙, 비용 키 없음, 덮어쓰기 보호, 중단 시 .partial 정리
├── test_data_subset.py      # 중첩, 부분 분할, 크기 초과 오류
├── test_data_versioning.py  # 해시 안정성(CRLF/LF), 파일 변경 감지, check_physics
└── test_data_report.py      # 그림·JSON 생성, 경고 규칙(소진 > 30%, 쏠림, 세트 불균형)

requirements.txt             # 새 파일: numpy, scipy, matplotlib, pytest
```

**Structure Decision**: PLAN.md 7장의 단일 프로젝트 구조를 따라 `data/` 패키지를 새로 만든다. 데이터셋 결과물은
같은 디렉터리의 `data/datasets/`에 둔다(PLAN.md: "data/ — 샘플링, 데이터 생성, 생성된 데이터셋"). 표준
라이브러리 `inspect`와 이름이 겹치지 않도록 점검 모듈 이름은 `report.py`로 정했다. 테스트는 기존 관례대로
`tests/` 바로 아래에 둔다.

## 구현 순서 (tasks 작성 지침)

1. **기반**: `requirements.txt`, `physics` 추가(버전 상수, `simulate_detailed` + 테스트), `data/config.py`, `data/versioning.py`
2. **User Story 1 (P1)**: sampling → simulate(필터) → split → io(원자적 저장, 로드) → generate CLI. 각 단계는 테스트를 먼저 쓴다
3. **User Story 2 (P2)**: report(그림 4개, inspection.json, report.md, 경고 규칙)
4. **User Story 3 (P3)**: `--range` 옵션, subset CLI, check_physics CLI
5. **마무리**: quickstart 1~8단계를 실제로 실행하고, 기본 데이터셋 `lhs_n10000_seed42`를 생성·점검한 뒤 PLAN.md 3.4 체크리스트를 갱신

## Complexity Tracking

위반 없음.
