# CLAUDE.md — 액화수소 탱크 단열 설계 대리모델 (캡스톤)

LH2 탱크 단열 설계 변수 10개를 넣으면 0~365일 액체 잔량 곡선을 즉시 예측하는 대리모델(surrogate)을 만들고,
그 모델로 **MLI 적층 비용 ↔ 보일오프 손실 비용** 트레이드오프를 최적화한다.

- 배경 설계와 물리식: `PLAN.md` (사용자가 고칠 수 있는 문서)
- 프로젝트 원칙: `.specify/memory/constitution.md` (다른 문서와 충돌하면 헌법이 우선)
- 단계별 명세: `specs/000~004/` (spec.md, 진행 중인 기능은 plan.md·tasks.md 포함)

## 명령

```powershell
pip install -r requirements.txt
python -m pytest -q                                          # 전체 테스트 (수 초)
python -m data.generate --n 300 --seed 1 --out $env:TEMP\ds  # 작은 데이터셋 시험 생성
python -m data.generate                                      # 기본 1만 개 → data/datasets/lhs_n10000_seed42/ (약 25초)
python -m surrogate.tune --dataset data/datasets/lhs_n500_seed42 --trials 30   # 현재 최종 모델 (500개, 약 4분)
python -m optimize.run [--volume 30 --dmax 3.0 --name opt_vol30]               # 비용 최적화 → reports/
python -m optimize.validate                                  # 설계 20개 SC-001~003
streamlit run app/main.py                                    # 웹 UI (공유: --server.address 0.0.0.0, 모델 지정: $env:LH2_MODEL)
```

- 결과 보고서: `python -m report_site.build` → `docs/index.html`. GitHub `main`에 push하면 Vercel이 `docs/`만 올린다(`vercel.json`, `.vercelignore`).
- 플러그인: `plugins/lh2-kit/`(builder·verifier 에이전트, 보호 훅, `run-pipeline`·`publish-report` 스킬). 검사 `claude plugin validate ./plugins/lh2-kit`, 설치 `/plugin marketplace add ajh97102323-ship-it/capstone` → `/plugin install lh2-kit@lh2-capstone`. `.claude/`의 원본을 고치면 플러그인 사본도 같이 고친다.
- 현재 기본 모델은 `optimize.DEFAULT_MODEL` = `models/mlp_lhs_n500_seed42_seed0_tuned`(사용자 지시로 500개 데이터, 002 SC-001·002 미달).
- 이 세션의 샌드박스는 `models/`·`data/datasets/`·`reports/` 쓰기를 스크립트에도 막는다. 생성·학습·보고서 스크립트는 샌드박스 밖에서 실행해야 한다.

- 환경: Windows, Python 3.13. Git 저장소가 아니다(커밋 대신 체크포인트마다 pytest로 상태 확인).
- Git Bash에서는 stderr 한글이 깨져 보일 수 있다. 필요하면 `PYTHONIOENCODING=utf-8`.

## 구조 (데이터 흐름 순)

`physics/` 물리·비용 모델 → `data/` LHS 샘플링·데이터셋 생성 → `surrogate/` 학습 → `optimize/` 비용 최적화 → `app/` 웹 UI(Streamlit)

- `physics/`가 유일한 정답 기준이다. 대리모델·최적화 결과는 반드시 ODE로 재검증해서 보고한다.
- `physics/`는 `data/` 등 다른 패키지를 import하지 않는다.
- 데이터셋 파일 형식과 CLI는 `specs/001-dataset-generation/contracts/`가 계약이다. 키 이름·열 순서·종료 코드를 바꾸지 않는다.

## 규칙 (헌법 요약)

- **테스트 우선 (NON-NEGOTIABLE)**: 동작을 바꾸면 pytest를 먼저 쓰고 실패를 확인한 뒤 구현한다. 테스트가 실패한 상태로 다음 단계로 가지 않는다.
- **물리 모델 변경은 신중히**: `physics/`를 바꾸면 데이터 재생성·재학습 여부를 판단해 기록한다. 물리 상수 옆에는 `[단위]`와 출처를 적는다.
- **경제 변수는 후처리**: c_layer, p_H2, 수명, 할인율은 대리모델 입력이나 데이터셋에 넣지 않는다. 비용은 잔량비에서 계산한다.
- **학습 범위와 재현성**: 입력은 학습 범위 밖으로 받지 않는다. 시드를 고정·기록하고, 생성물에는 설정과 물리 모델 버전(`PHYSICS_VERSION` + 소스 해시)을 함께 저장한다.
- **단순성**: 파이프라인 전체를 먼저 끝까지 연결한다. PLAN.md 10장의 확장 아이디어는 그 뒤에 한다.

## 주요 승인 요건 (각 spec.md의 Success Criteria 중 핵심)

| 단계 | 통과해야 할 기준 |
|---|---|
| 000 물리·비용 모델 | PLAN.md 2.4 체크리스트가 모두 자동 테스트로 통과, 질량 보존 오차 0.1% 이내, 기본 경제 조건의 최적 N이 근사식과 12% 이내 |
| 001 데이터셋 생성 | 1만 개 생성 10분 이내, 유효 샘플 99% 이상, 무작위 20개 재계산 차이 1e-6 이하, 같은 시드면 결과 100% 동일, 분할 70/15/15(±1개)이고 세트별 소진 비율 차이 5%p 이내 |
| 002 대리모델 학습 | 테스트 R² ≥ 0.99, 365일 잔량비 평균 오차 ≤ 0.005·최대 ≤ 0.03, ODE보다 100배 이상 빠름, 예측이 항상 0~1이고 단조 감소 |
| 003 비용 최적화 | 설계 20개에서 대리모델 최적 N이 ODE와 ±2층 이내, 그 N의 ODE 총비용이 최적보다 1% 이상 크지 않음, 경제 변수 변경 후 1초 안에 최적 N 갱신 |
| 004 웹 UI | 입력·경제 변수 변경 후 1초 안에 갱신, 5명 동시 접속에서도 유지, 4개 탭(예측·비교·검증·최적화) 동작, 사용자 간 저장 설계안 노출 0건 |

세부 기준과 수용 시나리오(Given–When–Then)는 각 `specs/00x/spec.md`를 본다.

## 작업 방식

### Spec Kit
`/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-analyze` → `/speckit-implement`
- 현재 기능 위치는 `.specify/feature.json`에 있다.
- 스킬 파일(`.claude/skills/speckit-*`)은 한국어로 번역돼 있다. 영어 원본은 `.specify/backup/skills-en-2026-11-13/`에 있다.

### builder / verifier 분리
- **builder** (`.claude/agents/builder.md`): tasks.md의 지정한 작업만 구현한다. 테스트를 먼저 쓰고, 재현 명령과 함께 보고한다.
- **verifier** (`.claude/agents/verifier.md`): 읽기 전용이다. 맞다는 증거가 아니라 **반례**를 찾는다. 보고를 재현하고, 함수를 메모리에서 일부러 틀리게 바꿔 테스트가 실제로 잡아내는지 확인한다(변이 확인).
- verifier에게는 작업 ID, 바뀐 파일, 실행해 볼 명령만 넘긴다. **builder의 결론("통과했다")은 넘기지 않는다.**
- 메인 세션은 두 보고 모두 그대로 믿지 않고 핵심을 직접 재현한다. tasks.md의 `[X]`는 verifier가 반례를 못 찾은 작업에만 메인 세션이 표시한다.
- **verifier의 반려는 작업마다 2회까지다.** 같은 작업이 두 번 반려되면 builder에게 세 번째로 돌려보내지 않고, 남은 발견사항을 정리해 사용자에게 결정을 받는다.
- builder와 verifier 모두 hook·권한 규칙에 막히면 우회하지 않고 보고한다.

## 보호 장치 (`.claude/settings.json` + `.claude/hooks/guard_protected.py`)

| 대상 | 처리 |
|---|---|
| `reports/**`, `models/**`, `data/datasets/**` 파일 도구로 쓰기 | 차단. 스크립트로만 다시 만든다 |
| 재귀 삭제 (`rm -rf`/`-fr`, `Remove-Item -Recurse`, `shutil.rmtree` 등) | 차단 |
| `physics/**` 수정 (파일 도구, 또는 쓰기 대상이 physics/인 셸 명령) | 확인 요청 |

- 테스트나 시험 생성은 생성물 폴더가 아니라 `tmp_path`나 임시 폴더로 출력한다.
- 메모리 안에서만 함수를 바꾸는 변이 확인, physics를 읽기만 하는 명령은 막히지 않는다.
- 판정 시험 스크립트는 저장소 밖에 있다. hook을 고치면 같은 방식(입력 JSON을 hook에 파이프)으로 다시 시험한다.
