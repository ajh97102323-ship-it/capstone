# Tasks: 단열 설계 예측·최적화 웹 UI (004)

**Input**: plan.md, research.md, data-model.md, contracts/ui.md, quickstart.md
**Tests**: 포함(헌법 원칙 II). 테스트를 먼저 쓰고 실패를 확인한 뒤 구현한다.
**공통 규약**: `physics/`·`data/`·`surrogate/`·`optimize/`는 고치지 않는다(필요하면 보고). 로직 테스트는 `tests/conftest.py`의
`ODESurrogate`(`ode_sur`)를 쓴다. UI 테스트는 `streamlit.testing.v1.AppTest`로, 모델은 환경변수 `LH2_MODEL`로 작은 테스트 모델(tmp_path)을 지정한다.

## Phase 1: User Story 1 — 예측 탭 (P1, MVP)

- [X] T001 [P] `tests/test_app_logic.py`: ① `input_specs(sur)` 10개, 순서·범위가 `sur.train_range`와 같고 G_sup·Pv0·G_out·S만 log, 로그 options 61개가 lo~hi 로그 등간격, 모든 default가 범위 안, 라벨에 `[` 단위 포함(무차원은 `[-]`). ② `summarize`: curve == `sur.predict_one`, Q0 == `BoiloffModel(p).heat_to_liquid(0, m0)`, ratio_at_query == interp, boiloff_rate == Q0/H_FG/m0·86400·100, 비용이 `optimize.problem.cost_arrays`와 같음. ③ N 증가 시 annual_boiloff ↓, annual_mli ↑. ④ 소진 설계에서 depleted True, t_empty가 0~365, 비소진이면 None. ⑤ 범위 밖 설계는 `OutOfRangeError`
- [X] T002 `app/__init__.py`, `app/logic.py`(input_specs, summarize, load_model) — load_model은 경로 없음/`.partial`/형식 오류 시 원인을 담은 예외
- [X] T003 [P] `tests/test_app_ui.py`: ① AppTest로 `app/main.py` 실행 시 예외 없음, 탭 4개 이름·순서(`예측`,`비교`,`검증`,`최적화`). ② 사이드바 슬라이더 범위가 학습 범위, 로그 입력은 select_slider. ③ 예측 탭 지표 7개 라벨에 단위. ④ N 슬라이더 값을 바꾸고 재실행하면 보일오프 비용 지표 값이 감소, 한 번 재실행이 1초 이내. ⑤ 소진 설계로 바꾸면 warning에 "과소평가". ⑥ `LH2_MODEL`이 없는 경로면 error 요소에 경로가 나오고 탭이 그려지지 않음. ⑦ t_query 변경 시 해당 지표 갱신
- [X] T004 `app/main.py` 사이드바·예측 탭(contracts/ui.md), `requirements.txt`에 `streamlit>=1.40`

## Phase 2: User Story 2 — 최적화 탭 (P1)

- [X] T005 [P] 테스트 추가: logic `optimize_view(sur, design, cost, residual=None, volume=None)`가 `optimize.optimize_layers` 결과와 같은 n_opt·flat·warnings를 돌려주고, p_h2 5→10에서 n_opt 비감소. AppTest: 최적화 탭에 최적 N 지표, p_h2 변경 후 재실행 시 최적 N 증가 방향, 재실행 1초 이내, "ODE 검증" 버튼 클릭 후 상대오차 [%] 표시, 경계 경고(p_h2 극단), 경제 변수 위젯이 0·음수 수명을 허용하지 않음(min 설정)
- [X] T006 `logic.optimize_view` + main.py 최적화 탭(잔량 제약·체적 고정 선택 포함)

## Phase 3: User Story 3 — 검증 탭 (P2)

- [X] T007 [P] 테스트 추가: `logic.validate`의 curve_ode == `physics.simulate(p)[1]`, 오차·비용 차이 정의대로, ms 값 > 0. AppTest: 검증 버튼 후 지표 4개(최대 오차, 365일 오차, 비용 차이, 계산 시간)
- [X] T008 `logic.validate` + 검증 탭

## Phase 4: User Story 4 — 비교 탭과 세션 분리 (P3)

- [X] T009 [P] 테스트 추가: `logic.add_saved`(빈 이름·중복 거부), `remove_saved`, `compare_table`. AppTest: 설계안 2개 저장 → 비교 탭 표 2행, 삭제 → 1행. **세션 분리**: AppTest 인스턴스 A·B를 같은 프로세스에서 실행해 A에서 저장한 설계안이 B의 비교 탭에 없음(SC-006). `app/` 모듈에 사용자 데이터를 담는 전역 가변 객체가 없음(소스 검사)
- [X] T010 logic 저장 함수 + 비교 탭 + 새로고침 시 사라짐 안내

## Phase 5: 마무리

- [X] T011 [P] `tests/test_app_logic.py`에 동시성 테스트: 스레드 5개가 summarize+optimize_view를 20회씩(한 스레드는 validate 섞음) 실행, 각 호출 최대 지연 < 1 s (SC-003, 실제 학습 모델 사용 가능하면 그것으로, 없으면 skip 아닌 ode_sur)
- [X] T012 전체 테스트 통과 후 실제 모델로 `streamlit run app/main.py`를 띄워 브라우저로 4개 탭 확인, 수소 가격 10 $/kg 최적 N 확인, 결과 보고. CLAUDE.md 명령 절에 실행 방법 추가


**마무리 결과 (2026-11-13)**: 사용자 지시로 verifier 생략, 메인 세션이 pytest(전체 459 통과)와 브라우저로 확인. `streamlit run app/main.py`에서 4개 탭 표시, 예측 지표 7개, 수소 가격 5→10 $/kg에서 최적 N 66→89, 검증 탭 AI 0.5 ms / ODE 3.5 ms. 5개 스레드 동시성 테스트 최대 지연 < 1 s. 실제 브라우저 5명 동시 접속은 수동 확인하지 않음.
