# Tasks: 잔량 곡선 대리모델 학습과 평가 (002)

**Input**: plan.md, research.md, data-model.md, contracts/model-format.md, quickstart.md
**Tests**: 포함(헌법 원칙 II). 각 Phase에서 테스트를 먼저 쓰고 실패를 확인한 뒤 구현한다.
**공통 규약**: 학습·생성 테스트의 출력은 `tmp_path`(`models/`는 파일 도구 쓰기 금지). `physics/`·`data/`는 고치지 않는다. 경제 변수는 쓰지 않는다. 형식·API·CLI는 `contracts/model-format.md`를 글자 그대로 따른다. 학습 테스트는 001의 `small_dataset` fixture(300개)와 작은 은닉층·적은 epoch로 빠르게 돌린다.

## Phase 1: Setup

- [X] T001 `requirements.txt`에 `scikit-learn>=1.5`, `joblib>=1.4`, `optuna>=3.6`을 추가하고 설치한다. `surrogate/__init__.py`를 만든다(공개 API: `load_surrogate`, `Surrogate`, `OutOfRangeError`)

## Phase 2: Foundational (특성)

- [X] T002 [P] `tests/test_surrogate_features.py`: ① 특성은 11개, 순서는 데이터셋 `input_names` + `log10_k`, 로그 스케일 4개는 log10. ② 무작위 설계 50개(소진 설계 포함)에서 k가 `BoiloffModel(p).heat_to_liquid(0, m0) / (H_FG·m0) × 86400`과 상대 1e-3 이내. ③ w 표 값이 `CapsuleTank(1, 2·LD).wetted_area(level(fill·V_tot))/A_tot`와 1e-3 이내. ④ 입력 순서가 다르면 ValueError. ⑤ 1000개 특성 계산이 50 ms 이내(배열 계산 확인)
- [X] T003 `surrogate/features.py`: research R2대로 구현한다. w는 모듈 로드 시 (fill, L/D) 격자(fill 0.5~0.95, L/D 0~3)에서 `CapsuleTank`로 한 번 계산해 2차원 선형 보간한다. `mli_heat_flux`, `H_FG`, `T_C`, `RHO_L`, `ETA`는 `physics/`에서 가져온다. 외부 온도는 인자 `Th`(기본 300.0)

## Phase 3: User Story 1 + 3 — 학습·평가·오차 분석 (P1, MVP)

- [X] T004 [P] `tests/test_surrogate_model.py`: ① 예측은 (n,100), `Y[:,0]==1`, 0≤Y≤1, 단조 비증가(MLP 출력을 일부러 범위 밖·증가로 만든 경우 포함). ② 범위 밖 입력은 `OutOfRangeError`(name·value·lo·hi), N=57.5 같은 실수는 허용. ③ 조기 종료가 **데이터셋 검증 세트**의 MSE로 판단하고 가장 좋았던 epoch 가중치를 쓴다(history의 최소 epoch == best_epoch, 최종 모델의 검증 MSE == history 최솟값). 테스트 세트는 학습 중 쓰지 않는다. ④ 저장→불러오기 왕복 후 예측이 같다. `.partial` 경로 거부, 모르는 `format_version` 거부. ⑤ 같은 설정·시드로 두 번 학습하면 테스트 지표가 상대 1e-6 이내. ⑥ `ratio365(X) == predict(X)[:,-1]`
- [X] T005 `surrogate/model.py`: `Surrogate`(fit/predict/predict_one/ratio365/check_range/save/load/physics_matches), `OutOfRangeError`, `load_surrogate`. research R3(후처리)·R4(partial_fit epoch 루프, 검증 세트 조기 종료, 최적 가중치 깊은 복사)·R5·R6(원자적 저장 `<name>.partial`→이름 변경, 이름 규칙은 001과 같고 대소문자 무시)
- [X] T006 [P] `tests/test_surrogate_evaluate.py`: ① `test_r2`·`ratio365_mae`·`ratio365_max`가 직접 계산한 값과 같다. ② `sc_pass` 판정이 기준(R²≥0.99, MAE≤0.005·최대≤0.03, 속도≥100, 위반 0)과 맞는다(가짜 지표로 경계 확인). ③ `report/`에 `report.md`, `metrics.json`, 그림 4개가 생기고 `report.md` 맨 위에 SC 통과 여부가 있다. ④ 오차 상위 12개 sample_id가 직접 정렬한 결과와 같다. ⑤ 비용 환산 오차가 `5·m0·|δ|`와 같다
- [X] T007 `surrogate/evaluate.py`: research R9의 지표·그림·report.md·metrics.json(US3 오차 분석 포함), CLI `python -m surrogate.evaluate MODEL_DIR`
- [X] T008 [P] `tests/test_surrogate_train.py`: ① `main([...])` 성공 시 0, 모델 디렉터리에 model.joblib·meta.json·report/, `.partial` 없음, 마지막 줄이 모델 경로. ② 같은 이름이면 2, `--overwrite`면 0. ③ 잘못된 인자 1, `--help` 0. ④ 학습 중 KeyboardInterrupt면 3이고 아무것도 남지 않음. ⑤ meta.json에 데이터셋 물리 지문·학습 설정·시드·버전·train_range가 있고 비용 키가 없다. ⑥ 데이터셋 물리 지문이 현재와 다르면 stderr에 `WARNING [PHYSICS_MISMATCH]`
- [X] T009 `surrogate/train.py`: contracts의 CLI(`--dataset`, `--out`, `--name`, `--seed`, `--hidden`, `--lr`, `--batch`, `--alpha`, `--max-epochs`, `--patience`, `--overwrite`, `--no-report`)와 종료 코드

## Phase 4: User Story 2 — 하이퍼파라미터 탐색 (P2)

- [X] T010 [P] `tests/test_surrogate_tune.py`: 작은 탐색(trials 3, 작은 공간)에서 `tuning.json`에 시도 3개·최적 설정이 기록되고, 최적 설정으로 학습한 모델이 저장되며, 탐색 중 테스트 세트를 쓰지 않는다(테스트 세트를 NaN으로 바꿔도 탐색이 끝남)
- [X] T011 `surrogate/tune.py`: research R7의 Optuna 탐색(TPE, 시드 고정), CLI `python -m surrogate.tune`

## Phase 5: 마무리

- [X] T012 전체 테스트 통과 확인 후 기본 모델(`python -m surrogate.train`)과 탐색 모델(`python -m surrogate.tune --trials 30`)을 학습하고 SC-001~005 결과를 보고한다. SC-002 최대 오차를 못 맞추면 research R8 순서(앙상블 → 데이터 추가 → PyTorch)를 진행하기 전에 사용자에게 결과를 보고한다

**보류**: User Story 4(데이터 수별 학습 곡선, 비교 모델)는 001 Phase 5(부분 데이터셋)가 보류라 함께 보류한다.

## 의존성

Setup → Foundational → US1(+US3) → US2 → 마무리. 같은 Phase의 [P] 테스트는 병렬로 쓸 수 있다.


**T012 결과 (2026-11-13)**: 사용자 지시로 데이터셋을 500개(`lhs_n500_seed42`)로 줄이고 오차 기준보다 UI 완성을 우선함. 최종 모델 `models/mlp_lhs_n500_seed42_seed0_tuned`(Optuna 30회, 은닉 153×4): R² 0.965(SC-001 FAIL), 365일 평균 0.041·최대 0.179(SC-002 FAIL), 속도 320배(SC-003 PASS), 범위·단조 위반 0(SC-004 PASS). 1만 개 기본 모델은 R² 0.9996·최대 0.036. R8 대응(앙상블 등)은 하지 않음.
