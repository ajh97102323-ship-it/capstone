# Quickstart: 데이터셋 생성 검증 가이드

구현이 끝난 뒤 이 순서대로 실행하면 spec의 수용 시나리오와 성공 기준을 끝까지 확인할 수 있다.
명령 형식은 [contracts/cli.md](contracts/cli.md), 파일 형식은 [contracts/dataset-format.md](contracts/dataset-format.md)를 참고한다.

## 0. 준비

```powershell
pip install -r requirements.txt
python -m pytest -q          # 기존 물리 테스트 44개 + 데이터 테스트 모두 통과 (헌법 원칙 II)
```

## 1. 기본 데이터셋 생성 (User Story 1, SC-001·002·006)

```powershell
Measure-Command { python -m data.generate --inspect | Out-Host }
```

**기대 결과**
- 10분 안에 끝난다(실측 예상 1분 이내).
- `valid ≥ 9900 / requested 10000`.
- 분할이 7000 / 1500 / 1500(±1)이고, 세트별 소진 비율 차이가 5%p 이내다.
- `data/datasets/lhs_n10000_seed42/`에 `dataset.npz`, `config.json`, `summary.json`, `rejected.csv`, `report/`가 생긴다.
- `data/datasets/` 아래에 `.partial` 디렉터리가 남지 않는다.

## 2. 재계산 일치 (Acceptance 1-2, SC-003)

pytest의 `test_resimulate_matches`가 무작위 샘플 20개를 물리 모델로 다시 풀어, 곡선 차이가 1e-6 이하이고 보조
출력이 일치하는지 확인한다. 수동으로 확인하려면 `load_dataset`으로 샘플 하나를 꺼내 `physics.simulate`
결과와 비교한다.

## 3. 재현성 (Acceptance 1-4, SC-004)

```powershell
python -m data.generate --n 500 --seed 7 --name repro_a
python -m data.generate --n 500 --seed 7 --name repro_b
```

**기대 결과**: 두 `dataset.npz`의 모든 배열이 같다(`test_reproducible`이 자동으로 확인).

## 4. 덮어쓰기 보호 (Acceptance 3-3, FR-016)

```powershell
python -m data.generate --n 500 --seed 7 --name repro_a    # 종료 코드 2, 기존 데이터셋 그대로
python -m data.generate --n 500 --seed 7 --name repro_a --overwrite    # 종료 코드 0
```

## 5. 점검 보고서 확인 (User Story 2, SC-007)

`data/datasets/lhs_n10000_seed42/report/report.md`를 연다.

**기대 결과**
- 곡선 50개, 365일 잔량 히스토그램, 민감도(상관 막대, 산점도) 그림이 있다.
- 소진 비율은 약 20%이고(사전 시뮬레이션 값), 경고가 없다.
- 맨 위 요약만 보고 범위 조정이 필요한지 판단할 수 있다.

경고 동작 확인: `python -m data.generate --n 500 --range R=0.3:0.6 --name small_tanks --inspect`로 소형 탱크만
생성하면 `DEPLETED_HIGH` 경고가 나와야 한다.

## 6. 범위 변경 (Acceptance 3-1, FR-005)

```powershell
python -m data.generate --n 500 --range R=0.5:2.5 --name r05
```

**기대 결과**: 모든 샘플의 R이 [0.5, 2.5] 안에 있고, `config.json`의 `defaults_modified`에 `"R"`이 있다.

## 7. 부분 데이터셋 (Acceptance 3-2, FR-020)

```powershell
python -m data.subset data/datasets/lhs_n10000_seed42 --sizes 1000 5000
```

**기대 결과**: `subsets/n1000.npz`의 `rows`가 `n5000.npz`의 `rows` 앞 1000개와 같고, 각각 700/150/150,
3500/750/750으로 나뉜다.

## 8. 물리 모델 버전 확인 (Acceptance 1-5, FR-014a)

```powershell
python -m data.check_physics data/datasets/lhs_n10000_seed42   # 종료 코드 0
```

물리 모델 파일에 주석 한 줄을 추가한 뒤 다시 실행하면 종료 코드 4가 나와야 한다(확인 후 되돌린다).
자동 테스트는 임시 디렉터리에 복사한 가짜 물리 모델 파일로 같은 동작을 확인한다.

## 9. 정리

```powershell
Remove-Item -Recurse data/datasets/repro_*, data/datasets/small_tanks, data/datasets/r05
```
