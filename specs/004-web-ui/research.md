# Research: 웹 UI (004)

## R1. UI 기술

- **Decision**: Streamlit 1.58(설치됨). 그래프는 Streamlit 의존성인 Altair 사용.
- **Rationale**: 헌법 기술 제약의 기본값, 슬라이더+그래프 위주 화면에 적합. Plotly는 미설치라 새 의존성이 생긴다.
- **Alternatives**: Dash/FastAPI+JS(구현량 큼), Plotly(새 의존성).

## R2. 모델 공유와 세션 분리

- 대리모델: `@st.cache_resource def get_surrogate(path)` → 서버 프로세스당 한 번 로드, 모든 세션 공유(FR-004). 대리모델 예측은
  읽기 전용이라 스레드 간 공유가 안전하다(sklearn predict는 상태를 바꾸지 않음).
- 세션 상태: `st.session_state["saved"]`(저장 설계안 list), 입력 위젯 key. Streamlit 세션은 브라우저 탭마다 독립이므로
  사용자 간 노출이 없다(FR-005, SC-006). 전역 변수에 사용자 데이터를 두지 않는다(테스트로 금지 확인).
- 모델 경로: 환경변수 `LH2_MODEL` 또는 `optimize.DEFAULT_MODEL`. 불러오기 실패 시 `st.error(원인)` + `st.stop()`(ODE 대체 금지).

## R3. 입력 위젯

- 선형 입력(N, N̄, ε, R, L/D, fill): `st.slider(min=lo, max=hi)`. N은 정수 step 1.
- 로그 입력(G_sup, Pv0, G_out, S): `st.select_slider`에 로그 등간격 61개 값(lo~hi)을 주고 지수 표기로 표시 → 로그 눈금 조정(FR-002).
- 범위는 `sur.train_range`에서 읽으므로 범위 밖 값은 선택할 수 없다.
- 기본값: `physics.DesignParams()`(학습 범위 안). 로그 입력은 기본값에 가장 가까운 격자 값.

## R4. 예측 요약 (FR-006)

- 곡선: `sur.predict_one(**design)`, 시간 `sur.t` [day].
- 초기 열유입 Q0 [W]: `BoiloffModel(p).heat_to_liquid(0, m0)` (ODE 적분 없음, 물리 함수 직접 호출).
- 지정 기간 후 잔량비: `np.interp(t_query, t, curve)`, t_query 1~365 [day].
- 일일 보일오프율 [%/day]: 초기값 `Q0 / H_FG / m0 · 86400 · 100`.
- 소진 시점 [day]: 곡선이 `optimize.DEPLETION_TOL` 미만으로 처음 내려가는 시점을 선형 보간. 없으면 "1년 내 소진 없음".
  소진이면 "비용 과소평가" 경고(FR-007).
- 비용: `optimize.problem.cost_arrays`로 연간 MLI·보일오프·총비용 [$/yr].

## R5. 검증 탭 (FR-009)

- `physics.simulate(p)`(같은 100점 격자) vs 대리모델 곡선. 최대 절대 오차, 365일 잔량비 오차, 보일오프 비용 차이
  `p_h2 · m0 · |δ365|` [$/yr], 각 계산 시간 [ms](`time.perf_counter`).

## R6. 최적화 탭 (FR-010~013)

- 경제 변수 5개: `st.number_input`(c_layer > 0, c_fixed ≥ 0, p_h2 > 0, life ≥ 1, discount 0~0.2). 수소 가격은 2~15 슬라이더도 제공.
- 입력이 바뀔 때마다 `optimize_layers`(수 ms) → 비용 분해 차트, 최적 N, 평평한 구간, 경고, 최적 설계 곡선.
- 잔량 목표 제약(선택): 체크박스 + 기간·최소 잔량비. 체적 고정(선택): 체크박스 + 체적 [m³]·최대 직경 [m] → `optimize_volume`(verify=False) 결과 표.
- "ODE로 검증" 버튼 → `verify_with_ode` 결과(추천 N, ODE 최적 N, 총비용 상대오차)를 세션에 저장해 표시. 입력이 바뀌면 지운다.

## R7. 동시 사용자 (SC-003)

- Streamlit은 세션마다 스크립트를 스레드로 실행한다. ODE 검증 0.3 s는 GIL을 오래 잡지만 짧아 다른 사용자 예측(수 ms)을
  눈에 띄게 늦추지 않는다. 측정: 스레드 5개가 예측 요약+최적화를 20번씩 반복하고 그중 하나는 ODE 검증을 섞어 최대 지연 < 1 s를
  확인한다(테스트). 실제 브라우저 5개 접속은 마무리에서 수동/스크립트로 확인한다.
