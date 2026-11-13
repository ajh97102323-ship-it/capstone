---
name: "speckit-converge"
description: "현재 코드베이스를 기능의 spec, plan, tasks와 대조해 평가하고, 아직 구현되지 않은 남은 작업을 새 작업으로 tasks.md에 추가해 implement가 이를 완료할 수 있게 한다."
compatibility: "Requires spec-kit project structure with .specify/ directory"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/converge.md"
user-invocable: true
disable-model-invocation: false
---


## 사용자 입력

```text
$ARGUMENTS
```

진행하기 전에 사용자 입력을 반드시 고려해야 한다(**MUST**, 입력이 비어 있지 않은 경우).

## 실행 전 확인

**extension hook 확인(수렴 전)**:

- 프로젝트 루트에 `.specify/extensions.yml`이 있는지 확인한다.
- 파일이 있으면 읽고 `hooks.before_converge` 키 아래의 항목을 찾는다.
- YAML을 파싱할 수 없거나 유효하지 않으면 조용히 건너뛰지 않는다. `.specify/extensions.yml`을 읽을 수 없었다는 사실(파서 오류 포함)과, 거기에 등록된 필수(`optional: false`) hook을 포함해 어떤 hook도 확인하지 못했다는 사실을 사용자에게 알린 뒤 정상적으로 계속 진행한다.
- `enabled`가 명시적으로 `false`인 hook은 제외한다. `enabled` 필드가 없는 hook은 기본적으로 활성화된 것으로 간주한다.
- 남은 각 hook에 대해 hook의 `condition` 표현식을 해석하거나 평가하려고 시도하지 **않는다**.
  - hook에 `condition` 필드가 없거나 null/빈 값이면 실행 가능한 hook으로 간주한다.
  - hook에 비어 있지 않은 `condition`이 정의되어 있으면 해당 hook을 건너뛰고, condition 평가는 HookExecutor 구현에 맡긴다.
- hook 명령 이름으로 명령 호출을 구성할 때는 점(`.`)을 하이픈(`-`)으로 바꾼다. 예: `speckit.git.commit` → `/speckit-git-commit`.
- 실행 가능한 각 hook에 대해 `optional` 플래그에 따라 다음을 출력한다.
  - **선택 hook** (`optional: true`):

    ```text
    ## Extension Hooks

    **Optional Pre-Hook**: {extension}
    Command: `/{command}`
    Description: {description}

    Prompt: {prompt}
    To execute: `/{command}`
    ```

  - **필수 hook** (`optional: false`):

    ```text
    ## Extension Hooks

    **Automatic Pre-Hook**: {extension}
    Executing: `/{command}`
    EXECUTE_COMMAND: {command}

    Wait for the result of the hook command before proceeding to the Goal.
    ```
    위 블록을 출력한 뒤에는 hook을 실제로 호출하고(MUST), 끝날 때까지 기다린 다음 계속 진행해야 한다. 이 에이전트/세션에서 해당 명령을 직접 실행할 때와 같은 방식으로 실행한다(호출 방식은 위에 표시된 리터럴 `{command}` id와 다를 수 있다. 예를 들어 skills 모드 에이전트는 `/skill:speckit-...` 또는 `$speckit-...` 형태로 실행한다). 블록을 출력하는 것만으로는 hook이 실행되지 않는다.

- 등록된 hook이 없거나 `.specify/extensions.yml`이 없으면 조용히 건너뛴다.

## 목표 (Goal)

기능의 명세, plan, tasks가 요구하는 것과 코드베이스가 현재 구현한 것 사이의 차이를
메운다. `spec.md`, `plan.md`, `tasks.md`를 **유일한 의도의 출처**로 읽고(constitution은
지켜야 할 제약으로 삼는다), 코드의 현재 상태를 평가해 어떤 요구사항, 인수 기준, plan
결정, 기존 작업이 충족되지 않았거나 불완전하거나 일부만 충족되었는지 판단한 뒤, **남은
작업을 하나씩 추적 가능한 새 작업으로** `tasks.md` 맨 아래에 추가해
`/speckit-implement`가 이를 완료할 수 있게 한다. 이 명령은 현재 `tasks.md`에 대해
`/speckit-implement`가 실행된 뒤, 그리고 `/speckit-tasks`가 완전한 `tasks.md`를 만든
뒤에만 실행해야 한다(MUST).

이 명령은 diff 도구가 **아니며** 변경 사항을 추적하지도 **않는다**. 기능 산출물을 기준으로
코드의 현재 상태를 평가할 뿐이다. git도, branch 비교도, 이력도 사용하지 않는다.

## 운영 제약

**추가만 하고 절대 다시 쓰지 않는다(APPEND-ONLY, NEVER REWRITE)**: 이 명령이 하는 쓰기는 `tasks.md`에 새
`## Phase N: Convergence` 섹션을 추가하는 것**뿐**이다. 다음을 해서는 안 된다(MUST NOT).

- `spec.md`나 `plan.md`를 어떤 방식으로든 수정하는 것.
- 기존 작업(이전 Convergence 단계의 작업 포함)을 다시 쓰거나, 번호를 다시 매기거나, 순서를
  바꾸거나, 삭제하는 것.
- 애플리케이션 코드를 수정, 생성, 삭제하는 것. 추가된 작업을 완료하는 것은
  `/speckit-implement`의 일이다.

코드베이스가 이미 모든 것을 충족하면 이 명령은 `tasks.md`를
**바이트 단위까지 그대로** 두고(빈 Convergence 제목도 넣지 않는다) 깨끗한 결과를 보고해야 한다(MUST).

**Constitution 우선권**: 프로젝트 constitution(`.specify/memory/constitution.md`)은
**타협할 수 없다(non-negotiable)**. MUST 원칙을 위반하는 코드는 가장 심각도가 높은 발견 사항이며
그에 맞는 수정 작업을 만든다. constitution이 채워지지 않은 템플릿이면
실패하지 말고 constitution 검사를 자연스럽게 건너뛴다.

## 실행 단계

### 1. 수렴 컨텍스트 초기화

저장소 루트에서 `.specify/scripts/powershell/check-prerequisites.ps1 -Json -RequireSpec -RequireTasks -IncludeTasks`를 한 번 실행하고 JSON을 파싱해 FEATURE_DIR과 AVAILABLE_DOCS를 얻는다. 절대 경로를 도출한다.

- SPEC = FEATURE_DIR/spec.md
- PLAN = FEATURE_DIR/plan.md
- TASKS = FEATURE_DIR/tasks.md
- CONSTITUTION = `.specify/memory/constitution.md` (있는 경우)
`spec.md`, `plan.md`, `tasks.md` 중 하나라도 없으면, 실행해야 할 선행 명령을 명시한 명확하고 실행 가능한
메시지와 함께 중단한다(spec이 없으면 `/speckit-specify`, plan이 없으면 `/speckit-plan`,
tasks가 없으면 `/speckit-tasks`). 부분적인 결과를 출력하지 않는다.
"I'm Groot"처럼 인자에 작은따옴표가 들어가면 이스케이프 구문을 사용한다. 예: 'I'\''m Groot' (가능하면 큰따옴표 사용: "I'm Groot").

### 2. 산출물 불러오기(점진적 공개)

각 산출물에서 꼭 필요한 최소한의 컨텍스트만 불러온다.

**spec.md에서:**

- Functional Requirements (FR-###)
- Success Criteria (SC-###) — 구현 가능한 작업이 필요한 항목만 포함한다. 출시 후 성과
  지표와 비즈니스 KPI는 제외한다.
- User Stories와 각각의 Acceptance Scenarios
- Edge Cases (있는 경우)

**plan.md에서:**

- 아키텍처/스택 선택과 기술적 결정
- Data Model 참조
- 단계와 명시된 접점(plan에서 생성하거나 수정한다고 밝힌 파일/컴포넌트)
- 기술적 제약

**tasks.md에서:**

- 작업 ID(다음 ID와 다음 단계 번호를 계산하기 위해)
- 설명, 단계 그룹, 참조된 파일 경로

**constitution에서(채워지지 않은 템플릿이 아닌 경우):**

- 원칙 이름과 MUST/SHOULD 규범 문장

### 3. 의도 인벤토리 구성

내부 모델을 만든다(원본 산출물을 그대로 출력하지 않는다).

- **요구사항 인벤토리**: FR-### / SC-### / user story 인수 시나리오(예: `US1/AC2`)마다
  안정적인 키를 하나씩 두고, 구현 의무를 부과하는 plan 결정과 constitution 원칙도
  포함한다.
- **코드 범위 맵**: `plan.md`와 `tasks.md`에 명시된 파일 경로와, 각 요구사항이 설명하는
  개념에 대한 키워드 검색을 바탕으로 평가 대상이 되는 소스 파일과 컴포넌트 집합을
  도출한다. 평가는 이 범위로 한정한다. 산출물이 정의한 것을 넘어 범위를 추론하지
  **않는다**.

### 4. 코드베이스 평가 및 발견 사항 분류

체크박스 상태나 Convergence 단계와 관계없이 기존 작업을 모두 의도 인벤토리에 포함한다.
완료했다는 주장은 증거가 아니다. 현재 동작을 spec, plan, tasks, constitution과
대조해 검증한다. 수정 작업이 연쇄된 경우에는 대체된 구현 세부 사항이 아니라 최종
동작을 평가한다. 충족되지 않은 의무와, 명시된 의도와 모순되거나 이를 넘어서거나
벗어난 구현을 모두 확인한다.

의도 인벤토리의 각 항목에 대해 범위 내 현재 코드를 살펴보고, 차이가 있는 경우에만
`Finding`을 만든다. 모든 발견 사항을 **차이 유형**으로 분류한다.

- **`missing`**: 요구된 작업이 코드에 전혀 없다.
- **`partial`**: 작업이 있지만 요구사항 / 인수 기준 / plan 결정을 아직 완전히
  충족하지 못한다.
- **`contradicts`**: 코드가 명시된 의도나 constitution의 MUST 원칙과 충돌하는 일을
  한다.
- **`unrequested`**: spec, plan, tasks가 요구하지 않은 작업이 코드에 있다
  (인지할 수 있도록 드러내는 것이다. converge는 코드를 삭제하지 **않으며**, 이를 검토/정당화하거나
  제거하는 작업만 추가한다).

각 `Finding`에는 안정적인 id, 추적 대상인 `source-ref`, `gap-type`,
심각도, 그리고 증거(관찰한 파일/영역)를 포함한 짧고 읽기 쉬운 설명을 기록한다.

**엣지 케이스:**

- **코드가 거의 또는 전혀 없음**: 실패하지 말고 명시된 범위 전체를 `missing` 남은 작업으로
  처리한다.
- **남은 것이 없음**: 발견 사항을 0개로 하고 이 스킬의 실행 절차 7번(Step 7)에 있는 수렴 완료 분기를 따른다(tasks.md의 Phase 7이 아니다).

### 5. 심각도 지정

- **CRITICAL**: constitution의 MUST 원칙을 위반하거나, P1 user story의 기본 기능을 막는
  `missing`/`contradicts` 차이.
- **HIGH**: 핵심 functional requirement나 인수 기준에 대한 `missing` 또는 `partial`
  차이.
- **MEDIUM**: 부차적 요구사항에 대한 `partial` 차이, 또는 정당성이 불분명한 `unrequested`
  추가 사항.
- **LOW**: 사소한 부분 차이, 다듬기, 또는 위험이 낮은 `unrequested` 추가 사항.

### 6. 세션 내 발견 사항 요약 제시

무엇이든 추가하기 전에 심각도별로 정리한 간결한 요약을 출력한다(아직 파일에 쓰지 않는다).

## Convergence Findings

| ID | Gap Type | Severity | Source | Evidence | Remaining Work |
|----|----------|----------|--------|----------|----------------|
| F1 | missing  | HIGH     | FR-008 | Example: no append-only guard detected in path/to/module.py when writing tasks.md | Add append-only enforcement |

**요약 지표:**

- 확인한 요구사항 / 인수 기준
- 확인한 plan 결정
- 확인한 constitution 원칙(또는 "skipped — template")
- 차이 유형별 발견 사항(missing / partial / contradicts / unrequested)
- 심각도별 발견 사항

### 7. Convergence 작업 추가(또는 수렴 완료 보고)

**실행 가능한 발견 사항이 하나 이상 있으면** (`tasks_appended` 결과):

추가 규약에 따라 `tasks.md`의 **맨 끝**에 추가한다.

1. 기존 작업 ID를 모두 스캔해 최댓값을 `M`으로 둔다. 다음 단계 번호 `N`을 정한다
   (기존 최고 단계 + 1).
2. 새 섹션 제목 `## Phase N: Convergence`를 하나 쓴다.
3. 실행 가능한 발견 사항마다 checklist 항목을 하나씩 출력한다. CRITICAL/HIGH를 먼저 두고,
   0으로 채운 ID `T{M+1:03d}, T{M+2:03d}, …`를 부여한다.

   ```markdown
   - [ ] T042 <imperative description> per <source-ref> (<gap-type>)
   ```

   `<source-ref>`는 작업의 출처를 추적한다. 예: `FR-003`, `SC-002`,
   `US1/AC2`, `plan: storage decision`, `Constitution II`.

   `<gap-type>`은 `missing`, `partial`, `contradicts`, `unrequested` 중 하나다.

   constitution 위반 작업은 가장 먼저 출력하고 `CRITICAL`로
   기술해야 한다(MUST).
4. 기존 ID를 재사용하거나 번호를 다시 매기지 않는다. 이전 Convergence 단계가 있으면 그 아래에
   번호를 따로 매긴 새 단계를 추가하고, 이전 단계는 건드리지 않는다.

**실행 가능한 발견 사항이 없으면** (`converged` 결과):

- `tasks.md`를 전혀 수정하지 **않는다**. 빈 단계 제목도 넣지 않는다.
- 보고: **"✅ Converged — the implementation satisfies the spec, plan, and tasks."**
- 확인한 항목의 요약 수치를 포함한다.

### 8. 다음 작업 안내(인계)

- `tasks_appended`인 경우: 어느 단계에 작업을 몇 개 추가했는지 밝히고, 이를 완료하도록
  `/speckit-implement` 실행을 권장한다. 이어서 converge를 다시 실행하면
  남은 항목이 줄거나 없을 것임을 알린다.
- `converged`인 경우: 리뷰 진행이나 PR 생성을 권장한다. 이 기능의 명시된 범위에 대해서는
  implement를 더 실행할 필요가 없다.

### 9. extension hook 확인

결과를 만든 뒤 프로젝트 루트에 `.specify/extensions.yml`이 있는지 확인한다.

- 파일이 있으면 읽고 `hooks.after_converge` 키 아래의 항목을 찾는다.
- YAML을 파싱할 수 없거나 유효하지 않으면 조용히 건너뛰지 않는다. `.specify/extensions.yml`을 읽을 수 없었다는 사실(파서 오류 포함)과, 거기에 등록된 필수(`optional: false`) hook을 포함해 어떤 hook도 확인하지 못했다는 사실을 사용자에게 알린 뒤 정상적으로 계속 진행한다.
- `enabled`가 명시적으로 `false`인 hook은 제외한다. `enabled` 필드가 없는 hook은 기본적으로 활성화된 것으로 간주한다.
- 남은 각 hook에 대해 hook의 `condition` 표현식을 해석하거나 평가하려고 시도하지 **않는다**.
  - hook에 `condition` 필드가 없거나 null/빈 값이면 실행 가능한 hook으로 간주한다.
  - hook에 비어 있지 않은 `condition`이 정의되어 있으면 해당 hook을 건너뛰고, condition 평가는 HookExecutor 구현에 맡긴다.
- hook을 나열하기 전에 수렴 결과(`converged` 또는 `tasks_appended`)를 세션 내에서 먼저 보고해
  사용자가 선택적 후속 명령을 실행할지 결정할 수 있게 한다.
- hook 명령 이름으로 명령 호출을 구성할 때는 점(`.`)을 하이픈(`-`)으로 바꾼다. 예: `speckit.git.commit` → `/speckit-git-commit`.
- 실행 가능한 각 hook에 대해 `optional` 플래그에 따라 다음을 출력한다.
  - **선택 hook** (`optional: true`):

    ```text
    ## Extension Hooks

    **Optional Hook**: {extension}
    Command: `/{command}`
    Description: {description}

    Prompt: {prompt}
    To execute: `/{command}`
    ```

  - **필수 hook** (`optional: false`):

    ```text
    ## Extension Hooks

    **Automatic Hook**: {extension}
    Executing: `/{command}`
    EXECUTE_COMMAND: {command}
    ```
    위 블록을 출력한 뒤에는 hook을 실제로 호출하고(MUST), 끝날 때까지 기다린 다음 계속 진행해야 한다. 이 에이전트/세션에서 해당 명령을 직접 실행할 때와 같은 방식으로 실행한다(호출 방식은 위에 표시된 리터럴 `{command}` id와 다를 수 있다. 예를 들어 skills 모드 에이전트는 `/skill:speckit-...` 또는 `$speckit-...` 형태로 실행한다). 블록을 출력하는 것만으로는 hook이 실행되지 않는다.

- 등록된 hook이 없거나 `.specify/extensions.yml`이 없으면 조용히 건너뛴다.
