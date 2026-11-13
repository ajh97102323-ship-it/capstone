---
name: "speckit-specify"
description: "자연어로 된 feature 설명을 바탕으로 feature 명세(specification)를 작성하거나 갱신한다."
argument-hint: "명세할 feature를 설명하세요"
compatibility: "Requires spec-kit project structure with .specify/ directory"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/specify.md"
user-invocable: true
disable-model-invocation: false
---


## 사용자 입력

```text
$ARGUMENTS
```

진행하기 전에 사용자 입력을 **MUST** 고려한다(비어 있지 않은 경우).

## 실행 전 점검

**extension hook 확인 (명세 작성 전)**:
- 프로젝트 루트에 `.specify/extensions.yml`이 있는지 확인한다.
- 파일이 있으면 읽고 `hooks.before_specify` 키 아래의 항목을 찾는다.
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

트리거 메시지에서 사용자가 `/speckit-specify` 뒤에 입력한 텍스트가 **곧** feature 설명이다. 아래에 `$ARGUMENTS`가 문자 그대로 나타나더라도, 이 대화에서 언제나 그 설명을 사용할 수 있다고 가정한다. 사용자가 빈 명령을 입력한 경우가 아니면 다시 말해 달라고 요청하지 않는다.

그 feature 설명을 바탕으로 다음을 수행한다:

1. feature의 **간결한 short name**(2~4단어)을 **만든다**:
   - feature 설명을 분석해 가장 의미 있는 키워드를 추출한다.
   - feature의 본질을 담은 2~4단어 short name을 만든다.
   - 가능하면 동작-명사 형식을 사용한다(예: "add-user-auth", "fix-payment-bug").
   - 기술 용어와 약어(OAuth2, API, JWT 등)는 그대로 유지한다.
   - 간결하되, 한눈에 feature를 이해할 수 있을 만큼 설명적으로 만든다.
   - 예시:
     - "사용자 인증을 추가하고 싶다" → "user-auth"
     - "API에 OAuth2 연동을 구현한다" → "oauth2-api-integration"
     - "분석용 대시보드를 만든다" → "analytics-dashboard"
     - "결제 처리 타임아웃 버그를 고친다" → "fix-payment-timeout"

2. **branch 생성** (선택, hook을 통해):

   위의 실행 전 점검에서 `before_specify` hook이 성공적으로 실행되었다면, 그 hook이 git branch를 생성하거나 해당 branch로 전환했고 `BRANCH_NAME`과 `FEATURE_NUM`이 담긴 JSON을 출력했을 것이다. 이 값들은 참고용으로 기록해 두되, branch 이름이 spec 디렉터리 이름을 결정하지는 **않는다**.

   사용자가 `GIT_BRANCH_NAME`을 명시적으로 제공했다면 그 값을 hook에 그대로 전달해, branch 스크립트가 그 값을 정확히 branch 이름으로 쓰게 한다(접두사/접미사 생성을 모두 건너뜀).

3. **spec feature 디렉터리를 생성한다**:

   사용자가 `SPECIFY_FEATURE_DIRECTORY`를 명시적으로 제공하지 않는 한, spec은 기본 `specs/` 디렉터리 아래에 둔다.

   **`SPECIFY_FEATURE_DIRECTORY` 결정 순서**:
   1. 사용자가 `SPECIFY_FEATURE_DIRECTORY`를 명시적으로 제공했다면(예: 환경 변수, 인자, 설정을 통해) 그대로 사용한다.
   2. 그렇지 않으면 `specs/` 아래에 자동으로 생성한다:
      - `.specify/init-options.json`에서 `feature_numbering`(권장) 또는 `branch_numbering`(deprecated, 마이그레이션 전용 — 향후 릴리스에서 제거 예정)을 확인한다.
      - `"timestamp"`이면 접두사는 `YYYYMMDD-HHMMSS`(현재 타임스탬프)이다.
      - `"sequential"`이거나 값이 없으면 접두사는 `NNN`(`specs/`의 기존 디렉터리를 스캔한 뒤 사용 가능한 다음 3자리 번호)이다.
      - 디렉터리 이름을 `<prefix>-<short-name>` 형식으로 구성한다(예: `003-user-auth` 또는 `20260319-143022-user-auth`).
      - `SPECIFY_FEATURE_DIRECTORY`를 `specs/<directory-name>`으로 설정한다.
      - `branch_numbering`을 사용했다면(`feature_numbering`이 없는 경우) 한 줄 경고를 출력한다: "⚠️ `branch_numbering` in init-options.json is deprecated. Rename to `feature_numbering`."

   **디렉터리와 spec 파일을 생성한다**:
   - 저장소 루트에서 `.specify/scripts/powershell/resolve-template.ps1 spec-template -Json`을 실행하고, `TEMPLATE_CONTENT`를 활성 `spec-template`으로 파싱한다. 공용 resolver는 `append`, `prepend`, `wrap` 전략을 포함해 프로젝트 override, preset 레이어, extension 레이어를 core 템플릿 위에 합성한다. 실패하면 중단하고 결정(resolution) 오류를 보고한다. 템플릿 레이어 하나만 가지고 계속 진행하지 않는다.
   - `mkdir -p SPECIFY_FEATURE_DIRECTORY`
   - `TEMPLATE_CONTENT`를 시작점으로 `SPECIFY_FEATURE_DIRECTORY/spec.md`에 쓴다. 대신 디스크의 템플릿 파일을 복사하지 않는다. preset이 `spec-template`을 합성하는 경우 전체 템플릿을 담은 단일 파일이 존재하지 않기 때문이다.
   - `SPEC_FILE`을 `SPECIFY_FEATURE_DIRECTORY/spec.md`로 설정한다.
   - 결정된 경로를 `.specify/feature.json`에 저장한다:
     ```json
     {
       "feature_directory": "<resolved feature dir>"
     }
     ```
     리터럴 문자열 `SPECIFY_FEATURE_DIRECTORY`가 아니라 실제로 결정된 디렉터리 경로 값(예: `specs/003-user-auth`)을 쓴다.
     이렇게 하면 후속 명령(`/speckit-plan`, `/speckit-tasks` 등)이 git branch 이름 규칙에 의존하지 않고도 feature 디렉터리를 찾을 수 있다.

   **IMPORTANT**:
   - `/speckit-specify` 호출 한 번에 feature는 하나만 생성해야 한다.
   - spec 디렉터리 이름과 git branch 이름은 서로 독립적이다. 같을 수도 있지만 그것은 사용자의 선택이다.
   - spec 디렉터리와 파일은 항상 이 명령이 생성하며, hook이 생성하는 일은 없다.

4. `TEMPLATE_CONTENT`를 사용해 필수 섹션을 파악한다.

5. **IF EXISTS**: 프로젝트 원칙과 거버넌스 제약을 위해 `.specify/memory/constitution.md`를 불러온다.

6. 다음 실행 흐름을 따른다:
    1. 인자에서 사용자 설명을 파싱한다.
       비어 있으면: ERROR "No feature description provided"
    2. 설명에서 핵심 개념을 추출한다.
       식별 대상: 행위자, 행동, 데이터, 제약
    3. 불분명한 부분은 다음과 같이 처리한다:
       - 맥락과 업계 표준에 근거해 합리적으로 추정한다.
       - 다음 경우에만 [NEEDS CLARIFICATION: specific question]으로 표시한다:
         - 그 선택이 feature 범위나 사용자 경험에 큰 영향을 미친다.
         - 함의가 서로 다른 합리적인 해석이 여러 개 존재한다.
         - 합리적인 기본값이 없다.
       - **제한: [NEEDS CLARIFICATION] 표시는 전체 최대 3개**
       - 명확화 항목은 영향도 순으로 우선순위를 매긴다: 범위 > 보안/개인정보 > 사용자 경험 > 기술 세부사항
    4. User Scenarios & Testing 섹션을 채운다.
       명확한 사용자 흐름이 없으면: ERROR "Cannot determine user scenarios"
    5. Functional Requirements를 생성한다.
       각 requirement는 테스트 가능해야 한다.
       명시되지 않은 세부사항에는 합리적인 기본값을 사용한다(가정은 Assumptions 섹션에 기록).
    6. Success Criteria를 정의한다.
       측정 가능하고 기술에 종속되지 않는 결과를 만든다.
       정량 지표(시간, 성능, 규모)와 정성 지표(사용자 만족도, 작업 완료)를 모두 포함한다.
       각 기준은 구현 세부사항 없이 검증할 수 있어야 한다.
    7. Key Entities를 식별한다(데이터가 관련된 경우).
    8. 반환: SUCCESS (spec이 planning 준비 완료)

7. 템플릿 구조를 사용해 SPEC_FILE에 명세를 쓴다. 섹션 순서와 제목은 유지하면서, 플레이스홀더를 feature 설명(인자)에서 도출한 구체적인 내용으로 바꾼다.

8. **명세 품질 검증**: 초기 spec을 작성한 뒤 품질 기준에 따라 검증한다:

   a. **spec 품질 checklist 생성**: checklist 템플릿 구조를 사용해 `SPECIFY_FEATURE_DIRECTORY/checklists/requirements.md`에 다음 검증 항목이 담긴 checklist 파일을 생성한다:

      ```markdown
      # Specification Quality Checklist: [FEATURE NAME]

      **Purpose**: Validate specification completeness and quality before proceeding to planning
      **Created**: [DATE]
      **Feature**: [Link to spec.md]

      ## Content Quality

      - [ ] No implementation details (languages, frameworks, APIs)
      - [ ] Focused on user value and business needs
      - [ ] Written for non-technical stakeholders
      - [ ] All mandatory sections completed

      ## Requirement Completeness

      - [ ] No [NEEDS CLARIFICATION] markers remain
      - [ ] Requirements are testable and unambiguous
      - [ ] Success criteria are measurable
      - [ ] Success criteria are technology-agnostic (no implementation details)
      - [ ] All acceptance scenarios are defined
      - [ ] Edge cases are identified
      - [ ] Scope is clearly bounded
      - [ ] Dependencies and assumptions identified

      ## Feature Readiness

      - [ ] All functional requirements have clear acceptance criteria
      - [ ] User scenarios cover primary flows
      - [ ] Feature meets measurable outcomes defined in Success Criteria
      - [ ] No implementation details leak into specification

      ## Notes

      - Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`
      ```

   b. **검증 실행**: checklist의 각 항목에 비추어 spec을 검토한다:
      - 각 항목이 통과인지 실패인지 판단한다.
      - 발견한 구체적인 문제를 기록한다(관련 spec 섹션을 인용).

   c. **검증 결과 처리**:

      - **모든 항목이 통과하면**: checklist를 완료로 표시하고 필수 실행 후 hook 섹션으로 진행한다.

      - **실패한 항목이 있으면([NEEDS CLARIFICATION] 제외)**:
        1. 실패한 항목과 구체적인 문제를 나열한다.
        2. 각 문제를 해결하도록 spec을 수정한다.
        3. 모든 항목이 통과할 때까지 검증을 다시 실행한다(최대 3회 반복).
        4. 3회 반복 후에도 실패하면 남은 문제를 checklist 메모에 기록하고 사용자에게 경고한다.

      - **[NEEDS CLARIFICATION] 표시가 남아 있으면**:
        1. spec에서 모든 [NEEDS CLARIFICATION: ...] 표시를 추출한다.
        2. **개수 확인**: 표시가 3개를 넘으면 가장 중요한 3개(범위/보안/UX 영향 기준)만 남기고 나머지는 합리적으로 추정한다.
        3. 필요한 각 명확화 항목(최대 3개)에 대해 다음 형식으로 사용자에게 선택지를 제시한다:

           ```markdown
           ## Question [N]: [Topic]

           **Context**: [Quote relevant spec section]

           **What we need to know**: [Specific question from NEEDS CLARIFICATION marker]

           **Suggested Answers**:

           | Option | Answer | Implications |
           |--------|--------|--------------|
           | A      | [First suggested answer] | [What this means for the feature] |
           | B      | [Second suggested answer] | [What this means for the feature] |
           | C      | [Third suggested answer] | [What this means for the feature] |
           | Custom | Provide your own answer | [Explain how to provide custom input] |

           **Your choice**: _[Wait for user response]_
           ```

        4. **CRITICAL - 표 서식**: markdown 표의 서식이 올바른지 확인한다:
           - 파이프를 정렬해 간격을 일관되게 맞춘다.
           - 각 셀의 내용 양옆에 공백을 둔다: `|Content|`가 아니라 `| Content |`
           - 헤더 구분선에는 대시가 최소 3개 있어야 한다: `|--------|`
           - markdown 미리보기에서 표가 올바르게 렌더링되는지 확인한다.
        5. 질문에는 순서대로 번호를 붙인다(Q1, Q2, Q3 - 전체 최대 3개).
        6. 응답을 기다리기 전에 모든 질문을 한꺼번에 제시한다.
        7. 사용자가 모든 질문에 대한 선택을 답할 때까지 기다린다(예: "Q1: A, Q2: Custom - [details], Q3: B").
        8. 각 [NEEDS CLARIFICATION] 표시를 사용자가 선택하거나 제공한 답으로 바꿔 spec을 수정한다.
        9. 모든 명확화가 해결되면 검증을 다시 실행한다.

   d. **checklist 갱신**: 검증을 반복할 때마다 checklist 파일에 현재 통과/실패 상태를 갱신한다.

## 필수 실행 후 hook

**사용자에게 완료를 보고하기 전에 이 섹션을 반드시 완료해야 한다(MUST).**

프로젝트 루트에 `.specify/extensions.yml`이 있는지 확인한다.
- 파일이 없거나 `hooks.after_specify` 아래에 등록된 hook이 없으면 완료 보고로 건너뛴다.
- 파일이 있으면 읽고 `hooks.after_specify` 키 아래의 항목을 찾는다.
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

다음 내용을 담아 사용자에게 완료를 보고한다:
- `SPECIFY_FEATURE_DIRECTORY` — feature 디렉터리 경로
- `SPEC_FILE` — spec 파일 경로
- checklist 결과 요약
- 다음 단계(`/speckit-clarify` 또는 `/speckit-plan`) 진행 준비 여부

**참고:** branch 생성은 `before_specify` hook(git extension)이 담당한다. spec 디렉터리와 파일 생성은 항상 이 core 명령이 담당한다.

## 빠른 가이드라인

- 사용자에게 **무엇이(WHAT)** 필요하고 **왜(WHY)** 필요한지에 집중한다.
- 구현 방법(HOW)은 피한다(기술 스택, API, 코드 구조를 쓰지 않는다).
- 개발자가 아니라 비즈니스 이해관계자를 위해 작성한다.
- spec 안에 포함된 checklist는 만들지 않는다(DO NOT). 그것은 별도 명령의 몫이다.

### 섹션 요구사항

- **필수 섹션**: 모든 feature에서 반드시 작성한다.
- **선택 섹션**: feature와 관련이 있을 때만 포함한다.
- 해당하지 않는 섹션은 통째로 삭제한다("N/A"로 남겨 두지 않는다).

### AI 생성 시 지침

사용자 프롬프트로 이 spec을 만들 때:

1. **합리적으로 추정한다**: 맥락, 업계 표준, 일반적인 패턴을 활용해 빈 곳을 채운다.
2. **가정을 기록한다**: 합리적인 기본값을 Assumptions 섹션에 기록한다.
3. **명확화를 제한한다**: [NEEDS CLARIFICATION] 표시는 최대 3개이며, 다음과 같은 중요한 결정에만 사용한다:
   - feature 범위나 사용자 경험에 큰 영향을 미친다.
   - 함의가 서로 다른 합리적인 해석이 여러 개 있다.
   - 합리적인 기본값이 전혀 없다.
4. **명확화 우선순위를 정한다**: 범위 > 보안/개인정보 > 사용자 경험 > 기술 세부사항
5. **테스터처럼 생각한다**: 모호한 requirement는 모두 "테스트 가능하고 모호하지 않음" checklist 항목에서 실패해야 한다.
6. **명확화가 자주 필요한 영역**(합리적인 기본값이 없을 때만):
   - feature 범위와 경계(특정 사용 사례의 포함/제외)
   - 사용자 유형과 권한(서로 충돌하는 해석이 여러 개 가능할 때)
   - 보안/컴플라이언스 요구사항(법적·재정적으로 중요할 때)

**합리적인 기본값의 예**(이런 것은 묻지 않는다):

- 데이터 보존: 해당 도메인의 업계 표준 관행
- 성능 목표: 별도 명시가 없으면 일반적인 웹/모바일 앱 수준의 기대치
- 오류 처리: 적절한 대체 동작을 갖춘 사용자 친화적 메시지
- 인증 방식: 웹 앱이라면 일반적인 세션 기반 인증 또는 OAuth2
- 연동 패턴: 프로젝트에 맞는 패턴을 사용한다(웹 서비스는 REST/GraphQL, 라이브러리는 함수 호출, 도구는 CLI 인자 등).

### Success Criteria 가이드라인

Success criteria는 다음 조건을 갖춰야 한다:

1. **측정 가능**: 구체적인 지표(시간, 비율, 개수, 속도)를 포함한다.
2. **기술 비종속**: 프레임워크, 언어, 데이터베이스, 도구를 언급하지 않는다.
3. **사용자 중심**: 시스템 내부가 아니라 사용자/비즈니스 관점에서 결과를 기술한다.
4. **검증 가능**: 구현 세부사항을 몰라도 테스트/검증할 수 있다.

**좋은 예**:

- "사용자가 3분 안에 결제를 완료할 수 있다"
- "시스템이 동시 사용자 10,000명을 지원한다"
- "검색의 95%가 1초 안에 결과를 반환한다"
- "작업 완료율이 40% 향상된다"

**나쁜 예**(구현 중심):

- "API 응답 시간이 200ms 미만이다"(너무 기술적이다. "사용자가 결과를 즉시 확인한다"를 사용한다)
- "데이터베이스가 1000 TPS를 처리할 수 있다"(구현 세부사항이다. 사용자 관점의 지표를 사용한다)
- "React 컴포넌트가 효율적으로 렌더링된다"(프레임워크 종속)
- "Redis 캐시 적중률이 80%를 넘는다"(기술 종속)

## 완료 조건

- [ ] 명세가 `SPEC_FILE`에 작성되고 품질 checklist로 검증되었다
- [ ] 위의 필수 실행 후 hook 규칙에 따라 extension hook이 실행되었거나 건너뛰어졌다
- [ ] feature 디렉터리, spec 파일 경로, checklist 결과와 함께 사용자에게 완료를 보고했다
