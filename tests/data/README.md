# tests/data

## simulate_reference.npz

`tests/test_physics.py::test_simulate_matches_reference`(specs/001 T004③)가 쓰는 **고정 기준값**이다.
`simulate_detailed` 추가(T007)로 기존 `simulate()` 출력이 바뀌지 않았는지 확인한다. 현재 코드로 다시 만들면
기준값의 의미가 사라지므로 **재생성하지 않는다**. 물리 모델을 의도적으로 바꿀 때(헌법 원칙 I)에만 새로 만들고,
그 이유를 이 파일에 기록한다.

### 내용

| 키 | dtype / shape | 내용 |
|---|---|---|
| `design_fields` | str (11,) | `DesignParams` 필드 이름 (`N, Nbar, eps, G_sup, Pv0, G_out, S, R, LD, fill, Th`) |
| `designs` | float64 (33, 11) | 설계 입력. 행 하나가 설계 하나 |
| `t_default`, `ratio_default` | float64 (33, 100) | `simulate(p)` (기본 365일, 100점) 출력 |
| `short_days`, `short_n_points` | 스칼라 | 두 번째 호출 형태의 인자: 100.0일, 37점 |
| `t_short`, `ratio_short` | float64 (33, 37) | `simulate(p, 100.0, 37)` 출력 |

설계 33개: 기본 `DesignParams()`, 소진 설계 2개
(`R=0.3, N=10, Pv0=1e-1, G_out=1e-6, S=1e-4, LD=0, fill=0.5`와
`R=0.2, LD=0, N=10, Pv0=10, G_out=1e-4, S=1e-4, G_sup=1.0, fill=0.5`),
`np.random.default_rng(123)`로 PLAN.md 3.1 범위 안에서 뽑은 무작위 설계 30개(N은 정수, 로그 변수는 로그 균등).

### 만든 방법과 시점

1. 2026-11-13 11:40:42 (+09:00), T007 구현 직전에 builder 에이전트가 스냅샷 스크립트(`sim_snapshot.py`)로
   당시 `physics/` 코드의 `simulate()` 출력을 `before.npz`로 저장했다
   (`before.npz` SHA-256 `b3ca40f9c38114aa937b2b78db2b70ab766e644371c599da6c5b3c6594225636`).
2. 그 직후 T007(`physics/model.py`, 수정 시각 11:40:50)과 T008(`physics/__init__.py`)을 적용했다.
3. 2회차 수정에서 `build_reference.py`가 `before.npz`의 배열을 **재계산 없이** 옮기고, 스냅샷 스크립트와 같은
   코드로 설계 입력 목록을 다시 만들어 함께 저장했다(설계 생성에는 `DesignParams` 정의만 쓰고 `simulate`는
   호출하지 않음). 결과 SHA-256 `a9a49ad9694868593a55a012e5e87af358c8cf57a973912e93e346fecbedd611`.

두 스크립트는 저장소 밖 세션 임시 디렉터리에 있었으며 저장소에는 포함하지 않았다.

### 한계

- 저장소가 git이 아니고 T007 이전 `physics/model.py` 원본이 남아 있지 않다. 이 기준값이 **원본 코드로**
  만들어졌다는 근거는 builder의 작업 기록과 파일 수정 시각(`before.npz` 11:40:42 < `model.py` 11:40:50)뿐이며,
  독립적으로 증명할 수 없다.
- 설계 입력은 `before.npz`에 들어 있지 않았으므로 같은 코드(같은 시드)로 다시 만든 것이다. 같은 numpy 버전
  (2.4)의 `default_rng(123)`이 같은 수열을 낸다는 데 근거한다.
- `designs`는 float64로 저장되므로 원래 정수였던 `N`(예: 40)이 실수(40.0)로 복원된다. 테스트가 이 상태로
  비트 단위 일치를 확인하므로 결과에는 영향이 없음을 함께 검증한다.
- 비트 단위 비교(`np.array_equal`)이므로 numpy/scipy 버전이나 플랫폼이 바뀌면 물리 모델이 같아도 실패할 수
  있다. 그 경우 원인을 확인한 뒤에만 재생성한다.
