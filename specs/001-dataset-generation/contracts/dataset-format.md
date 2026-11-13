# Contract: 데이터셋 파일 형식

002(대리모델 학습), 003(최적화 검증), 004(UI 검증 탭)는 이 형식에 의존한다. 필드 의미는
[data-model.md](../data-model.md)를 참고한다.

## 디렉터리 배치

```text
data/datasets/<name>/
├── dataset.npz          # 숫자 배열 (아래 키 목록)
├── config.json          # GenerationConfig (물리 모델 버전 포함)
├── summary.json         # 생성 요약
├── rejected.csv         # 제외 기록 (제외가 0건이어도 헤더만 있는 파일을 둔다)
├── report/              # (선택) 점검 보고서
│   ├── report.md
│   ├── inspection.json
│   ├── curves.png
│   ├── ratio365_hist.png
│   ├── sensitivity.png
│   └── scatter.png
└── subsets/             # (선택) 부분 데이터셋
    ├── n1000.npz        # 키: rows (int64[k]), split (int8[k]), size, subset_seed
    └── n5000.npz
```

생성 중에는 `data/datasets/<name>.partial/`을 쓴다. 이 이름의 디렉터리는 완성된 데이터셋이 아니며 읽어서는 안 된다.

## `dataset.npz` 키

| 키 | dtype | shape | 내용 |
|---|---|---|---|
| `X` | float64 | (n, 10) | 입력, 물리 단위, `input_names` 순서 |
| `Y` | float64 | (n, 100) | 잔량비 곡선 |
| `t` | float64 | (100,) | 시간 격자 [day], 0 … 365 |
| `aux` | float64 | (n, 5) | `aux_names` 순서 |
| `depleted` | bool | (n,) | |
| `split` | int8 | (n,) | 0 = train, 1 = val, 2 = test |
| `sample_id` | int64 | (n,) | |
| `input_names` | str | (10,) | `N, Nbar, eps, G_sup, Pv0, G_out, S, R, LD, fill` |
| `input_scales` | str | (10,) | `int` / `linear` / `log` (002의 전처리가 로그 변환 대상을 고를 때 씀) |
| `input_lo`, `input_hi` | float64 | (10,) | 학습 범위 (002, 004의 외삽 방지용) |
| `aux_names` | str | (5,) | `Q0, m0, m_lost, A_mli, t_empty` |

- 비용 관련 키는 없다(헌법 원칙 IV, FR-009).
- 읽을 때 `allow_pickle=False`로 열 수 있어야 한다(문자열 배열은 고정 길이 유니코드로 저장).

## `config.json` 예

```json
{
  "name": "lhs_n10000_seed42",
  "n_requested": 10000,
  "n_valid": 10000,
  "seed": 42,
  "inputs": [{"name": "N", "unit": "layers", "lo": 10, "hi": 120, "scale": "int"}, "..."],
  "fixed": {"Th": 300.0},
  "days": 365.0,
  "n_points": 100,
  "split": [0.7, 0.15, 0.15],
  "physics": {"version": "0.1.0", "sha256": "3f2a…"},
  "defaults_modified": [],
  "created_at": "2026-11-13T15:04:05+09:00",
  "format_version": 1
}
```

`format_version`은 이 계약이 바뀌면 올린다. 읽는 쪽은 모르는 버전이면 오류를 내야 한다.

## Python 읽기 API (`data.io`)

| 함수 | 반환 | 비고 |
|---|---|---|
| `load_dataset(path) -> Dataset` | `X, Y, t, aux, depleted, split, sample_id, config, summary` 속성 | `.partial` 경로는 거부 |
| `Dataset.part("train" \| "val" \| "test")` | `(X, Y, aux)` 튜플 | |
| `load_subset(path, size) -> Dataset` | 부분 데이터셋을 Dataset과 같은 모양으로 반환. `split`은 부분 데이터셋 자체 분할 | |
| `check_physics(path) -> (bool, stored, current)` | 물리 모델 해시 일치 여부 (FR-014a) | |
