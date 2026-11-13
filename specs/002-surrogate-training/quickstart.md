# Quickstart: 대리모델 학습 검증 가이드

구현이 끝난 뒤 이 순서대로 실행해 spec의 수용 시나리오와 성공 기준을 확인한다.
명령 형식과 파일 형식은 [contracts/model-format.md](contracts/model-format.md)를 참고한다.

## 0. 준비

```powershell
pip install -r requirements.txt          # optuna 추가됨
python -m pytest -q                      # 기존 테스트 + surrogate 테스트 모두 통과
Test-Path data/datasets/lhs_n10000_seed42/dataset.npz   # 001 기본 데이터셋 (없으면 python -m data.generate)
```

## 1. 기본 모델 학습과 평가 (User Story 1, SC-001~005)

```powershell
Measure-Command { python -m surrogate.train | Out-Host }
```

**기대 결과**
- 15분 안에 끝난다(SC-005, 사전 실험 약 15~30초).
- `models/mlp_lhs_n10000_seed42_seed0/`에 `model.joblib`, `meta.json`, `report/`가 생기고 `.partial`이 남지 않는다.
- `report/report.md` 맨 위에 SC-001~004 통과 여부가 표시된다(SC-006).
- 사전 실험 기준 예상치: R² ≈ 0.9995(SC-001 통과), 365일 평균 오차 ≈ 0.005, 최대 오차 ≈ 0.04(SC-002 최대는 미달 가능, research R8), 속도 수백 배(SC-003), 위반 0건(SC-004).

## 2. 저장된 모델로 예측 (Acceptance 1-2, 1-5)

```powershell
python -c "from surrogate import load_surrogate; m = load_surrogate('models/mlp_lhs_n10000_seed42_seed0'); y = m.predict_one(N=60, Nbar=20, eps=0.03, G_sup=1e-3, Pv0=1e-3, G_out=1e-8, S=1e-3, R=1.5, LD=1.0, fill=0.9); print(y[0], y[-1], (y[1:] <= y[:-1]).all())"
python -c "from surrogate import load_surrogate; m = load_surrogate('models/mlp_lhs_n10000_seed42_seed0'); m.predict_one(N=200, Nbar=20, eps=0.03, G_sup=1e-3, Pv0=1e-3, G_out=1e-8, S=1e-3, R=1.5, LD=1.0, fill=0.9)"
```

**기대 결과**: 첫 명령은 `1.0 <365일 값> True`. 두 번째는 `OutOfRangeError`로 N이 [10, 120] 밖이라고 알린다.

## 3. 재현성 (Acceptance 1-4)

`test_reproducible_training`이 같은 설정·시드로 두 번 학습해 테스트 지표가 상대 1e-6 이내로 같은지 확인한다(작은 데이터셋 사용).

## 4. 하이퍼파라미터 탐색 (User Story 2)

```powershell
python -m surrogate.tune --trials 30 --name mlp_tuned
```

**기대 결과**: `models/mlp_tuned/tuning.json`에 시도 30개와 최적 설정이 기록되고, 최적 설정으로 학습한 모델과 보고서가 저장된다. 탐색 중에는 테스트 세트를 쓰지 않는다.

## 5. 오차 분석 확인 (User Story 3)

`models/<name>/report/`의 `worst_curves.png`, `error_by_input.png`, `cost_error.png`를 연다.
SC-002 최대 오차를 못 맞추면 어느 입력 영역(작은 탱크, 소진 근처 등)에서 틀리는지 여기서 확인하고 research R8의 대응 순서를 따른다.
