# Quickstart: 비용 최적화 검증 (003)

선행 조건: 002 최종 모델이 `models/`에 있다(`optimize.DEFAULT_MODEL`).

```powershell
python -m pytest -q tests/test_optimize_*.py        # 최적화 로직(가짜 대리모델 사용)
python -m optimize.run                              # 기본 설계 최적화 → reports/opt_<모델>/
python -m optimize.run --volume 30 --dmax 3.0 --name opt_vol30 --overwrite   # 체적 고정
python -m optimize.validate                         # SC-001/002/003 → reports/opt_validate_<모델>/
```

기대 결과:

| 확인 | 기대 |
|---|---|
| `report.md` 맨 위 | 대리모델 최적 N, ODE 최적 N, 근사식 N*, 총비용, 연간 손실 질량 표 / 차이 ±2층 이내 |
| `cost_breakdown.png` | MLI 직선 증가, 보일오프 감소, 총비용 U자, ODE·대리모델 겹침 |
| `sensitivity.png` | p_H2 ↑ → N* ↑, c_layer ↑ → N* ↓, 근사식과 같은 경향 |
| 체적 고정, 직경 제약 없음 | 최적 L/D ≤ 0.2 |
| 체적 30 m³, D_max 3.0 m | 2R ≤ 3.0인 L/D 중 가장 작은 값 근처 |
| validate | SC-001(±2층) · SC-002(≤1%) · SC-003(<1 s) 판정 표 |
