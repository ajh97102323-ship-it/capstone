---

description: "Task list for 001-dataset-generation"
---

# Tasks: 대리모델 학습용 데이터셋 생성

**Input**: Design documents from `specs/001-dataset-generation/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: 포함한다. 헌법 원칙 II(물리 경향 테스트 우선, NON-NEGOTIABLE)가 모든 동작 변경에 pytest를 요구한다.
각 스토리에서 테스트를 먼저 쓰고 실패하는 것을 확인한 뒤 구현한다.

**Organization**: 사용자 스토리별로 묶었다. 경로는 저장소 루트(`C:\work\Capstone`) 기준이다.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 병렬 가능(다른 파일, 미완료 작업에 의존하지 않음)
- **[Story]**: US1 / US2 / US3 (spec.md의 사용자 스토리)

## 공통 규약 (모든 작업에 적용)

- 테스트 파일은 기존 관례대로 `tests/` 바로 아래에 둔다. 경로 설정은 T003의 `tests/conftest.py`가 맡는다.
- 숫자에는 단위를 주석이나 이름에 `[단위]`로 적는다(헌법 원칙 III).
- `physics/`는 `data/`를 import하지 않는다(헌법 기술 제약).
- 데이터셋에 비용 관련 값(경제 변수, 비용)을 저장하지 않는다(헌법 원칙 IV, FR-009).
- 파일 형식과 API 이름은 `contracts/dataset-format.md`, CLI 옵션과 종료 코드는 `contracts/cli.md`를 정확히 따른다.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 의존성과 패키지 뼈대

- [X] T001 저장소 루트에 `requirements.txt`를 만든다. 내용: `numpy>=2.0`, `scipy>=1.15`, `matplotlib>=3.8`, `pytest>=8.0`. 그런 다음 `pip install -r requirements.txt`를 실행하고 `python -c "import matplotlib"`로 설치를 확인한다(research R11)
- [X] T002 [P] `data/__init__.py`를 만든다. 내용은 모듈 docstring(`"""대리모델 학습용 데이터셋 생성 패키지 (specs/001-dataset-generation)."""`)만 넣는다
- [X] T003 [P] `tests/conftest.py`를 만들어 저장소 루트를 `sys.path` 맨 앞에 넣는다(`Path(__file__).resolve().parents[1]`). 기존 `tests/test_physics.py`, `tests/test_cost.py`의 `sys.path.insert` 줄은 그대로 둔다. `python -m pytest -q`로 기존 44개 테스트가 통과하는지 확인한다

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 모든 스토리가 쓰는 물리 모델 확장, 버전 식별, 입력 설정

**⚠️ CRITICAL**: 이 단계를 마치기 전에는 사용자 스토리 작업을 시작하지 않는다

### Tests (먼저 작성, 실패 확인)

- [X] T004 [P] `tests/test_physics.py`에 `simulate_detailed` 테스트 3개를 추가한다. ① 소진 설계(`DesignParams(R=0.3, N=10, Pv0=1e-1, G_out=1e-6, S=1e-4, LD=0, fill=0.5)`)에서 `t_empty`가 유한하고, `t_empty`보다 뒤의 격자 시점에서 `ratio == 0`이며, 처음 0이 되는 격자 시점과의 차이가 격자 간격(365/99일) 이하다. 또 촘촘한 격자(`n_points=20001`)로 같은 설계를 다시 풀어 마지막 양수 시점과 처음 0 시점 사이 구간 [t_a, t_b]를 구하고, `t_empty`가 그 구간 안에(허용오차 0.05일) 있는지 확인한다. 격자 근사값(100점 격자의 첫 0 시점)이나 ±2일 어긋난 값이면 실패해야 한다(검증 2회차 발견 #1) ② 기본 `DesignParams()`에서 `t_empty == inf`다. ③ 기존 동작 유지(research R4)는 **고정 기준값**과 비교한다. 기준값 파일 `tests/data/simulate_reference.npz`는 T007 이전 코드로 만든 `simulate()` 출력 스냅샷(설계 33개 × 2개 호출 형태, 설계 입력 포함)이며, 만든 방법과 시점을 `tests/data/README.md`에 적는다. 테스트는 각 설계의 현재 `simulate()` 출력과 `simulate_detailed()[:2]`가 기준값과 `np.array_equal`로 같은지 확인한다. 두 경로끼리만 비교하는 테스트는 항상 참이라 쓰지 않는다(검증 1회차 발견 #2)
- [X] T005 [P] `tests/test_data_versioning.py`를 만든다. `physics/*.py`를 `tmp_path`에 복사해 `physics_fingerprint(root=...)`로 확인한다. ① 같은 내용이면 해시가 같다. ② 줄바꿈만 CRLF↔LF로 바꿔도 해시가 같다. ③ 파일 한 곳에 주석 한 줄을 추가하면 해시가 달라진다. ④ `.py` 파일을 하나 추가하면 해시가 달라진다. ⑤ `__pycache__/x.pyc`를 추가해도 해시가 같다. ⑥ `version`이 `__init__.py`의 `PHYSICS_VERSION` 값과 같다. ⑦ 내용은 그대로 두고 파일 이름만 바꾸면 해시가 달라진다. ⑧ 하위 디렉터리에 `.py`를 추가해도 해시가 같다. ⑨ 사본의 `__init__.py`에서 버전 문자열만 `"9.9.9"`로 바꾸면 `version == "9.9.9"`이다(import가 아니라 파일에서 읽는지 확인). ⑩ 실제 정의 앞에 `# old: PHYSICS_VERSION = "0.0.1"` 주석과 `OLD_PHYSICS_VERSION = "0.0.2"` 줄이 있어도 실제 정의 값을 읽는다. ⑪ 확장자가 대문자(`Upper.PY`)인 파일은 해시에 포함되지 않는다(OS와 무관하게 같은 결과, 검증 1회차 발견 #6·#7). ⑫ 사본 `__init__.py` 앞에 UTF-8 BOM(`b"\xef\xbb\xbf"`)을 붙여도 `version == "0.1.0"`이다. ⑬ `PHYSICS_VERSION: str = "0.1.0"`처럼 타입 주석이 붙어도 읽는다. ⑭ `PHYSICS_VERSION` 정의가 두 번 있으면 `ValueError`(import 결과와 정규식 결과가 달라지는 것을 막음, 검증 2회차 발견 #2·#3)
- [X] T006 [P] `tests/test_data_config.py`를 만든다. ① `DEFAULT_INPUTS`의 이름 순서가 `N, Nbar, eps, G_sup, Pv0, G_out, S, R, LD, fill`이고 모두 `DesignParams` 필드다. ② `parse_range("R=0.5:2.5")`가 `("R", 0.5, 2.5)`를 돌려준다. ③ `"X=1:2"`(알 수 없는 이름), `"R=2:1"`(lo ≥ hi), `"Pv0=0:1"`(로그 변수 lo ≤ 0), `"N=10.5:120"`(정수 변수에 정수 아닌 값), `"R0.5:2.5"`(형식 오류)는 `ValueError`를 낸다. ④ `with_ranges(DEFAULT_INPUTS, [...])`가 바뀐 이름 목록(`defaults_modified`)을 함께 돌려준다. ⑤ 스케일 변경은 Python API로만 지원한다(FR-005): `dataclasses.replace(spec, scale="linear")`로 `G_sup`의 스케일을 바꾼 `inputs`를 `GenerationConfig(inputs=...)`에 넣으면 `to_json_dict()["inputs"]`에 바뀐 스케일이 기록되고, `defaults_modified`에 `"G_sup"`이 들어간다(샘플링 분포 확인은 Phase 3의 T011⑥으로 옮겼다). ⑥ `GenerationConfig`는 입력 이름 집합이 `DEFAULT_INPUTS`의 10개와 정확히 같지 않으면(빠지거나, 남거나, 중복) `ValueError`를 낸다. ⑦ `defaults_modified`는 호출자가 넘긴 값을 받지 않고 항상 `inputs`와 `DEFAULT_INPUTS`를 비교해 계산한다(틀린 값을 넘겨도 무시되거나 `TypeError`). ⑧ 숫자 검증: `split`에 NaN이 있거나 합이 1이 아니면, `days`·`n_requested`·`fixed` 값이 유한한 양수가 아니면, `InputSpec`의 `lo`/`hi`가 숫자(bool 제외)가 아니면 `ValueError`. ⑨ 물리적 하한: `R`, `G_sup`, `Pv0`, `G_out`, `S`, `Nbar`의 `lo > 0`, `N`의 `lo ≥ 1`, `LD`의 `lo ≥ 0`, `eps`·`fill`은 `0 < lo < hi ≤ 1`을 어기는 범위(`parse_range`와 `with_ranges` 모두)는 `ValueError`(검증 1회차 발견 #4·#5·#8). ⑩ 입력 순서가 `DEFAULT_INPUTS`와 다르면 `ValueError`(data-model 1절 "순서가 곧 X 배열의 열 순서", contracts의 `input_names` 순서 고정). ⑪ `GenerationConfig`와 `InputSpec`은 만든 뒤 값을 바꿀 수 없다(frozen: 필드 대입 시 `FrozenInstanceError`, `inputs`는 tuple로 저장). `to_json_dict()["defaults_modified"]`는 항상 현재 `inputs`로 계산한 값이다. ⑫ `name`은 비어 있지 않고, `/`·`\`·`..`를 포함하지 않으며, `.partial`·`.old`로 끝나지 않고, 영문자·숫자·`_`·`-`·`.`만 쓴다. 어기면 `ValueError`(T018의 `out_dir / name`·`.partial` 처리와 충돌 방지, 검증 2회차 발견 #4·#5·#6)

### Implementation

- [X] T007 `physics/model.py`의 `BoiloffModel`에 `simulate_detailed(self, days=SIM_DAYS, n_points=100) -> (t [day], ratio, t_empty [day])`를 추가한다. 기존 `simulate`의 `solve_ivp` 호출을 그대로 옮기고, 소진 이벤트가 있으면 `t_empty = sol.t_events[0][0] / DAY`, 없으면 `np.inf`로 한다. 기존 `BoiloffModel.simulate`는 `simulate_detailed`를 호출해 앞의 두 값만 돌려주도록 바꾼다. 모듈 수준 `simulate()`의 시그니처와 반환값은 바꾸지 않는다. T004 통과 + 기존 44개 통과를 확인한다
- [X] T008 `physics/__init__.py`에 `PHYSICS_VERSION = "0.1.0"`을 추가하고 `__all__`이 있으면 함께 넣는다(research R5)
- [X] T009 [P] `data/versioning.py`에 `physics_fingerprint(root: Path | None = None) -> dict`를 구현한다. 기본 `root`는 `physics` 패키지 디렉터리다. `root.glob("*.py")`를 파일 이름순으로 정렬하고(하위 디렉터리와 `__pycache__` 제외), 파일마다 `이름 + b"\0" + 내용(b"\r\n"→b"\n") + b"\0"`을 SHA-256에 넣는다. `version`은 `root/__init__.py`를 `utf-8-sig`로 읽고(BOM 무시) 정규식 `^PHYSICS_VERSION\s*(?::\s*str\s*)?=\s*["']([^"']+)["']`(MULTILINE, 줄 시작에 고정해 주석과 `OLD_` 접두 이름을 거르고 타입 주석 허용)로 읽는다. 일치가 정확히 1개가 아니면 `ValueError`(import하지 않음, 임시 복사본에서도 동작). 파일 목록은 `suffix == ".py"`(대소문자 구분)로 거른다. 반환값은 `{"version": str, "sha256": str}`. T005가 통과해야 한다
- [X] T010 [P] `data/config.py`를 구현한다. `@dataclass(frozen=True) InputSpec(name, unit, lo, hi, scale)`이고 `scale`은 `"linear" | "log" | "int"`. 검증 규칙(data-model 1절): "`lo < hi`. 로그 변수는 `lo > 0`. 정수 변수는 `lo`, `hi`가 정수." / "이름은 `DesignParams` 필드와 일치해야 하며 중복될 수 없다." `DEFAULT_INPUTS`는 data-model 1절 표와 정확히 같게 둔다: `N` layers 10~120 int / `Nbar` layers/cm 10~30 linear / `eps` - 0.02~0.06 linear / `G_sup` W/K 1e-4~1e-2 log / `Pv0` Pa 1e-4~1e-1 log / `G_out` Pa·m³/s 1e-9~1e-6 log / `S` m³/s 1e-4~1e-2 log / `R` m 0.3~2.5 linear / `LD` - 0~3 linear / `fill` - 0.5~0.95 linear. `@dataclass(frozen=True) GenerationConfig`는 data-model 2절 필드와 기본값을 따른다(`inputs`는 tuple, 입력 이름과 순서가 `DEFAULT_INPUTS`와 같아야 함, `name` 형식 검증 포함, T006⑩~⑫)(`n_requested=10000`, `seed=42`, `fixed={"Th": 300.0}`, `days=365.0`, `n_points=100`, `split=(0.70, 0.15, 0.15)`, `name`은 기본 `f"lhs_n{n_requested}_seed{seed}"`). `to_json_dict()`도 구현한다. 그 밖에 `parse_range(s) -> (name, lo, hi)`와 `with_ranges(inputs, ranges) -> (new_inputs, defaults_modified)`를 둔다. T006이 통과해야 한다

**Checkpoint**: `python -m pytest -q` 전부 통과. 물리 모델 기존 동작이 그대로이고, 버전 식별과 설정이 준비됨

---

## Phase 3: User Story 1 - 기본 데이터셋 한 번에 생성 (Priority: P1) 🎯 MVP

**Goal**: 명령 하나로 1만 개 LHS 샘플 → 곡선 + 보조 출력 → 필터 → 70/15/15 분할 → 설정과 함께 원자적 저장

**Independent Test**: `python -m data.generate --n 300 --seed 1 --out <tmp>`로 만든 데이터셋을 `load_dataset`으로 열어 샘플 수, 범위, 곡선 규칙, 분할 비율을 확인하고, 무작위 샘플을 물리 모델로 다시 계산해 일치하는지 본다

### Tests for User Story 1 (먼저 작성, 실패 확인) ⚠️

- [X] T011 [P] [US1] `tests/test_data_sampling.py`를 만든다(`sample_inputs(inputs, n, rng) -> ndarray (n, 10)` 대상). ① 모든 값이 [lo, hi] 안에 있다. ② N 열이 모두 정수값이고, n=2000일 때 10과 120이 모두 나온다(research R3). ③ n=1000일 때 각 입력을 10개 구간으로 나누면(로그 변수는 log10 구간) 모든 구간에 샘플이 있다(SC-005). ④ 로그 변수의 log10 평균이 구간 중앙과 ±0.05 decade 이내다. ⑤ 같은 시드의 `np.random.Generator`로 두 번 뽑으면 `array_equal`이다. ⑥ `G_sup`의 스케일을 `"linear"`로 바꾼 inputs로 뽑으면 선형 분포가 된다(산술 평균이 구간 중앙과 구간 폭의 5% 이내, T006⑤에서 옮김). ⑦ LHS 층화 확인: n=10으로 뽑으면 정수가 아닌 각 입력을 10개 등구간(로그 변수는 log10 등구간)으로 나눴을 때 모든 구간에 **정확히 1개씩** 들어간다(독립 균등 샘플로 바꾸면 실패해야 함, 검증 3회차 발견 #2)
- [X] T012 [P] [US1] `tests/test_data_simulate.py`를 만든다(`run_sample(x, inputs, cfg) -> SampleResult | Rejection` 대상). ① 기본 설계에서 `Y.shape == (100,)`, `Y[0] == 1`(정확히 1.0, ODE가 1 − 2e-16 같은 값을 돌려줘도 마찬가지), `aux`가 `Q0, m0, m_lost, A_mli, t_empty` 순서다. `m_lost == m0 * (1 - Y[-1])`, `A_mli == BoiloffModel(p).tank.A_tot`, `Q0 == BoiloffModel(p).heat_to_liquid(0, m0)`, `t_empty == inf`. ② T004의 소진 설계에서 `t_empty`가 유한하고, `Y[t > t_empty] == 0`, `m_lost == m0`이다(FR-007). ③ `validate_curve`가 NaN이면 `nan`, 음수이면 `negative`, 1 + 1e-9 초과이면 `above_one`, 인접 차이가 1e-9 초과로 증가하면 `increasing`을 돌려준다(research R6). ④ `monkeypatch`로 `simulate_detailed`가 `RuntimeError`를 던지게 하면 `reason == "solver_error"`이고 `detail`에 메시지가 담긴다. ⑤ 설정 반영: `GenerationConfig(days=100.0, n_points=37)`이면 `Y.shape == (37,)`이고 `BoiloffModel(p).simulate_detailed(100.0, 37)`의 곡선과 같다. `fixed={"Th": 280.0}`이면 결과가 `DesignParams(..., Th=280.0)`로 계산한 값과 같고 `Th=300`일 때와 다르다(검증 3회차 발견 #3)
- [X] T013 [P] [US1] `tests/test_data_split.py`를 만든다(`split_labels(n, ratios, rng) -> int8[n]` 대상). ① n=10000이면 7000/1500/1500, n=999이면 `round(0.7·999)=699`, `round(0.15·999)=150`, 나머지 150. ② 라벨은 0/1/2만 있고 모든 샘플이 정확히 하나의 세트에 속한다. ③ 같은 시드면 결과가 같다
- [X] T014 [US1] `tests/test_data_generate.py`를 만든다(`generate(cfg, out_dir) -> Path`와 `main(argv) -> int` 대상, n=300, `tmp_path` 사용). ① `dataset.npz`, `config.json`, `summary.json`, `rejected.csv`가 생기고 `.partial`이 남지 않는다. ② `np.load(..., allow_pickle=False)`로 열리고, 키 집합이 contracts/dataset-format.md 표와 정확히 같으며, 키 이름에 `cost`, `price`, `p_h2`, `c_layer`가 없다(헌법 원칙 IV). ③ `X`가 범위 안이고 `Y[:,0] == 1`, `0 ≤ Y ≤ 1`, 단조 비증가다. ④ 같은 설정으로 두 번(다른 이름) 생성하면 모든 배열이 `array_equal`이다(SC-004). ⑤ 시드를 고정해 무작위 20개 샘플을 `BoiloffModel(p).simulate_detailed()`로 다시 계산하면 `max|ΔY| ≤ 1e-6`이고(SC-003), 보조 출력 5개(`Q0, m0, m_lost, A_mli, t_empty`)도 상대오차 1e-9 이내로 일치한다(`t_empty`는 둘 다 inf이거나 유한값이 일치, Acceptance 1-2). ⑥ `summary.json`의 `n_requested`, `n_valid`, `split_counts`, `depleted_rate`가 배열에서 직접 센 값과 같다. ⑦ 같은 이름이 있으면 `main`이 종료 코드 2를 돌려주고 기존 파일이 그대로다. `--overwrite`이면 0을 돌려주고 내용이 바뀐다. ⑧ `monkeypatch`로 50번째 `run_sample`에서 `KeyboardInterrupt`를 던지면 `.partial`과 최종 디렉터리가 모두 없고 종료 코드는 3이다(FR-017). ⑨ `run_sample`이 2%의 샘플에서 Rejection을 돌려주게 하면 `summary["warnings"]`에 제외 비율 경고가 있고, `rejected.csv`에 그 행들이 `sample_id`, 입력 10개, `reason`, `detail` 열로 기록되며, `n_valid == n_requested - n_rejected`이다(FR-011, Clarification 3). 경고 경계: 300개 중 정확히 3개(1%) 제외면 경고가 없고, 4개면 경고가 있다. ⑩ 기록 정확성(검증 3회차 발견 #3): `config.json`의 `physics`가 `physics_fingerprint()`와 같다. `created_at`을 `datetime.fromisoformat`으로 읽으면 `tzinfo`가 있다. 분할 라벨이 `split_labels(n_valid, ratios, default_rng(SeedSequence(seed).spawn(3)[1]))`와 같다(LHS와 분할이 서로 다른 spawn 시드를 씀, research R2). ⑪ 이름 대소문자(검증 3회차 발견 #1): `--name foo.PARTIAL`, `--name bar.Old`는 종료 코드 1이고 아무 디렉터리도 생기지 않는다. 임시 폴더에 `foo.PARTIAL` 디렉터리를 미리 만들어 두고 `--name foo`로 생성해도 그 디렉터리와 안의 파일이 그대로 남는다. `load_dataset(<dir>/x.Partial)`은 `ValueError`. ⑫ `main(["--help"])`는 `SystemExit`을 던지지 않고 0을 돌려준다

### Implementation for User Story 1

- [X] T015 [P] [US1] `data/sampling.py`에 `sample_inputs(inputs, n, rng)`를 구현한다. `scipy.stats.qmc.LatinHypercube(d=len(inputs), rng=rng).random(n)`으로 뽑은 뒤 변환한다(research R3): linear는 `lo + u·(hi − lo)`, log는 `10**(log10 lo + u·(log10 hi − log10 lo))`, int는 `clip(lo + floor(u·(hi − lo + 1)), lo, hi)`. T011이 통과해야 한다
- [X] T016 [P] [US1] `data/simulate.py`를 구현한다. `SampleResult(Y, aux, depleted)`, `Rejection(reason, detail)` 데이터클래스, `validate_curve(Y) -> (reason, detail) | None`(research R6 표의 사유 코드와 조건을 그대로 쓴다), `run_sample(x, inputs, cfg)`. `run_sample`은 `DesignParams(**dict(zip(names, x)), **cfg.fixed)`를 만들고 `BoiloffModel(p).simulate_detailed(cfg.days, cfg.n_points)`로 곡선과 `t_empty`를 얻는다. ODE 풀이기는 t=0에서 1.0 대신 1 − 2e-16 같은 값을 돌려줄 수 있으므로(약 13%), `abs(Y[0] − 1) ≤ 1e-12`이면 `Y[0] = 1.0`으로 맞추고, 그보다 크게 벗어나면 `Rejection("initial_not_one", f"Y[0]={Y[0]!r}")`으로 제외한다. 이 보정은 데이터 단계에서만 하고 `physics/`는 고치지 않는다(헌법 원칙 I, 검증 1회차 발견 #3). 보조 출력은 `Q0 = model.heat_to_liquid(0.0, model.m0)` [W], `m0` [kg], `m_lost = m0·(1 − Y[-1])` [kg], `A_mli = model.tank.A_tot` [m²], `t_empty` [day]이다. 예외는 `Rejection("solver_error", str(e))`로 바꾸되 `KeyboardInterrupt`는 다시 던진다. T012가 통과해야 한다
- [X] T017 [P] [US1] `data/split.py`에 `split_labels(n, ratios, rng)`를 구현한다. `n_train = round(r0·n)`, `n_val = round(r1·n)`, `n_test = n − n_train − n_val`로 하고, `rng.permutation(n)` 순서대로 0/1/2를 매긴다(research R7). T013이 통과해야 한다
- [X] T018 [US1] `data/io.py`를 구현한다. ① `write_dataset(final_dir, arrays, config, summary, rejected_rows, overwrite)`: 대상이 있고 `overwrite`가 아니면 `DatasetExistsError`. `<final_dir>.partial/`에 `dataset.npz`(`np.savez`, 비압축, 문자열은 고정 길이 유니코드), `config.json`(`format_version: 1` 포함, UTF-8, `ensure_ascii=False`, indent 2), `summary.json`, `rejected.csv`(제외 0건이어도 헤더 행 기록)를 쓴다. `overwrite`이면 기존 디렉터리를 `<name>.old`로 옮기고 `.partial`을 최종 이름으로 `os.replace`한 뒤 `.old`를 지운다. 예외(KeyboardInterrupt 포함)가 나면 `.partial`을 지우고 다시 던진다(research R10). ② `Dataset` 데이터클래스와 `load_dataset(path)`: 경로가 `.partial`로 끝나면 `ValueError`, `format_version != 1`이면 `ValueError`. 속성은 `X, Y, t, aux, depleted, split, sample_id, input_names, input_scales, input_lo, input_hi, aux_names, config, summary`. ③ `Dataset.part(name) -> (X, Y, aux)`(`"train"=0, "val"=1, "test"=2`)
- [X] T019 [US1] `data/generate.py`에 `generate(cfg, out_dir, overwrite=False) -> Path`와 `main(argv=None) -> int`를 구현한다. 파이프라인: `SeedSequence(cfg.seed).spawn(3)` → [lhs, split, subset] 시드 → `sample_inputs` → 샘플마다 `run_sample`(1000개마다 `[generate] i/n` 출력) → 유효 샘플 모으기 → `split_labels` → summary 계산(data-model 5절 Summary 필드 전부; `reject_rate > 0.01`이면 `warnings`에 추가하고 stderr에 `WARNING [REJECT_HIGH] ...`) → `write_dataset`. config에는 `physics_fingerprint()`, `created_at`(현지 시간대 ISO 8601), `n_valid`, `defaults_modified`를 기록한다. 완료 요약 줄에는 제외 건수와 함께 사유별 건수를 출력한다(예: `rejected 3 (solver_error 2, increasing 1)`, Acceptance 1-1). defaults_modified는 범위뿐 아니라 스케일이 기본값과 다른 입력도 포함한다(FR-005). 배열 키는 contracts/dataset-format.md 표 그대로이고 `t = np.linspace(0, days, n_points)`다. CLI 옵션은 `--n`, `--seed`, `--out`(기본 `data/datasets`), `--name`, `--overwrite`이며, `--range`와 `--inspect`는 US2·US3에서 추가한다. 종료 코드는 contracts/cli.md를 따른다(0 성공 / 1 설정 오류 / 2 이미 있음 / 3 실패·중단). 마지막 줄에 결과 경로를 출력하고, `if __name__ == "__main__": sys.exit(main())`. T014가 통과해야 한다
- [X] T020 [US1] `tests/conftest.py`에 session 범위 fixture `small_dataset`를 추가한다. `tmp_path_factory`에 `generate(GenerationConfig(n_requested=300, seed=1), out)`으로 만든 경로를 돌려준다. US2·US3 테스트가 쓴다

**Checkpoint**: `python -m data.generate --n 300 --out <tmp>`가 동작하고 T011~T014가 통과한다. 이것만으로 002(대리모델 학습)를 시작할 수 있다(MVP)

---

## Phase 4: User Story 2 - 데이터 분포 점검 보고 (Priority: P2)

**Goal**: 데이터셋 하나로 그림 4개, `inspection.json`, `report.md`와 경고를 만든다

**Independent Test**: `small_dataset`에 `python -m data.report <dir>`를 실행해 `report/` 파일이 생기는지, 요약 수치가 배열에서 직접 센 값과 같은지 확인한다

### Tests for User Story 2 ⚠️

- [ ] T021 [P] [US2] `tests/test_data_report.py`를 만든다. ① `small_dataset`에 `main([dir])`를 실행하면 종료 코드 0이고 `report/`에 `report.md`, `inspection.json`, `curves.png`, `ratio365_hist.png`, `sensitivity.png`, `scatter.png`가 생긴다. ② `inspection.json`의 `depleted_rate`, `depleted_rate_by_split`, `ratio365_quantiles`(0, 10, 25, 50, 75, 90, 100%), `ratio365_low_share`, `ratio365_high_share`가 배열에서 직접 계산한 값과 같고, `spearman` 키가 입력 이름 10개이며, `physics_match`가 True다. ③ 순수 함수 `compute_inspection(...)`에 합성 배열을 넣어 경고 규칙을 확인한다: 소진 31% → `DEPLETED_HIGH`, 29% → 없음 / 365일 잔량비 [0, 0.1]에 50% 이상 → `RATIO365_SKEWED`([0.9, 1.0]도 같음) / 세트별 소진 비율 차이 > 5%p → `SPLIT_IMBALANCE` / summary의 `reject_rate` > 1% → `REJECT_HIGH`. ④ 경고가 있으면 `report.md` 맨 위 요약에 코드와 함께 "입력 범위 조정 검토" 안내가 나온다(FR-019)

### Implementation for User Story 2

- [ ] T022 [US2] `data/report.py`를 구현한다. ① `compute_inspection(Y, depleted, split, X, input_names, input_scales, summary, physics_match) -> dict`: data-model 6절 필드를 만들고, Spearman(`scipy.stats.spearmanr`, 로그 변수는 log10 후)은 각 입력 대 `Y[:, -1]`로 계산한다. 경고 규칙은 research R8을 따른다(소진 > 0.30, 한쪽 끝 구간 ≥ 0.50, `reject_rate` > 0.01, 세트별 소진 비율 최대−최소 > 0.05). ② `make_figures(ds, out_dir)`: `matplotlib.use("Agg")`. 곡선 50개(시드 0으로 고르고, 소진 샘플은 다른 색, x축 [day], y축 잔량비), 365일 잔량비 히스토그램(구간 폭 0.05), Spearman 막대, 2×5 산점도(로그 변수는 로그 x축). ③ `write_report(ds_dir)`: `report/`를 새로 만들고 `inspection.json`과 `report.md`(맨 위: 경고 목록 또는 "경고 없음", 다음: 요약 표, 그림 링크)를 쓴다. `physics_match`는 `physics_fingerprint()["sha256"] == config["physics"]["sha256"]`이다. ④ `main(argv) -> int`: 경고를 stderr에 `WARNING [코드] 메시지`로 출력하고, 데이터셋을 읽지 못하면 1을 돌려준다. T021이 통과해야 한다
- [ ] T023 [US2] `data/generate.py`에 `--inspect` 옵션을 추가한다. 생성이 끝나면 `data.report.write_report(path)`를 호출한다. `tests/test_data_generate.py`에 `--inspect`이면 `report/inspection.json`이 생긴다는 테스트를 추가한다

**Checkpoint**: US1 + US2 동작. 점검 보고서로 범위 조정 여부를 판단할 수 있다

---

## Phase 5: User Story 3 - 설정 변경과 부분 데이터셋 (Priority: P3)

**Goal**: 입력 범위 변경, 전체 크기 1k/5k 중첩 부분 데이터셋(각자 70/15/15), 물리 모델 버전 불일치 확인

**Independent Test**: `--range R=0.5:2.5`로 만든 데이터셋의 R 범위와 `defaults_modified`를 확인하고, 1k가 5k의 앞부분과 같은지, 물리 모델 사본을 바꾸면 `check_physics`가 4를 돌려주는지 본다

### Tests for User Story 3 ⚠️

- [ ] T024 [P] [US3] `tests/test_data_ranges.py`를 만든다. ① `main(["--n","200","--range","R=0.5:2.5","--out",tmp,...])`이면 모든 R이 [0.5, 2.5] 안에 있고, `config.json`의 `defaults_modified == ["R"]`이며 `inputs`에 새 범위가 기록된다. 또 `dataset.npz`의 `input_lo/hi`도 새 범위다. ② `--range X=1:2`, `--range R=2:1`이면 종료 코드 1이고 아무 디렉터리도 생기지 않는다. ③ `--range`를 두 번 주면 둘 다 반영된다
- [ ] T025 [P] [US3] `tests/test_data_subset.py`를 만든다(`small_dataset` 사용, n_valid=300 가정 아래 크기 100/200). ① `main([dir, "--sizes", "100", "200"])` → `subsets/n100.npz`, `subsets/n200.npz`가 생긴다. ② `rows(n100) == rows(n200)[:100]`(FR-020 중첩). ③ 각 부분 데이터셋의 split 개수가 `round(0.7k)/round(0.15k)/나머지`다. ④ 다시 실행하면 같은 결과다. 또 `--sizes 200`만 따로 실행한 `n200.npz`의 `rows`와 `split`이 `--sizes 100 200`으로 만든 것과 같다(다른 크기 요청 여부와 무관, 헌법 원칙 V). ⑤ `--sizes 301`이면 종료 코드 1이다. ⑥ `load_subset(dir, 100)`이 Dataset과 같은 속성을 갖고, `X`가 부모의 `X[rows]`와 같다. ⑦ 실행 전후 `dataset.npz`의 수정 시각과 내용이 바뀌지 않는다
- [ ] T026 [P] [US3] `tests/test_data_versioning.py`에 `check_physics` 테스트를 추가한다. ① `small_dataset`에 `check_physics(dir)`를 실행하면 `(True, stored, current)`이고 CLI 종료 코드는 0이다. ② `physics/` 사본을 `tmp_path`에 두고 한 파일을 바꾼 뒤 `check_physics(dir, root=사본)`이면 False이고, `main([dir, "--physics-root", 사본])`은 종료 코드 4이며 stderr에 두 해시가 나온다(FR-014a, Acceptance 1-5)

### Implementation for User Story 3

- [ ] T027 [US3] `data/generate.py`에 `--range NAME=LO:HI` 옵션을 추가한다(`action="append"`). `config.with_ranges`로 반영하고, `ValueError`이면 stderr에 메시지를 쓰고 디렉터리를 만들지 않은 채 종료 코드 1을 돌려준다. `defaults_modified`를 config에 기록한다. T024가 통과해야 한다
- [ ] T028 [US3] `data/split.py`에 `subset_rows(n_valid, sizes, subset_seed) -> dict[int, (rows, split)]`를 추가한다. `subset_seed`는 정수다(data-model 7절). 순서는 `np.random.default_rng(subset_seed).permutation(n_valid)`로 한 번 만들고, 크기 k는 그 앞 k개로 한다. 크기 k의 분할은 `np.random.default_rng(np.random.SeedSequence([subset_seed, k]))`로 만든 rng를 `split_labels`에 넘긴다. 그러면 분할이 k와 `subset_seed`만으로 정해져 `--sizes`에 다른 크기를 함께 요청하든 따로 요청하든 같은 결과가 나온다(research R7, 헌법 원칙 V). k > n_valid이면 `ValueError`. 이어서 `data/io.py`에 `write_subset(ds_dir, k, rows, split, subset_seed)`(`subsets/n{k}.npz`, 키 `rows`, `split`, `size`, `subset_seed`)와 `load_subset(ds_dir, k) -> Dataset`을 추가한다. `subset_seed`는 `int(np.random.SeedSequence(config["seed"]).spawn(3)[2].generate_state(1)[0])`로 파생한다(generate의 LHS·분할 시드와 같은 spawn 결과를 공유). 이 함수는 `data/versioning.py`가 아니라 `data/split.py`의 `derive_subset_seed(master_seed) -> int`로 둔다
- [ ] T029 [US3] `data/subset.py`에 CLI `main(argv) -> int`를 구현한다(`DATASET_DIR --sizes K [K ...]`). 마지막 줄에 만든 파일 경로를 출력한다. T025가 통과해야 한다
- [ ] T030 [US3] `data/io.py`에 `check_physics(ds_dir, root=None) -> (bool, stored: dict, current: dict)`를 추가하고, `data/check_physics.py`에 CLI `main(argv) -> int`(`DATASET_DIR [--physics-root DIR]`)를 구현한다. 일치하면 0, 다르면 stderr에 저장된 version/sha256과 현재 version/sha256을 출력하고 4를 돌려준다. T026이 통과해야 한다

**Checkpoint**: 세 스토리가 모두 독립적으로 동작

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T031 `python -m pytest -q tests/` 전체를 실행해 기존 44개와 새 테스트가 모두 통과하는지 확인한다(헌법 품질 게이트)
- [ ] T032 `specs/001-dataset-generation/quickstart.md`의 1~8단계를 실제로 실행한다. 기본 데이터셋 `data/datasets/lhs_n10000_seed42`를 `--inspect`와 함께 생성하고 걸린 시간을 기록한다(SC-001 10분 이내, SC-002 유효 ≥ 99%, SC-006 세트별 소진 비율 차이 ≤ 5%p). 결과 수치를 `specs/001-dataset-generation/quickstart.md` 맨 아래 "실행 기록" 절에 추가한다
- [ ] T033 `data/datasets/lhs_n10000_seed42/report/report.md`의 결과로 `PLAN.md` 3.4 데이터 점검 체크리스트 4개 항목을 갱신한다(통과하면 `[x]`, 소진 비율 등 실측값을 한 줄로 덧붙임). 경고가 나왔으면 체크하지 말고 범위 조정이 필요하다고 사용자에게 보고한다
- [ ] T034 [P] quickstart 9단계대로 임시 데이터셋(`repro_*`, `small_tanks`, `r05`)을 지운다. 기본 데이터셋 `lhs_n10000_seed42`와 부분 데이터셋은 남긴다

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 의존성 없음
- **Foundational (Phase 2)**: Setup 이후. 모든 스토리를 막는다
  - T004 → T007(물리 확장), T005 → T009, T006 → T010. T008은 T009보다 먼저(해시 대상에 버전 상수 포함)
- **US1 (Phase 3)**: Foundational 이후
- **US2 (Phase 4)**: US1의 `data/io.py`(`load_dataset`)와 T020 fixture가 필요하다. 보고서 로직 자체는 US1과 독립적이다
- **US3 (Phase 5)**: US1의 `generate`, `io`, `split`이 필요하다. US2와는 독립적이다(US2보다 먼저 해도 됨)
- **Polish (Phase 6)**: 모든 스토리 이후

### User Story Dependencies

```text
Setup → Foundational → US1 (MVP) ─┬→ US2 (점검)
                                  └→ US3 (범위·부분 데이터셋·버전 확인)
                                         └→ Polish
```

### Within Each User Story

- 테스트를 먼저 쓰고 실패하는 것을 확인한다(헌법 원칙 II)
- sampling / simulate / split(서로 독립) → io → generate
- `data/generate.py`를 고치는 작업(T019, T023, T027)은 같은 파일이라 순서대로 한다

### Parallel Opportunities

- Phase 1: T002, T003
- Phase 2: 테스트 T004, T005, T006을 동시에 쓰고, 구현 T009, T010을 동시에 한다(T007은 물리 파일이라 따로)
- US1: 테스트 T011, T012, T013 동시, 구현 T015, T016, T017 동시
- US2와 US3: US1 완료 뒤 병렬 진행 가능(단 T023과 T027은 둘 다 `data/generate.py`를 고치므로 순서대로)
- US3: 테스트 T024, T025, T026 동시

---

## Parallel Example: User Story 1

```text
# 테스트 먼저 (서로 다른 파일):
Task: "T011 tests/test_data_sampling.py — 범위, 정수 끝값, 10구간 커버리지, 재현성"
Task: "T012 tests/test_data_simulate.py — 곡선·보조 출력, 소진 규칙, 필터 사유 코드"
Task: "T013 tests/test_data_split.py — 70/15/15 반올림 규칙, 재현성"

# 그다음 구현 (서로 다른 파일):
Task: "T015 data/sampling.py"
Task: "T016 data/simulate.py"
Task: "T017 data/split.py"

# 마지막으로 순서대로: T018 data/io.py → T019 data/generate.py → T020 tests/conftest.py fixture
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 Setup → Phase 2 Foundational (물리 모델 기존 테스트 44개 유지 확인)
2. Phase 3 US1 → `python -m data.generate`로 기본 데이터셋 생성
3. **STOP and VALIDATE**: T014 통과, quickstart 1~4단계 확인
4. 이 시점에서 002(대리모델 학습) spec의 plan을 시작할 수 있다

### Incremental Delivery

1. Setup + Foundational → 기반 준비
2. US1 → 데이터셋 생성 가능 (MVP)
3. US2 → 점검 보고서로 범위 조정 판단
4. US3 → 범위 변경, 학습 곡선용 부분 데이터셋, 물리 모델 변경 감지
5. Polish → 기본 데이터셋 확정, PLAN.md 3.4 갱신

---

## Notes

- [P] = 다른 파일이고 미완료 작업에 의존하지 않음
- **보류 (2026-11-13 사용자 결정)**: Phase 4(US2, T021~T023)와 Phase 5(US3, T024~T030)는 미룬다. MVP(Phase 1~3)가 끝나면 기본 데이터셋 `lhs_n10000_seed42`를 생성하고 002 대리모델 학습으로 넘어간다. Phase 6 중 T033(PLAN.md 3.4 갱신)은 점검 보고서(Phase 4)가 필요하므로 함께 보류한다.
- **알려진 한계 (T006·T010, 반려 한도 초과로 사용자 결정에 따라 남김, 2026-11-13)**
  - `NUL`·`CON` 같은 Windows 예약 이름과 끝에 점이 붙은 이름(`abc.`)을 거부하지 않는다. `abc.`는 Windows에서 `abc`와 같은 디렉터리가 된다. 기본 이름(`lhs_n{n}_seed{seed}`)을 쓰면 생기지 않는다.
  - `GenerationConfig(fixed={})`를 받아들인다. 이 경우 외부 온도(기본 300 K)가 config.json에 기록되지 않는다. 기본값은 `{"Th": 300.0}`이다.
  - `GenerationConfig`는 frozen이지만 `fixed` dict 안의 값은 바꿀 수 있다.
  - 대소문자만 다른 `.PARTIAL`·`.OLD` 이름 문제는 데이터 삭제로 이어지므로 T014⑪/T018에서 고친다(고침).
- **알려진 한계 (T011·T012·T014·T018·T019, 반려 한도 도달로 사용자 결정에 따라 남김, 2026-11-13)**
  - Windows에서 경로 끝에 점을 붙이면(`load_dataset("x.partial.")`) `.partial` 거부를 피해 읽힌다.
  - 이름 끝에 점을 붙이고(`--name foo.partial.`) `--overwrite`를 주면, Windows에서는 기존 `foo.partial` 디렉터리가 덮어써져 지워진다. 이상한 이름과 `--overwrite`를 함께 명시해야 일어난다.
  - 작업 경로(`<name>.partial`/`.old`)가 이미 있어 멈출 때(종료 코드 3), 오류 메시지에 "지우지 않음"과 "(.partial 정리 완료)"가 함께 나온다. 디렉터리는 보존된다. 강제 종료로 남은 낡은 `.partial`은 사용자가 직접 지워야 한다.
  - `config.json`에 고정값(`fixed`)이 빠지는 회귀를 잡는 테스트가 없다(현재 구현은 `{"Th": 300.0}`을 올바르게 기록).
- 저장소가 git이 아니므로 커밋 대신 체크포인트마다 `python -m pytest -q`로 상태를 확인한다
- 물리 모델(`physics/`)은 T007, T008 외에는 고치지 않는다. 고쳐야 할 일이 생기면 멈추고 사용자에게 알린다(헌법 원칙 I)
