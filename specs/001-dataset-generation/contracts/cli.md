# Contract: 명령줄 인터페이스

모든 명령은 저장소 루트에서 `python -m data.<명령>`으로 실행한다. 사람용 진행 상황과 요약은 stdout, 경고와
오류는 stderr로 출력한다. 마지막 줄에는 결과 경로를 출력해 스크립트에서 쓸 수 있게 한다.

## `python -m data.generate`

데이터셋을 생성한다(User Story 1, 3).

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--n INT` | 10000 | 요청 샘플 수 |
| `--seed INT` | 42 | 마스터 시드 |
| `--out DIR` | `data/datasets` | 출력 상위 디렉터리 |
| `--name STR` | `lhs_n{n}_seed{seed}` | 데이터셋 이름 |
| `--range NAME=LO:HI` | (없음) | 입력 범위 변경, 여러 번 사용 가능. 예: `--range R=0.5:2.5` |
| `--overwrite` | 꺼짐 | 같은 이름이 있으면 새 데이터셋이 완성된 뒤 교체 |
| `--inspect` | 꺼짐 | 생성 직후 점검 보고서도 만든다 |

**종료 코드**

| 코드 | 의미 |
|---|---|
| 0 | 성공(경고가 있어도 0) |
| 1 | 설정 오류(범위가 잘못됨, 알 수 없는 변수 이름) |
| 2 | 대상 데이터셋이 이미 있음(`--overwrite` 없음) |
| 3 | 생성 실패 또는 중단(`.partial` 정리 완료) |

**stdout 예**

```text
[generate] lhs_n10000_seed42: 10000 samples, physics 0.1.0 (3f2a1c…)
[generate] 1000/10000 … 10000/10000 (24.8 s)
[generate] valid 10000 / requested 10000 (rejected 0, 0.00%)
[generate] split train 7000 / val 1500 / test 1500, depleted 20.1% (train 20.0 / val 20.4 / test 20.2)
data/datasets/lhs_n10000_seed42
```

## `python -m data.report DATASET_DIR`

점검 보고서를 `DATASET_DIR/report/`에 만든다(User Story 2). 이미 있으면 다시 만든다.
경고가 있으면 stderr에 `WARNING [코드] 메시지` 형식으로 출력한다. 종료 코드는 0(경고 포함) 또는 1(데이터셋을
읽을 수 없음)이다.

## `python -m data.subset DATASET_DIR --sizes 1000 5000`

부분 데이터셋을 `DATASET_DIR/subsets/n{k}.npz`에 만든다(User Story 3, FR-020). k가 유효 샘플 수보다 크면 종료
코드 1. 같은 데이터셋과 크기로 다시 실행하면 같은 결과가 나온다.

## `python -m data.check_physics DATASET_DIR`

저장된 물리 모델 버전과 현재 버전을 비교한다(FR-014a). 일치하면 종료 코드 0, 다르면 stderr에 두 버전과 해시를
출력하고 종료 코드 4.
