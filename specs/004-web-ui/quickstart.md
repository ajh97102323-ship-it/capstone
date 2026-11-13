# Quickstart: 웹 UI 검증 (004)

선행 조건: 002 최종 모델(`optimize.DEFAULT_MODEL`)과 003 `optimize` 패키지.

```powershell
python -m pytest -q tests/test_app_logic.py tests/test_app_ui.py
streamlit run app/main.py
```

| 확인 | 기대 |
|---|---|
| 첫 접속 | 예측 탭에 기본 설계 곡선·지표 |
| N 슬라이더 증가 | 1초 안에 곡선 갱신, 보일오프 비용 ↓, MLI 비용 ↑ |
| 슬라이더 끝 | 학습 범위 밖 불가 |
| R=0.3, Pv0=0.1, N=10 근처 | 소진 시점과 비용 과소평가 경고 |
| 최적화 탭에서 수소 가격 5→10 | 최적 N 증가, 1초 이내 |
| 검증 탭 버튼 | AI·ODE 곡선, 오차, 계산 시간 |
| 브라우저 두 개에서 저장 | 서로의 비교 목록에 안 보임 |
