---
name: "speckit-constitution"
description: "대화형 입력이나 제공된 원칙 입력을 바탕으로 프로젝트 constitution을 작성하거나 갱신한다."
argument-hint: "프로젝트 constitution에 담을 원칙이나 가치"
compatibility: "Requires spec-kit project structure with .specify/ directory"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/constitution.md"
user-invocable: true
disable-model-invocation: false
---


## 사용자 입력

```text
$ARGUMENTS
```

진행하기 전에 사용자 입력을 반드시 고려해야 한다(**MUST**, 입력이 비어 있지 않은 경우).

## 범위 제한

이 명령이 직접 하는 작업은 프로젝트 constitution 자체를 갱신하는 것으로 한정된다. constitution에 의존하는 템플릿과
명령은 실행 시점에 constitution을 읽으므로 여기서 수정하지 않는다.

- 사용자 입력의 모든 부분을 constitution 내용 또는 거버넌스와 무관한 별도 의도 중 하나로
  분류한다.
- 입력에 기능 구현, 코드 생성, 리팩터링, 빌드, 배포 요청이 포함되어 있으면 이를 실행해서는
  안 된다(**MUST NOT**). 대신 보류된 의도로 추출한다.
- 애플리케이션 소스 파일, 기능 라우트, 컴포넌트, 테스트, 배포 파일, 그 밖에 constitution
  워크플로와 무관한 산출물을 생성, 수정, 삭제해서는
  안 된다(**MUST NOT**).
- 어떤 지시가 constitution 내용인지 불분명하면 변경하기 전에 명확히 해 달라고
  요청한다.
- constitution 갱신을 마친 뒤 보류된 각 의도에 대해 `Next Actions` 섹션을 포함한다. 원래 의도를
  나열하고, `/speckit-specify` 같은 적절한 후속 Spec Kit 명령을 제안하되 직접 호출하지
  않는다.
- 거버넌스와 무관한 의도가 없으면 `Next Actions` 섹션을 생략한다.

## 실행 전 확인

**extension hook 확인(constitution 갱신 전)**:
- 프로젝트 루트에 `.specify/extensions.yml`이 있는지 확인한다.
- 파일이 있으면 읽고 `hooks.before_constitution` 키 아래의 항목을 찾는다.
- YAML을 파싱할 수 없거나 유효하지 않으면 조용히 건너뛰지 않는다. `.specify/extensions.yml`을 읽을 수 없었다는 사실(파서 오류 포함)과, 거기에 등록된 필수(`optional: false`) hook을 포함해 어떤 hook도 확인하지 못했다는 사실을 사용자에게 알린 뒤 정상적으로 계속 진행한다.
- `enabled`가 명시적으로 `false`인 hook은 제외한다. `enabled` 필드가 없는 hook은 기본적으로 활성화된 것으로 간주한다.
- 남은 각 hook에 대해 hook의 `condition` 표현식을 해석하거나 평가하려고 시도하지 **않는다**.
  - hook에 `condition` 필드가 없거나 null/빈 값이면 실행 가능한 hook으로 간주한다.
  - hook에 비어 있지 않은 `condition`이 정의되어 있으면 해당 hook을 건너뛰고, condition 평가는 HookExecutor 구현에 맡긴다.
- hook 명령 이름으로 명령 호출을 구성할 때는 점(`.`)을 하이픈(`-`)으로 바꾼다. 예: `speckit.git.commit` → `/speckit-git-commit`.
- 실행 가능한 각 hook에 대해 `optional` 플래그에 따라 다음을 출력한다.
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
    위 블록을 출력한 뒤에는 hook을 실제로 호출하고(MUST), 끝날 때까지 기다린 다음 계속 진행해야 한다. 이 에이전트/세션에서 해당 명령을 직접 실행할 때와 같은 방식으로 실행한다(호출 방식은 위에 표시된 리터럴 `{command}` id와 다를 수 있다. 예를 들어 skills 모드 에이전트는 `/skill:speckit-...` 또는 `$speckit-...` 형태로 실행한다). 블록을 출력하는 것만으로는 hook이 실행되지 않는다.
- 등록된 hook이 없거나 `.specify/extensions.yml`이 없으면 조용히 건너뛴다.

## 개요 (Outline)

`.specify/memory/constitution.md`에 있는 프로젝트 constitution을 갱신하는 작업이다. 현재 적용할
constitution 골격은 명령 실행 시점에 Spec Kit preset/template 해석 스택을 거쳐 `constitution-template`에서
결정된다.

다음 실행 흐름을 따른다.

1. 저장소 루트에서 `.specify/scripts/powershell/resolve-template.ps1 constitution-template -Json`을 실행하고, `TEMPLATE_CONTENT`를 파싱해 현재 적용할 템플릿으로 사용한다.
   - 공용 리졸버는 코어 템플릿으로 대체하기 전에 프로젝트 오버라이드, 조합되는 preset 레이어,
     extension 레이어를 적용한다. 이 단계는 반드시 성공해야 다음으로 넘어갈 수 있다(MUST).
   - 실패하면 중단하고 해석 오류를 보고한다. 기여하는 템플릿 레이어 중 하나만으로
     계속 진행하지 않는다.
   - `.specify/memory/constitution.md`가 있으면 현재 프로젝트 고유의 값과 개정 사항의
     출처로 불러온다. 새로 해석된 골격을 적용할 때 여전히 유효한 정보는
     보존한다.
   - 없으면 해석된 템플릿을 초기 문서로 사용한다.
   - 버전 관리되는 어떤 템플릿 레이어에도 다시 쓰지 않는다.
   - `[ALL_CAPS_IDENTIFIER]` 형태의 플레이스홀더 토큰을 모두 찾는다.
   **중요**: 사용자는 템플릿에 있는 것보다 적거나 많은 원칙을 요구할 수 있다. 개수가 지정되면 이를 따르되 전체적인 템플릿 구성을 지킨다. 그에 맞게 문서를 갱신한다.

2. 플레이스홀더에 들어갈 값을 수집/도출한다.
   - 사용자 입력(대화)에서 값을 제공하면 그 값을 사용한다.
   - 그렇지 않으면 기존 저장소 맥락(README, 문서, 포함되어 있다면 이전 constitution 버전)에서 추론한다.
   - 거버넌스 날짜: `RATIFICATION_DATE`는 최초 채택일이다(모르면 묻거나 TODO로 표시한다). `LAST_AMENDED_DATE`는 변경이 있으면 오늘 날짜로, 없으면 이전 값을 유지한다.
   - `CONSTITUTION_VERSION`은 semantic versioning 규칙에 따라 올려야 한다.
     - MAJOR: 하위 호환되지 않는 거버넌스/원칙의 삭제 또는 재정의.
     - MINOR: 새 원칙/섹션 추가 또는 지침의 실질적 확장.
     - PATCH: 명확화, 문구 수정, 오탈자 수정, 의미에 영향 없는 다듬기.
   - 버전 증가 유형이 모호하면 확정하기 전에 근거를 제시한다.

3. 해석된 템플릿을 필수 구조로 삼아 갱신된 constitution 초안을 작성한다.
   - 모든 플레이스홀더를 구체적인 텍스트로 바꾼다(프로젝트가 아직 정의하지 않기로 의도적으로 남겨 둔 템플릿 슬롯을 제외하고는 대괄호 토큰을 남기지 않는다. 남겨 둔 것은 모두 명시적으로 그 이유를 밝힌다).
   - 제목 계층을 보존한다. 주석은 내용을 채운 뒤 삭제해도 되지만, 여전히 명확한 지침 역할을 한다면 남긴다.
   - 각 원칙 섹션이 다음을 갖추도록 한다: 간결한 이름 줄, 타협할 수 없는(non‑negotiable) 규칙을 담은 단락(또는 글머리표 목록), 자명하지 않은 경우 명시적 근거.
   - 거버넌스 섹션에 개정 절차, 버전 관리 정책, 준수 검토 기대 사항이 나열되도록 한다.

4. 갱신 후 constitution 파일 맨 위에 HTML 주석으로 Sync Impact Report를 작성한다.
   이 보고서는 개정 내용을 사람이 검토하기 위한 임시 작업 자료이며 거버넌스 내용이
   아니다. 개정된 constitution 파일을 커밋하기 전에 삭제하는 것을 전제로 한다.
   - 버전 변경: old → new
   - 수정된 원칙 목록(이름이 바뀐 경우 old title → new title)
   - 추가된 섹션
   - 삭제된 섹션
   - 의도적으로 보류한 플레이스홀더가 있으면 후속 TODO.

5. 최종 출력 전 검증:
   - 설명되지 않은 대괄호 토큰이 남아 있지 않다.
   - 버전 줄이 보고서와 일치한다.
   - 날짜는 ISO 형식 YYYY-MM-DD다.
   - 원칙은 선언적이고 테스트 가능하며 모호한 표현이 없다(적절한 경우 "should" → MUST/SHOULD와 근거로 바꾼다).

6. 완성된 constitution을 `.specify/memory/constitution.md`에 다시 쓴다(덮어쓰기).

7. 다음 내용을 담은 최종 요약을 사용자에게 출력한다.
   - 새 버전과 버전 증가 근거.
   - 수동 후속 조치가 필요한 TODO 플레이스홀더나 보류 항목.
   - 제안 커밋 메시지(예: `docs: amend constitution to vX.Y.Z (principle additions + governance update)`).
   - 보류된 거버넌스 무관 의도에 대한 `Next Actions` 섹션.

서식 및 스타일 요구 사항:

- Markdown 제목은 템플릿과 똑같이 사용한다(수준을 낮추거나 높이지 않는다).
- 가독성을 위해 긴 근거 문장은 줄 바꿈한다(가능하면 100자 미만). 단, 어색하게 끊어 가며 억지로 맞추지는 않는다.
- 섹션 사이에는 빈 줄을 하나만 둔다.
- 줄 끝 공백을 남기지 않는다.

사용자가 부분 갱신만 제공하더라도(예: 원칙 하나만 수정) 검증과 버전 결정 단계는 그대로 수행한다.

핵심 정보가 없으면(예: 최초 채택일(RATIFICATION_DATE)을 정말 알 수 없는 경우) `TODO(<FIELD_NAME>): explanation`을 삽입하고, Sync Impact Report의 보류 항목에 포함한다.

`.specify/memory/constitution.md`에만 쓴다. 템플릿 원본 파일은 생성하거나 수정하지 않는다.

## 실행 후 확인

**extension hook 확인(constitution 갱신 후)**:
프로젝트 루트에 `.specify/extensions.yml`이 있는지 확인한다.
- 파일이 있으면 읽고 `hooks.after_constitution` 키 아래의 항목을 찾는다.
- YAML을 파싱할 수 없거나 유효하지 않으면 조용히 건너뛰지 않는다. `.specify/extensions.yml`을 읽을 수 없었다는 사실(파서 오류 포함)과, 거기에 등록된 필수(`optional: false`) hook을 포함해 어떤 hook도 확인하지 못했다는 사실을 사용자에게 알린 뒤 정상적으로 계속 진행한다.
- `enabled`가 명시적으로 `false`인 hook은 제외한다. `enabled` 필드가 없는 hook은 기본적으로 활성화된 것으로 간주한다.
- 남은 각 hook에 대해 hook의 `condition` 표현식을 해석하거나 평가하려고 시도하지 **않는다**.
  - hook에 `condition` 필드가 없거나 null/빈 값이면 실행 가능한 hook으로 간주한다.
  - hook에 비어 있지 않은 `condition`이 정의되어 있으면 해당 hook을 건너뛰고, condition 평가는 HookExecutor 구현에 맡긴다.
- hook 명령 이름으로 명령 호출을 구성할 때는 점(`.`)을 하이픈(`-`)으로 바꾼다. 예: `speckit.git.commit` → `/speckit-git-commit`.
- 실행 가능한 각 hook에 대해 `optional` 플래그에 따라 다음을 출력한다.
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
    위 블록을 출력한 뒤에는 hook을 실제로 호출하고(MUST), 끝날 때까지 기다린 다음 계속 진행해야 한다. 이 에이전트/세션에서 해당 명령을 직접 실행할 때와 같은 방식으로 실행한다(호출 방식은 위에 표시된 리터럴 `{command}` id와 다를 수 있다. 예를 들어 skills 모드 에이전트는 `/skill:speckit-...` 또는 `$speckit-...` 형태로 실행한다). 블록을 출력하는 것만으로는 hook이 실행되지 않는다.
- 등록된 hook이 없거나 `.specify/extensions.yml`이 없으면 조용히 건너뛴다.
