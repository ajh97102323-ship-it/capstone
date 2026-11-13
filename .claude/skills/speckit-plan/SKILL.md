---
name: "speckit-plan"
description: "plan 템플릿을 사용해 구현 계획 워크플로를 실행하고 설계 산출물을 생성한다."
argument-hint: "계획 단계에 대한 지침(선택)"
compatibility: "Requires spec-kit project structure with .specify/ directory"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/plan.md"
user-invocable: true
disable-model-invocation: false
---


## 사용자 입력

```text
$ARGUMENTS
```

진행하기 전에 사용자 입력(비어 있지 않다면)을 반드시 고려해야 한다(**MUST**).

## 실행 전 점검

**extension hook 확인(계획 수립 전)**:
- 프로젝트 루트에 `.specify/extensions.yml`이 있는지 확인한다.
- 있으면 읽고 `hooks.before_plan` 키 아래의 항목을 찾는다
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

    Wait for the result of the hook command before proceeding to the Outline.
    ```
    위 블록을 출력한 뒤에는 반드시(MUST) hook을 실제로 호출하고, 끝날 때까지 기다린 다음 계속 진행한다. 이 agent/세션에서 직접 명령을 실행할 때와 같은 방식으로 실행한다(호출 방식은 위에 표시된 리터럴 `{command}` id와 다를 수 있다. 예를 들어 skills 모드 agent는 `/skill:speckit-...` 또는 `$speckit-...`로 실행한다). 블록을 출력하는 것만으로는 hook이 실행되지 않는다.
- 등록된 hook이 없거나 `.specify/extensions.yml`이 없으면 조용히 건너뛴다

## 개요 (Outline)

1. **준비**: repo 루트에서 `.specify/scripts/powershell/setup-plan.ps1 -Json`을 실행하고 JSON을 파싱해 FEATURE_SPEC, IMPL_PLAN, FEATURE_DIR, BRANCH를 얻는다. "I'm Groot"처럼 인자에 작은따옴표가 있으면 이스케이프 구문을 쓴다. 예: 'I'\''m Groot' (가능하면 큰따옴표: "I'm Groot").

2. **맥락 불러오기**: FEATURE_SPEC과 `.specify/memory/constitution.md`를 읽는다. IMPL_PLAN 템플릿(이미 복사되어 있음)을 불러온다.

3. **plan 워크플로 실행**: IMPL_PLAN 템플릿의 구조에 따라 다음을 수행한다:
   - Technical Context를 채운다(알 수 없는 항목은 "NEEDS CLARIFICATION"으로 표시)
   - constitution을 바탕으로 Constitution Check 섹션을 채운다
   - 게이트를 평가한다(정당화되지 않은 위반이 있으면 ERROR)
   - Phase 0: research.md를 생성한다(모든 NEEDS CLARIFICATION 해결)
   - Phase 1: data-model.md, contracts/, quickstart.md를 생성한다
   - 설계 후 Constitution Check를 다시 평가한다

## 필수 실행 후 hook (Mandatory Post-Execution Hooks)

**사용자에게 완료를 보고하기 전에 이 섹션을 반드시(MUST) 마쳐야 한다.**

프로젝트 루트에 `.specify/extensions.yml`이 있는지 확인한다.
- 파일이 없거나 `hooks.after_plan` 아래에 등록된 hook이 없으면 Completion Report로 건너뛴다.
- 있으면 읽고 `hooks.after_plan` 키 아래의 항목을 찾는다.
- YAML을 파싱할 수 없거나 유효하지 않으면 조용히 건너뛰지 않는다. `.specify/extensions.yml`을 읽을 수 없었다는 사실(파서 오류 포함)과, 그곳에 등록된 필수(`optional: false`) hook을 포함해 어떤 hook도 확인하지 못했다는 사실을 사용자에게 알린 뒤 Completion Report로 넘어간다.
- `enabled`가 명시적으로 `false`인 hook은 제외한다. `enabled` 필드가 없는 hook은 기본적으로 활성화된 것으로 본다.
- 남은 각 hook에 대해 hook의 `condition` 표현식을 해석하거나 평가하려고 하지 **않는다**:
  - hook에 `condition` 필드가 없거나 null/빈 값이면 실행 가능한 hook으로 본다
  - hook에 비어 있지 않은 `condition`이 정의되어 있으면 그 hook은 건너뛰고 조건 평가는 HookExecutor 구현에 맡긴다
- hook 명령 이름으로 명령 호출을 구성할 때는 점(`.`)을 하이픈(`-`)으로 바꾼다. 예: `speckit.git.commit` → `/speckit-git-commit`.
- 실행 가능한 각 hook에 대해 `optional` 플래그에 따라 다음을 출력한다:
  - **필수 hook** (`optional: false`) — **필수 hook마다 반드시(MUST) `EXECUTE_COMMAND:`를 출력한다**:
    ```
    ## Extension Hooks

    **Automatic Hook**: {extension}
    Executing: `/{command}`
    EXECUTE_COMMAND: {command}
    ```
    위 블록을 출력한 뒤에는 반드시(MUST) hook을 실제로 호출하고, 끝날 때까지 기다린 다음 계속 진행한다. 이 agent/세션에서 직접 명령을 실행할 때와 같은 방식으로 실행한다(호출 방식은 위에 표시된 리터럴 `{command}` id와 다를 수 있다. 예를 들어 skills 모드 agent는 `/skill:speckit-...` 또는 `$speckit-...`로 실행한다). 블록을 출력하는 것만으로는 hook이 실행되지 않는다.
  - **선택 hook** (`optional: true`):
    ```
    ## Extension Hooks

    **Optional Hook**: {extension}
    Command: `/{command}`
    Description: {description}

    Prompt: {prompt}
    To execute: `/{command}`
    ```

## 완료 보고 (Completion Report)

명령은 Phase 1 설계를 마치면 끝난다. branch, IMPL_PLAN 경로, 생성된 산출물을 보고한다.

## 단계

### Phase 0: 개요 및 research

1. 위 **Technical Context에서 알 수 없는 항목을 추출한다**:
   - 각 NEEDS CLARIFICATION → research task
   - 각 의존성 → 모범 사례 task
   - 각 통합 → 패턴 task

2. **research agent를 생성하고 실제로 띄워 실행(dispatch)한다**:

   ```text
   For each unknown in Technical Context:
     Task: "Research {unknown} for {feature context}"
   For each technology choice:
     Task: "Find best practices for {tech} in {domain}"
   ```

3. 다음 형식으로 `research.md`에 **결과를 정리한다**:
   - Decision: [무엇을 선택했는가]
   - Rationale: [왜 선택했는가]
   - Alternatives considered: [그 밖에 무엇을 검토했는가]

**산출물**: 모든 NEEDS CLARIFICATION이 해결된 research.md

### Phase 1: 설계 및 contract

**선행 조건:** `research.md` 완료

1. **기능 spec에서 엔터티를 추출한다** → `data-model.md`:
   - 엔터티 이름, 필드, 관계
   - 요구사항에서 도출한 검증 규칙
   - 해당한다면 상태 전이

2. **인터페이스 contract를 정의한다**(프로젝트에 외부 인터페이스가 있는 경우) → `/contracts/`:
   - 프로젝트가 사용자나 다른 시스템에 노출하는 인터페이스를 파악한다
   - 프로젝트 유형에 맞는 contract 형식으로 문서화한다
   - 예: 라이브러리의 공개 API, CLI 도구의 명령 스키마, 웹 서비스의 엔드포인트, 파서의 문법, 애플리케이션의 UI contract
   - 순수 내부용 프로젝트(빌드 스크립트, 일회성 도구 등)라면 건너뛴다

3. **quickstart 검증 가이드를 만든다** → `quickstart.md`:
   - 기능이 처음부터 끝까지 동작함을 증명하는 실행 가능한 검증 시나리오를 문서화한다
   - 선행 조건, 준비 명령, 테스트·실행 명령, 기대 결과를 포함한다
   - contract와 data model 세부 내용은 중복해서 쓰지 말고 링크나 참조로 연결한다
   - 전체 구현 코드, 모델·서비스·컨트롤러 본문, 마이그레이션, 완전한 테스트 스위트는 넣지 않는다
   - 이 산출물은 검증·실행 가이드로 유지한다. 구현 세부 사항은 `tasks.md`와 구현 단계의 몫이다

**산출물**: data-model.md, /contracts/*, quickstart.md

## 핵심 규칙

- 파일 시스템 작업에는 절대 경로를 쓰고, 문서 안의 참조에는 프로젝트 기준 상대 경로를 쓴다
- 게이트 실패나 해결되지 않은 명확화 항목이 있으면 ERROR로 처리한다

## 완료 조건

- [ ] plan 워크플로를 실행하고 설계 산출물을 생성했다
- [ ] 위 Mandatory Post-Execution Hooks의 규칙에 따라 extension hook을 실행하거나 건너뛰었다
- [ ] branch, plan 경로, 생성된 산출물과 함께 사용자에게 완료를 보고했다
