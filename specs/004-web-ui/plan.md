# Implementation Plan: 단열 설계 예측·최적화 웹 UI

**Branch**: `004-web-ui` | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-web-ui/spec.md`

## Summary

Streamlit(설치됨, 1.58) 앱 `app/main.py`에 4개 탭(예측·비교·검증·최적화)을 만든다. 계산은 UI와 분리한 순수 함수
모듈 `app/logic.py`에 두어 pytest로 검증하고, 화면은 `streamlit.testing.v1.AppTest`로 헤드리스 테스트한다.
대리모델은 `st.cache_resource`로 서버당 한 번 불러와 공유하고(FR-004), 입력값·저장 설계안은 `st.session_state`에
둔다(FR-005). 최적화는 003 `optimize.optimize_layers`(대리모델만, 수 ms)를 입력이 바뀔 때마다 부르고, ODE 재검증은
버튼으로만 실행한다. 그래프는 Streamlit에 포함된 Altair로 그린다(새 의존성 없음).

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: streamlit 1.58(altair 포함), 기존 `physics/`, `surrogate/`, `optimize/`. 새 의존성 없음(requirements.txt에 streamlit 명시만 추가)

**Storage**: 없음. 저장 설계안은 세션 메모리에만(새로고침 시 사라짐을 화면에 안내)

**Testing**: pytest. `app/logic.py` 단위 테스트(가짜 대리모델 `ODESurrogate` 재사용), `AppTest`로 탭·위젯·세션 분리 테스트,
스레드 5개 동시 호출 지연 측정

**Target Platform**: 개발자 노트북/사내 서버 1대, 브라우저 접속(`streamlit run app/main.py --server.address 0.0.0.0`)

**Project Type**: 웹 앱(Streamlit 단일 스크립트 + 로직 모듈)

**Performance Goals**: 입력 변경 후 갱신 1초 이내(SC-001·002), 5명 동시(SC-003). 예측 1개 < 5 ms, N 최적화 < 50 ms, ODE 검증 < 0.5 s

**Constraints**: 입력은 학습 범위로 제한(헌법 V), 로그 스케일 입력 4개는 로그 눈금, 모든 수치 단위 표시(헌법 III), 경제 변수는 후처리(헌법 IV),
모델 불러오기 실패 시 명확히 실패(ODE 대체 금지)

**Scale/Scope**: 동시 사용자 5~10명, 화면 한국어

미결 사항(NEEDS CLARIFICATION)은 없다. 근거는 [research.md](research.md).

## Constitution Check

| 원칙 | 확인 내용 | Phase 0 전 | Phase 1 후 |
|---|---|---|---|
| I. 물리 모델이 기준 | 검증 탭에서 ODE와 직접 비교, 최적화 탭은 "ODE로 검증" 버튼으로 003 `verify_with_ode` 호출. 대리모델 실패 시 ODE로 조용히 대체하지 않음 | ✅ | ✅ |
| II. 테스트 우선 | logic 단위 테스트, AppTest 화면 테스트를 먼저 쓴다 | ✅ | ✅ |
| III. 단위 | 모든 위젯 라벨·지표에 단위 | ✅ | ✅ |
| IV. 경제 변수 분리 | 경제 변수는 `CostParams`로만 전달, 대리모델 입력 아님. 소진 설계는 경고, 최적화에서 제외(003) | ✅ | ✅ |
| V. 학습 범위 | 슬라이더 범위 = `sur.train_range`. 경계 최적 경고 | ✅ | ✅ |
| VI. 단순성 | Streamlit 기본 위젯·Altair, 새 의존성 없음 | ✅ | ✅ |
| 기술 제약 | 모델 1회 로드(cache_resource), 세션 상태 분리, `app/`만 추가 | ✅ | ✅ |

**결과**: 위반 없음.

## Project Structure

```text
specs/004-web-ui/
├── plan.md, research.md, data-model.md, quickstart.md
├── contracts/ui.md      # 탭별 위젯·표시 항목, 실행 명령
└── tasks.md

app/
├── __init__.py
├── logic.py             # 순수 계산: 입력 위젯 정의, 예측 요약, 검증, 비교 표, 최적화 호출
└── main.py              # Streamlit 화면 (streamlit run app/main.py)

tests/
├── test_app_logic.py
└── test_app_ui.py       # AppTest: 4개 탭, 위젯 범위, 세션 분리, 모델 오류
```

**Structure Decision**: PLAN.md 7장의 `app/`. 화면 코드는 얇게, 계산은 `logic.py`로 모은다.

## 구현 순서

1. logic.py(입력 정의·예측 요약) + 테스트 → main.py 예측 탭 (US1, MVP)
2. 최적화 탭 (US2)
3. 검증 탭 (US3)
4. 비교 탭과 세션 분리 (US4)
5. 마무리: 동시 5명 측정, 실행 문서, 브라우저 확인

## Complexity Tracking

위반 없음.
