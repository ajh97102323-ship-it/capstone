---
name: "speckit-tasks"
description: "사용 가능한 설계 산출물을 바탕으로 feature에 대한 실행 가능하고 의존성 순서로 정렬된 tasks.md를 생성한다."
argument-hint: "작업 생성 시 적용할 제약 조건(선택)"
compatibility: "Requires spec-kit project structure with .specify/ directory"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/tasks.md"
user-invocable: true
disable-model-invocation: false
---


## 사용자 입력

```text
$ARGUMENTS
```

진행하기 전에 사용자 입력을 **MUST** 고려한다(비어 있지 않은 경우).

## 실행 전 점검

**extension hook 확인 (tasks 생성 전)**:
- 프로젝트 루트에 `.specify/extensions.yml`이 있는지 확인한다.
- 파일이 있으면 읽고 `hooks.before_tasks` 키 아래의 항목을 찾는다.
- YAML을 파싱할 수 없거나 유효하지 않으면 조용히 건너뛰지 않는다. `.specify/extensions.yml`을 읽을 수 없었다는 사실(파서 오류 포함)과, 거기 등록된 필수(`optional: false`) hook을 포함해 어떤 hook도 확인하지 못했다는 사실을 사용자에게 알린 뒤 평소대로 계속 진행한다.
- `enabled`가 명시적으로 `false`인 hook은 제외한다. `enabled` 필드가 없는 hook은 기본적으로 활성화된 것으로 간주한다.
- 남은 각 hook에 대해 hook의 `condition` 표현식을 해석하거나 평가하려고 하지 **않는다**:
  - hook에 `condition` 필드가 없거나 null/빈 값이면 실행 가능한 hook으로 간주한다.
  - hook에 비어 있지 않은 `condition`이 정의되어 있으면 그 hook을 건너뛰고, condition 평가는 HookExecutor 구현에 맡긴다.
- hook의 command 이름으로 명령 호출을 구성할 때는 점(`.`)을 하이픈(`-`)으로 바꾼다. 예: `speckit.git.commit` → `/speckit-git-commit`.
- 실행 가능한 각 hook에 대해 `optional` 플래그에 따라 다음을 출력한다:
  - **선택 hook** (`optional: true`):
    ```
    ## Extension Hooks

    **Optional Pre-Hook**: {extension}
    Command: `/{command}`
    Description: {description}

    Prompt: {prompt}
    To execute: `/{command}`
    ```
  - **필수 hook** (`optional: false`):
    ```
    ## Extension Hooks

    **Automatic Pre-Hook**: {extension}
    Executing: `/{command}`
    EXECUTE_COMMAND: {command}

    Wait for the result of the hook command before proceeding to the Outline.
    ```
    위 블록을 출력한 뒤에는 hook을 실제로 호출하고, 끝날 때까지 기다린 다음 계속 진행해야 한다(MUST). 이 agent/세션에서 해당 명령을 직접 실행할 때와 같은 방식으로 실행한다(호출 방식은 위에 표시된 리터럴 `{command}` id와 다를 수 있다. 예를 들어 skills 모드 agent는 `/skill:speckit-...` 또는 `$speckit-...`로 실행한다). 블록을 출력하는 것만으로는 hook이 실행되지 않는다.
- 등록된 hook이 없거나 `.specify/extensions.yml`이 없으면 조용히 건너뛴다.

## 개요 (Outline)

1. **준비**: 저장소 루트에서 `.specify/scripts/powershell/setup-tasks.ps1 -Json`을 실행하고 FEATURE_DIR, TASKS_TEMPLATE_CONTENT, TASKS_TEMPLATE, AVAILABLE_DOCS 목록을 파싱한다. `FEATURE_DIR`과 `TASKS_TEMPLATE`이 제공되는 경우 반드시 절대 경로여야 한다. `AVAILABLE_DOCS`는 `FEATURE_DIR` 아래에서 사용할 수 있는 문서 이름/상대 경로의 목록이다(예: `research.md` 또는 `contracts/`). "I'm Groot"처럼 인자에 작은따옴표가 들어가면 이스케이프 구문을 사용한다. 예: 'I'\''m Groot'(가능하면 큰따옴표 사용: "I'm Groot").

2. **설계 문서 불러오기**: FEATURE_DIR에서 다음을 읽는다:
   - **필수**: plan.md(기술 스택, 라이브러리, 구조), spec.md(우선순위가 매겨진 user story)
   - **선택**: data-model.md(엔티티), contracts/(인터페이스 contract), research.md(결정 사항), quickstart.md(테스트 시나리오)
   - **IF EXISTS**: 프로젝트 원칙과 거버넌스 제약을 위해 `.specify/memory/constitution.md`를 불러온다.
   - 참고: 모든 프로젝트에 모든 문서가 있는 것은 아니다. 있는 문서를 바탕으로 tasks를 생성한다.

3. **tasks 생성 워크플로 실행**:
   - plan.md를 불러와 기술 스택, 라이브러리, 프로젝트 구조를 추출한다.
   - spec.md를 불러와 user story와 그 우선순위(P1, P2, P3 등)를 추출한다.
   - data-model.md가 있으면: 엔티티를 추출해 user story에 매핑한다.
   - contracts/가 있으면: 인터페이스 contract를 user story에 매핑한다.
   - research.md가 있으면: setup 작업에 쓸 결정 사항을 추출한다.
   - user story별로 구성된 tasks를 생성한다(아래 작업 생성 규칙 참고).
   - user story 완료 순서를 보여 주는 의존성 그래프를 생성한다.
   - user story별 병렬 실행 예시를 만든다.
   - 작업의 완전성을 검증한다(각 user story에 필요한 작업이 모두 있고, 독립적으로 테스트할 수 있는지).

4. **tasks.md 생성**: 위 JSON 출력의 TASKS_TEMPLATE_CONTENT를 구조로 사용한다. TASKS_TEMPLATE_CONTENT를 출력하지 않는 구버전 setup 스크립트와의 호환을 위해, 그 경우에는 TASKS_TEMPLATE을 대신 읽는다. 다음 내용으로 채운다:
   - plan.md에서 가져온 정확한 feature 이름
   - Phase 1: Setup 작업(프로젝트 초기화)
   - Phase 2: Foundational 작업(모든 user story의 선행 조건이 되는 차단 작업)
   - Phase 3+: user story마다 phase 하나(spec.md의 우선순위 순서대로)
   - 각 phase에 포함할 내용: story 목표, 독립 테스트 기준, 테스트(요청된 경우), 구현 작업
   - 마지막 Phase: Polish 및 공통 관심사(cross-cutting concerns)
   - 모든 작업은 엄격한 checklist 형식을 따라야 한다(아래 작업 생성 규칙 참고).
   - 작업마다 명확한 파일 경로
   - story 완료 순서를 보여 주는 의존성 섹션
   - story별 병렬 실행 예시
   - 구현 전략 섹션(MVP 우선, 점진적 전달)

## 필수 실행 후 hook

**사용자에게 완료를 보고하기 전에 이 섹션을 반드시 완료해야 한다(MUST).**

프로젝트 루트에 `.specify/extensions.yml`이 있는지 확인한다.
- 파일이 없거나 `hooks.after_tasks` 아래에 등록된 hook이 없으면 완료 보고로 건너뛴다.
- 파일이 있으면 읽고 `hooks.after_tasks` 키 아래의 항목을 찾는다.
- YAML을 파싱할 수 없거나 유효하지 않으면 조용히 건너뛰지 않는다. `.specify/extensions.yml`을 읽을 수 없었다는 사실(파서 오류 포함)과, 거기 등록된 필수(`optional: false`) hook을 포함해 어떤 hook도 확인하지 못했다는 사실을 사용자에게 알린 뒤 완료 보고로 넘어간다.
- `enabled`가 명시적으로 `false`인 hook은 제외한다. `enabled` 필드가 없는 hook은 기본적으로 활성화된 것으로 간주한다.
- 남은 각 hook에 대해 hook의 `condition` 표현식을 해석하거나 평가하려고 하지 **않는다**:
  - hook에 `condition` 필드가 없거나 null/빈 값이면 실행 가능한 hook으로 간주한다.
  - hook에 비어 있지 않은 `condition`이 정의되어 있으면 그 hook을 건너뛰고, condition 평가는 HookExecutor 구현에 맡긴다.
- hook의 command 이름으로 명령 호출을 구성할 때는 점(`.`)을 하이픈(`-`)으로 바꾼다. 예: `speckit.git.commit` → `/speckit-git-commit`.
- 실행 가능한 각 hook에 대해 `optional` 플래그에 따라 다음을 출력한다:
  - **필수 hook** (`optional: false`) — **필수 hook마다 `EXECUTE_COMMAND:`를 반드시 출력해야 한다(MUST)**:
    ```
    ## Extension Hooks

    **Automatic Hook**: {extension}
    Executing: `/{command}`
    EXECUTE_COMMAND: {command}
    ```
    위 블록을 출력한 뒤에는 hook을 실제로 호출하고, 끝날 때까지 기다린 다음 계속 진행해야 한다(MUST). 이 agent/세션에서 해당 명령을 직접 실행할 때와 같은 방식으로 실행한다(호출 방식은 위에 표시된 리터럴 `{command}` id와 다를 수 있다. 예를 들어 skills 모드 agent는 `/skill:speckit-...` 또는 `$speckit-...`로 실행한다). 블록을 출력하는 것만으로는 hook이 실행되지 않는다.
  - **선택 hook** (`optional: true`):
    ```
    ## Extension Hooks

    **Optional Hook**: {extension}
    Command: `/{command}`
    Description: {description}

    Prompt: {prompt}
    To execute: `/{command}`
    ```

## 완료 보고

생성된 tasks.md의 경로와 다음 요약을 출력한다:
- 전체 작업 수
- user story별 작업 수
- 파악된 병렬 실행 기회
- 각 story의 독립 테스트 기준
- 제안하는 MVP 범위(보통 User Story 1만)
- 형식 검증: 모든 작업이 checklist 형식(체크박스, ID, 라벨, 파일 경로)을 따르는지 확인한다.

작업 생성 맥락: $ARGUMENTS

tasks.md는 곧바로 실행할 수 있어야 한다. 각 작업은 LLM이 추가 맥락 없이 완료할 수 있을 만큼 구체적이어야 한다.

## 작업 생성 규칙

**CRITICAL**: 독립적인 구현과 테스트가 가능하도록 작업은 반드시 user story별로 구성해야 한다(MUST).

**테스트는 선택 사항(OPTIONAL)이다**: feature 명세에서 명시적으로 요청했거나 사용자가 TDD 방식을 요청한 경우에만 테스트 작업을 생성한다.

### Checklist 형식 (REQUIRED)

모든 작업은 반드시 이 형식을 엄격하게 따라야 한다(MUST):

```text
- [ ] [TaskID] [P?] [Story?] Description with file path
```

**형식 구성 요소**:

1. **체크박스**: 항상(ALWAYS) `- [ ]`(markdown 체크박스)로 시작한다.
2. **Task ID**: 실행 순서에 따른 일련번호(T001, T002, T003...)
3. **[P] 표시**: 병렬 실행이 가능한 작업(다른 파일을 다루고, 미완료 작업에 의존하지 않음)에만(ONLY) 붙인다.
4. **[Story] 라벨**: user story phase의 작업에만 필수(REQUIRED)다.
   - 형식: [US1], [US2], [US3] 등(spec.md의 user story에 대응)
   - Setup phase: story 라벨 없음(NO)
   - Foundational phase: story 라벨 없음(NO)
   - User Story phase: story 라벨이 반드시 있어야 한다(MUST)
   - Polish phase: story 라벨 없음(NO)
5. **설명**: 정확한 파일 경로를 포함한 명확한 동작

**예시**:

- ✅ CORRECT: `- [ ] T001 Create project structure per implementation plan`
- ✅ CORRECT: `- [ ] T005 [P] Implement authentication middleware in src/middleware/auth.py`
- ✅ CORRECT: `- [ ] T012 [P] [US1] Create User model in src/models/user.py`
- ✅ CORRECT: `- [ ] T014 [US1] Implement UserService in src/services/user_service.py`
- ❌ WRONG: `- [ ] Create User model` (ID와 Story 라벨 누락)
- ❌ WRONG: `T001 [US1] Create model` (체크박스 누락)
- ❌ WRONG: `- [ ] [US1] Create User model` (Task ID 누락)
- ❌ WRONG: `- [ ] T001 [US1] Create model` (파일 경로 누락)

### 작업 구성

1. **User Story(spec.md) 기준** - 주된 구성 방식:
   - 각 user story(P1, P2, P3...)마다 별도 phase를 둔다.
   - 관련된 모든 구성 요소를 해당 story에 매핑한다:
     - 그 story에 필요한 모델
     - 그 story에 필요한 서비스
     - 그 story에 필요한 인터페이스/UI
     - 테스트가 요청된 경우: 그 story 전용 테스트
   - story 간 의존성을 표시한다(대부분의 story는 독립적이어야 한다).

2. **Contract 기준**:
   - 각 인터페이스 contract → 그것이 지원하는 user story에 매핑한다.
   - 테스트가 요청된 경우: 각 인터페이스 contract → 해당 story phase에서 구현 전에 contract 테스트 작업 [P]를 둔다.

3. **Data Model 기준**:
   - 각 엔티티를 그것이 필요한 user story(들)에 매핑한다.
   - 엔티티가 여러 story에 쓰이면: 가장 이른 story 또는 Setup phase에 둔다.
   - 관계 → 적절한 story phase의 서비스 계층 작업으로 둔다.
   - data-model.md에서 제약(최대 길이, nullable/필수, enum 값, 검증 규칙)이 있는 각 필드는 그 제약을 작업 설명에 원문 그대로 인용해, 구현 시점의 재량에 맡겨지지 않게 한다.

4. **Setup/인프라 기준**:
   - 공유 인프라 → Setup phase(Phase 1)
   - 기반/차단 작업 → Foundational phase(Phase 2)
   - story 전용 setup → 해당 story의 phase 안에 둔다.

### Phase 구조

- **Phase 1**: Setup(프로젝트 초기화)
- **Phase 2**: Foundational(차단 선행 조건 - user story보다 먼저 반드시 완료해야 한다(MUST))
- **Phase 3+**: 우선순위 순서의 User Story(P1, P2, P3...)
  - 각 story 안에서: 테스트(요청된 경우) → 모델 → 서비스 → 엔드포인트 → 통합
  - 각 phase는 완결되고 독립적으로 테스트할 수 있는 증분이어야 한다.
- **마지막 Phase**: Polish 및 공통 관심사(Cross-Cutting Concerns)

## 완료 조건

- [ ] 모든 phase, task ID, 파일 경로를 갖춘 tasks.md가 생성되었다
- [ ] 위의 필수 실행 후 hook 규칙에 따라 extension hook이 실행되었거나 건너뛰어졌다
- [ ] 작업 수, story별 내역, MVP 범위와 함께 사용자에게 완료를 보고했다
