---
name: "speckit-analyze"
description: "task 생성 후 spec.md, plan.md, tasks.md 전반에 걸쳐 파일을 변경하지 않는 산출물 간 일관성·품질 분석을 수행한다."
argument-hint: "분석 시 중점을 둘 영역(선택)"
compatibility: "Requires spec-kit project structure with .specify/ directory"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/analyze.md"
user-invocable: true
disable-model-invocation: false
---


## 사용자 입력

```text
$ARGUMENTS
```

진행하기 전에 사용자 입력(비어 있지 않다면)을 반드시 고려해야 한다(**MUST**).

## 실행 전 점검

**extension hook 확인(분석 전)**:
- 프로젝트 루트에 `.specify/extensions.yml`이 있는지 확인한다.
- 있으면 읽고 `hooks.before_analyze` 키 아래의 항목을 찾는다
- YAML을 파싱할 수 없거나 유효하지 않으면 조용히 건너뛰지 않는다. `.specify/extensions.yml`을 읽을 수 없었다는 사실(파서 오류 포함)과, 그곳에 등록된 필수(`optional: false`) hook을 포함해 어떤 hook도 확인하지 못했다는 사실을 사용자에게 알린 뒤 평소대로 계속 진행한다
- `enabled`가 명시적으로 `false`인 hook은 제외한다. `enabled` 필드가 없는 hook은 기본적으로 활성화된 것으로 본다.
- 남은 각 hook에 대해 hook의 `condition` 표현식을 해석하거나 평가하려고 하지 **않는다**:
  - hook에 `condition` 필드가 없거나 null/빈 값이면 실행 가능한 hook으로 본다
  - hook에 비어 있지 않은 `condition`이 정의되어 있으면 그 hook은 건너뛰고 조건 평가는 HookExecutor 구현에 맡긴다
- hook 명령 이름으로 명령 호출을 구성할 때는 점(`.`)을 하이픈(`-`)으로 바꾼다. 예: `speckit.git.commit` → `/speckit-git-commit`.
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

    Wait for the result of the hook command before proceeding to the Goal.
    ```
    위 블록을 출력한 뒤에는 반드시(MUST) hook을 실제로 호출하고, 끝날 때까지 기다린 다음 계속 진행한다. 이 agent/세션에서 직접 명령을 실행할 때와 같은 방식으로 실행한다(호출 방식은 위에 표시된 리터럴 `{command}` id와 다를 수 있다. 예를 들어 skills 모드 agent는 `/skill:speckit-...` 또는 `$speckit-...`로 실행한다). 블록을 출력하는 것만으로는 hook이 실행되지 않는다.
- 등록된 hook이 없거나 `.specify/extensions.yml`이 없으면 조용히 건너뛴다

## 목표 (Goal)

구현에 들어가기 전에 세 핵심 산출물(`spec.md`, `plan.md`, `tasks.md`) 전반에서 불일치, 중복, 모호성, 명세가 부족한 항목을 찾아낸다. 이 명령은 반드시(MUST) `/speckit-tasks`가 완전한 `tasks.md`를 성공적으로 생성한 뒤에만 실행한다.

## 운영 제약

**엄격한 읽기 전용(STRICTLY READ-ONLY)**: 어떤 파일도 수정하지 **않는다**. 구조화된 분석 보고서를 출력한다. 선택적인 개선 계획을 제안한다(후속 편집 명령을 수동으로 실행하기 전에 사용자가 반드시 명시적으로 승인해야 한다).

**Constitution의 권위**: 프로젝트 constitution(`.specify/memory/constitution.md`)은 이 분석 범위 안에서 **타협할 수 없다(non-negotiable)**. constitution과의 충돌은 자동으로 CRITICAL이며, 원칙을 약화하거나 재해석하거나 조용히 무시하는 대신 spec, plan, tasks를 조정해야 한다. 원칙 자체를 바꿔야 한다면 `/speckit-analyze` 밖에서 별도로, 명시적으로 constitution을 갱신해야 한다.

## 실행 단계

### 1. 분석 맥락 초기화

repo 루트에서 `.specify/scripts/powershell/check-prerequisites.ps1 -Json -RequireSpec -RequireTasks -IncludeTasks`를 한 번 실행하고 JSON을 파싱해 FEATURE_DIR와 AVAILABLE_DOCS를 얻는다. 절대 경로를 도출한다:

- SPEC = FEATURE_DIR/spec.md
- PLAN = FEATURE_DIR/plan.md
- TASKS = FEATURE_DIR/tasks.md

필수 파일이 하나라도 없으면 오류 메시지와 함께 중단한다(누락된 선행 명령을 실행하라고 사용자에게 안내한다).
"I'm Groot"처럼 인자에 작은따옴표가 있으면 이스케이프 구문을 쓴다. 예: 'I'\''m Groot' (가능하면 큰따옴표: "I'm Groot").

### 2. 산출물 불러오기(점진적 공개)

각 산출물에서 꼭 필요한 최소한의 맥락만 불러온다:

**spec.md에서:**

- 개요/맥락
- Functional Requirements
- Success Criteria(측정 가능한 결과 — 예: 성능, 보안, 가용성, 사용자 성공, 비즈니스 영향)
- User Stories
- 엣지 케이스(있다면)

**plan.md에서:**

- 아키텍처·스택 선택
- Data Model 참조
- 단계(Phases)
- 기술적 제약

**tasks.md에서:**

- Task ID
- 설명
- 단계별 그룹
- 병렬 표시 [P]
- 참조된 파일 경로

**constitution에서:**

- 원칙 검증을 위해 `.specify/memory/constitution.md`를 불러온다

### 3. 의미 모델 구축

내부 표현을 만든다(원본 산출물을 출력에 포함하지 않는다):

- **요구사항 목록**: 각 Functional Requirement(FR-###)와 Success Criterion(SC-###)에 대해 안정적인 키를 기록한다. 명시적인 FR-/SC- 식별자가 있으면 이를 기본 키로 쓰고, 가독성을 위해 명령형 구문에서 slug를 추가로 도출해도 된다(예: "User can upload file" → `user-can-upload-file`). Success Criteria 항목 중 구현 작업이 필요한 것(예: 부하 테스트 인프라, 보안 감사 도구)만 포함하고, 출시 후 결과 지표와 비즈니스 KPI(예: "지원 티켓 50% 감소")는 제외한다.
- **user story·행동 목록**: 인수 기준이 있는 개별 사용자 행동
- **task 범위 매핑**: 각 task를 하나 이상의 요구사항 또는 story에 대응시킨다(키워드로 추론하거나 ID, 핵심 구문 같은 명시적 참조 패턴을 활용)
- **constitution 규칙 집합**: 원칙 이름과 MUST/SHOULD 규범 문장을 추출한다

### 4. 탐지 패스(토큰 효율적 분석)

신호가 강한 발견 사항에 집중한다. 발견 사항은 총 50개로 제한하고, 나머지는 초과분 요약으로 묶는다.

#### A. 중복 탐지 (Duplication Detection)

- 거의 중복된 요구사항을 찾는다
- 품질이 낮은 쪽 표현을 통합 대상으로 표시한다

#### B. 모호성 탐지 (Ambiguity Detection)

- 측정 가능한 기준이 없는 모호한 형용사(빠른, 확장 가능한, 안전한, 직관적인, 견고한)를 표시한다
- 해결되지 않은 플레이스홀더(TODO, TKTK, ???, `<placeholder>` 등)를 표시한다

#### C. 명세 부족 (Underspecification)

- 동사는 있지만 목적어나 측정 가능한 결과가 빠진 요구사항
- 인수 기준과의 정합이 빠진 user story
- spec/plan에 정의되지 않은 파일이나 컴포넌트를 참조하는 task

#### D. Constitution 정합 (Constitution Alignment)

- MUST 원칙과 충돌하는 요구사항이나 plan 요소
- constitution이 요구하는 섹션이나 품질 게이트의 누락

#### E. 범위 공백 (Coverage Gaps)

- 연결된 task가 하나도 없는 요구사항
- 대응하는 요구사항·story가 없는 task
- 구현 작업이 필요한 Success Criteria(성능, 보안, 가용성)가 tasks에 반영되지 않은 경우

#### F. 불일치 (Inconsistency)

- 용어 표류(같은 개념을 파일마다 다르게 부름)
- plan에서 참조하지만 spec에는 없는(또는 그 반대인) 데이터 엔터티
- task 순서 모순(예: 의존성 메모 없이 통합 task가 기반 준비 task보다 앞섬)
- 상충하는 요구사항(예: 한쪽은 Next.js를 요구하고 다른 쪽은 Vue를 지정)

### 5. 심각도 지정

다음 휴리스틱으로 발견 사항의 우선순위를 정한다:

- **CRITICAL**: constitution의 MUST 위반, 핵심 spec 산출물 누락, 또는 기본 기능을 가로막는, 연결된 task가 0개인(coverage 0) 요구사항
- **HIGH**: 중복되거나 상충하는 요구사항, 모호한 보안·성능 속성, 테스트할 수 없는 인수 기준
- **MEDIUM**: 용어 표류, 비기능 task 범위 누락, 명세가 부족한 엣지 케이스
- **LOW**: 스타일·문구 개선, 실행 순서에 영향을 주지 않는 사소한 중복

### 6. 간결한 분석 보고서 작성

다음 구조로 Markdown 보고서를 출력한다(파일에 쓰지 않는다):

## Specification Analysis Report

| ID | Category | Severity | Location(s) | Summary | Recommendation |
|----|----------|----------|-------------|---------|----------------|
| A1 | Duplication | HIGH | spec.md:L120-134 | Two similar requirements ... | Merge phrasing; keep clearer version |

(발견 사항마다 행을 하나씩 추가하고, 범주의 첫 글자를 접두어로 한 안정적인 ID를 생성한다.)

**Coverage Summary Table:**

| Requirement Key | Has Task? | Task IDs | Notes |
|-----------------|-----------|----------|-------|

**Constitution Alignment Issues:** (있다면)

**Unmapped Tasks:** (있다면)

**Metrics:**

- Total Requirements
- Total Tasks
- Coverage % (requirements with >=1 task)
- Ambiguity Count
- Duplication Count
- Critical Issues Count

### 7. 다음 조치 제시

보고서 끝에 간결한 Next Actions 블록을 출력한다:

- CRITICAL 이슈가 있으면: `/speckit-implement` 전에 해결하도록 권고한다
- LOW/MEDIUM만 있으면: 사용자가 진행해도 되지만 개선 제안을 제공한다
- 구체적인 명령을 제안한다. 예: "/speckit-specify를 실행해 spec을 보완하세요", "/speckit-plan을 실행해 아키텍처를 조정하세요", "tasks.md를 직접 편집해 'performance-metrics'에 대한 범위를 추가하세요"

### 8. 개선안 제안

사용자에게 묻는다: "상위 N개 이슈에 대해 구체적인 개선 편집안을 제안해 드릴까요?" (자동으로 적용하지 않는다(do NOT).)

### 9. extension hook 확인

보고를 마친 뒤 프로젝트 루트에 `.specify/extensions.yml`이 있는지 확인한다.
- 있으면 읽고 `hooks.after_analyze` 키 아래의 항목을 찾는다
- YAML을 파싱할 수 없거나 유효하지 않으면 조용히 건너뛰지 않는다. `.specify/extensions.yml`을 읽을 수 없었다는 사실(파서 오류 포함)과, 그곳에 등록된 필수(`optional: false`) hook을 포함해 어떤 hook도 확인하지 못했다는 사실을 사용자에게 알린 뒤 평소대로 계속 진행한다
- `enabled`가 명시적으로 `false`인 hook은 제외한다. `enabled` 필드가 없는 hook은 기본적으로 활성화된 것으로 본다.
- 남은 각 hook에 대해 hook의 `condition` 표현식을 해석하거나 평가하려고 하지 **않는다**:
  - hook에 `condition` 필드가 없거나 null/빈 값이면 실행 가능한 hook으로 본다
  - hook에 비어 있지 않은 `condition`이 정의되어 있으면 그 hook은 건너뛰고 조건 평가는 HookExecutor 구현에 맡긴다
- hook 명령 이름으로 명령 호출을 구성할 때는 점(`.`)을 하이픈(`-`)으로 바꾼다. 예: `speckit.git.commit` → `/speckit-git-commit`.
- 실행 가능한 각 hook에 대해 `optional` 플래그에 따라 다음을 출력한다:
  - **선택 hook** (`optional: true`):
    ```
    ## Extension Hooks

    **Optional Hook**: {extension}
    Command: `/{command}`
    Description: {description}

    Prompt: {prompt}
    To execute: `/{command}`
    ```
  - **필수 hook** (`optional: false`):
    ```
    ## Extension Hooks

    **Automatic Hook**: {extension}
    Executing: `/{command}`
    EXECUTE_COMMAND: {command}
    ```
    위 블록을 출력한 뒤에는 반드시(MUST) hook을 실제로 호출하고, 끝날 때까지 기다린 다음 계속 진행한다. 이 agent/세션에서 직접 명령을 실행할 때와 같은 방식으로 실행한다(호출 방식은 위에 표시된 리터럴 `{command}` id와 다를 수 있다. 예를 들어 skills 모드 agent는 `/skill:speckit-...` 또는 `$speckit-...`로 실행한다). 블록을 출력하는 것만으로는 hook이 실행되지 않는다.
- 등록된 hook이 없거나 `.specify/extensions.yml`이 없으면 조용히 건너뛴다

## 운영 원칙

### 맥락 효율

- **신호가 강한 최소한의 토큰**: 망라적인 문서화가 아니라 실행 가능한 발견 사항에 집중한다
- **점진적 공개**: 산출물을 단계적으로 불러온다. 모든 내용을 분석에 쏟아붓지 않는다
- **토큰 효율적인 출력**: 발견 사항 표는 50행으로 제한하고 초과분은 요약한다
- **결정적 결과**: 변경 없이 다시 실행하면 같은 ID와 개수가 나와야 한다

### 분석 지침

- **절대 파일을 수정하지 않는다** (읽기 전용 분석이다)
- **누락된 섹션을 절대 지어내지 않는다** (없으면 정확히 보고한다)
- **constitution 위반을 우선한다** (항상 CRITICAL이다)
- **망라적인 규칙보다 예시를 쓴다** (일반적인 패턴이 아니라 구체적인 사례를 인용한다)
- **이슈가 없어도 깔끔하게 보고한다** (범위 통계와 함께 성공 보고서를 출력한다)

## 맥락

$ARGUMENTS
