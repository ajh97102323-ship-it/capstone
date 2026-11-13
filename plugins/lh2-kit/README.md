# lh2-kit

액화수소 탱크 단열 설계 대리모델 캡스톤(https://github.com/ajh97102323-ship-it/capstone)의 작업 방식을 묶은 Claude Code 플러그인.

| 구성 | 이름 | 하는 일 |
|---|---|---|
| 에이전트 | `builder` | tasks.md의 지정 작업을 테스트 먼저 쓰고 구현, 재현 명령과 함께 보고 |
| 에이전트 | `verifier` | 읽기 전용. 반례를 찾고 메모리 변이로 테스트가 실제로 잡는지 확인 |
| 훅 | `guard_protected.py` (PreToolUse) | `reports/`·`models/`·`data/datasets/` 파일 도구 쓰기 차단, 재귀 삭제 차단, `physics/` 수정 시 확인 |
| 스킬 | `/lh2-kit:run-pipeline` | 테스트 → 데이터 → 학습 → 최적화 → UI 순서 실행과 SC 보고 |
| 스킬 | `/lh2-kit:publish-report` | `docs/index.html` 재생성, 테스트, push 후 Vercel 확인 |

## 설치

```text
> /plugin marketplace add ajh97102323-ship-it/capstone
> /plugin install lh2-kit@lh2-capstone
> /reload-plugins
```

로컬 시험: `claude --plugin-dir ./plugins/lh2-kit`
검사: `claude plugin validate ./plugins/lh2-kit`

## 필요한 것

- Python 3.13 (`python`이 PATH에 있어야 훅이 돈다). 훅은 표준 라이브러리만 쓴다.
- 훅의 보호 경로는 프로젝트 루트(`CLAUDE_PROJECT_DIR`) 기준이다. 이 저장소 구조가 아닌 폴더에서는 해당 경로가 없으므로 아무것도 막지 않는다.
