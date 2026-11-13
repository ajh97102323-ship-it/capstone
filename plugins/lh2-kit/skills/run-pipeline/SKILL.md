---
name: run-pipeline
description: LH2 단열 설계 캡스톤 파이프라인(데이터 생성 → 대리모델 학습 → 비용 최적화 → 웹 UI)을 순서대로 실행하고 결과를 확인한다. "파이프라인 돌려줘", "모델 다시 학습", "최적화 다시", "앱 띄워줘" 같은 요청에 쓴다.
---

# 파이프라인 실행

이 저장소(`physics/` → `data/` → `surrogate/` → `optimize/` → `app/`)를 처음부터 끝까지 다시 돌린다.
저장소 루트에 `CLAUDE.md`와 `requirements.txt`가 있는지 먼저 확인하고, 없으면 이 저장소가 아니라고 알리고 멈춘다.

## 순서

1. 테스트가 전부 통과하는지 먼저 본다. 실패가 있으면 다음 단계로 가지 않는다(헌법 II).
   ```powershell
   python -m pytest -q
   ```
2. 데이터셋 (필요할 때만, 기존이 있으면 건너뜀)
   ```powershell
   python -m data.generate --n 500        # 1만 개는 인자 없이 (약 25초)
   ```
3. 대리모델 탐색·학습 (약 4분)
   ```powershell
   python -m surrogate.tune --dataset data/datasets/lhs_n500_seed42 --trials 30
   ```
4. 최적화와 검증
   ```powershell
   python -m optimize.run --volume 30 --dmax 3.0 --name opt_vol30 --overwrite
   python -m optimize.validate --overwrite
   ```
5. 웹 UI: `streamlit run app/main.py` (포트 8501)

## 보고

- 각 단계의 종료 코드와 마지막 줄(출력 경로)을 적는다.
- `models/<이름>/report/report.md`와 `reports/*/report.md` 맨 위의 SC 판정(PASS/FAIL)을 그대로 옮긴다. FAIL을 숨기지 않는다.
- 최적화 결과는 ODE로 재검증한 값(추천 N, ODE 최적 N, 총비용 상대오차)을 보고한다(헌법 I).

## 주의

- `models/`, `reports/`, `data/datasets/`는 파일 도구로 고치지 않는다(lh2-kit 보호 훅이 막는다). 스크립트로만 다시 만든다.
- 경제 변수(c_layer, p_H2, 수명, 할인율)는 학습 입력에 넣지 않는다. 바꾸려면 `optimize.run`의 옵션으로만 바꾼다.
