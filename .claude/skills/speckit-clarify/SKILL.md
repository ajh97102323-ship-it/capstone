---
name: "speckit-clarify"
description: "현재 기능 spec에서 명세가 부족한 부분을 찾아 최대 5개의 핵심 명확화 질문을 하고, 답변을 spec에 다시 반영한다."
argument-hint: "spec에서 명확히 할 영역(선택 사항)"
compatibility: "Requires spec-kit project structure with .specify/ directory"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/clarify.md"
user-invocable: true
disable-model-invocation: false
---


## 사용자 입력

```text
$ARGUMENTS
```

진행하기 전에 사용자 입력을 반드시 고려해야 한다(**MUST**, 입력이 비어 있지 않은 경우).

## 실행 전 확인

**extension hook 확인(명확화 전)**:
- 프로젝트 루트에 `.specify/extensions.yml`이 있는지 확인한다.
- 파일이 있으면 읽고 `hooks.before_clarify` 키 아래의 항목을 찾는다.
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

목표: 현재 기능 명세의 모호한 부분이나 누락된 결정 사항을 찾아 줄이고, 명확화 내용을 spec 파일에 직접 기록한다.

참고: 이 명확화 워크플로는 `/speckit-plan`을 호출하기 전에 실행(및 완료)하는 것을 전제로 한다. 사용자가 명확화를 건너뛴다고 명시적으로 밝히면(예: 탐색용 spike) 진행해도 되지만, 이후 단계에서 재작업 위험이 커진다고 반드시 경고해야 한다.

실행 단계:

1. 저장소 루트에서 `.specify/scripts/powershell/check-prerequisites.ps1 -Json -PathsOnly`를 **한 번** 실행한다(`--json --paths-only` 결합 모드 / `-Json -PathsOnly`). 최소한의 JSON 페이로드 필드를 파싱한다.
   - `FEATURE_DIR`
   - `FEATURE_SPEC`
   - (이후 연쇄 흐름을 위해 `IMPL_PLAN`, `TASKS`도 선택적으로 확보한다.)
   - JSON 파싱에 실패하면 중단하고, 사용자에게 `/speckit-specify`를 다시 실행하거나 기능 branch 환경을 확인하라고 안내한다.
   - "I'm Groot"처럼 인자에 작은따옴표가 들어가면 이스케이프 구문을 사용한다. 예: 'I'\''m Groot' (가능하면 큰따옴표 사용: "I'm Groot").

2. **존재하는 경우**: 프로젝트 원칙과 거버넌스 제약을 확인하기 위해 `.specify/memory/constitution.md`를 불러온다.

3. 현재 spec 파일을 불러온다. 아래 분류 체계에 따라 구조화된 모호성·커버리지 스캔을 수행한다. 각 범주의 상태를 Clear / Partial / Missing으로 표시한다. 우선순위를 정하는 데 쓸 내부 커버리지 맵을 만든다(질문을 하나도 하지 않을 경우가 아니면 원본 맵을 출력하지 않는다).

   기능 범위와 동작:
   - 핵심 사용자 목표와 success criteria
   - 범위 밖 항목의 명시적 선언
   - 사용자 역할/페르소나 구분

   도메인과 데이터 모델:
   - 엔터티, 속성, 관계
   - 식별성과 고유성 규칙
   - 생명주기/상태 전이
   - 데이터 양/규모 가정

   상호작용과 UX 흐름:
   - 핵심 사용자 여정/순서
   - 오류/빈 상태/로딩 상태
   - 접근성 또는 현지화 관련 사항

   비기능 품질 속성:
   - 성능(지연 시간, 처리량 목표)
   - 확장성(수평/수직, 한계)
   - 신뢰성과 가용성(가동 시간, 복구 기대치)
   - 관측성(로깅, 메트릭, 추적 신호)
   - 보안과 개인정보(인증/인가, 데이터 보호, 위협 가정)
   - 컴플라이언스/규제 제약(있는 경우)

   통합과 외부 의존성:
   - 외부 서비스/API와 장애 유형
   - 데이터 가져오기/내보내기 형식
   - 프로토콜/버전 관리 가정

   엣지 케이스와 장애 처리:
   - 부정 시나리오
   - 속도 제한/스로틀링
   - 충돌 해결(예: 동시 편집)

   제약과 트레이드오프:
   - 기술적 제약(언어, 스토리지, 호스팅)
   - 명시적 트레이드오프 또는 기각된 대안

   용어와 일관성:
   - 표준 용어집 용어
   - 피해야 할 동의어/폐기된 용어

   완료 신호:
   - 인수 기준의 테스트 가능성
   - 측정 가능한 완료 정의(Definition of Done) 형태의 지표

   기타/플레이스홀더:
   - TODO 표시/미해결 결정
   - 정량화되지 않은 모호한 형용사("robust", "intuitive")

   상태가 Partial 또는 Missing인 각 범주에 대해 후보 질문 기회를 추가한다. 단, 다음의 경우는 제외한다.
   - 명확화해도 구현이나 검증 전략이 실질적으로 달라지지 않는 경우
   - 항목이 구체적으로 구현 방법, 기술 스택 비교, 작업 분해에 관한 것인 경우(내부적으로 기록해 둔다)

4. 우선순위가 매겨진 후보 명확화 질문 대기열을 (내부적으로) 생성한다(최대 5개). 한꺼번에 모두 출력하지 **않는다**. 다음 제약을 적용한다.
    - 세션 전체에서 질문은 총 5개를 넘지 않는다.
    - 각 질문은 다음 중 하나로 답할 수 있어야 한다.
       - 짧은 객관식 선택(서로 배타적인 2~5개의 선택지), 또는
       - 한 단어/짧은 구 답변(명시적으로 제한한다: "Answer in <=5 words").
    - 답변이 아키텍처, 데이터 모델링, 작업 분해, 테스트 설계, UX 동작, 운영 준비도, 컴플라이언스 검증에 실질적인 영향을 주는 질문만 포함한다.
    - 범주별 커버리지 균형을 맞춘다. 영향이 가장 큰 미해결 범주부터 다루도록 하고, 영향이 큰 영역(예: 보안 태세) 하나가 미해결인데 영향이 작은 질문 두 개를 하지 않는다.
    - 이미 답이 있는 질문, 사소한 스타일 선호, plan 수준의 실행 세부 사항(정확성을 막는 경우가 아니라면)은 제외한다.
    - 이후 단계의 재작업 위험을 줄이거나 어긋난 인수 테스트를 막는 명확화를 우선한다.
    - 미해결 범주가 5개보다 많으면 (영향도 * 불확실성) 휴리스틱으로 상위 5개를 고른다.

5. 순차 질문 루프(대화형):
    - 한 번에 **정확히 하나**의 질문만 제시한다.
    - **질문 작성 품질(객관식이든 단답형이든 모든 질문에 적용):**
       - `**Question:**`으로 시작하고 그 뒤에 `?`로 끝나는 완전한 의문문을 쓴다. `?` 앞의 질문 문장은 그것만으로 의미가 통해야 한다.
       - 주제 라벨, 섹션 제목, 요구사항 id를 질문 자체로 쓰지 **않는다**. 예를 들어 `Acceptance device/runtime matrix (FR-023)`은 질문이 아니라 라벨이므로 잘못된(INVALID) 예다.
       - `?` 뒤에 허용되는 것은 괄호로 감싼 요구사항/질문 id(선택 사항)뿐이다. 정확한 형식: `**Question:** <interrogative>?` 또는 `**Question:** <interrogative>? (FR-023)`. id를 `?` 앞에 두지 말고, id만(또는 주제 라벨과 함께) 질문 전체로 쓰지 않는다.
       - 질문 줄 바로 다음, 권장안/선택지 앞에 쉬운 말로 된 "Why it matters" 문장 하나(인수나 출시에 걸린 이해관계)를 추가한다.
       - 일상적인 표현을 쓴다. 전문 용어는 같은 문장에서 정의할 때만 사용한다. 자가 점검: Spec Kit을 모르는 사람도 질문 줄만 보고 답할 수 있어야 한다. 간결한 것은 괜찮지만 알아보기 힘든 라벨은 안 된다.
    - 객관식 질문의 경우:
       - **모든 선택지를 분석**하고 다음을 근거로 **가장 적합한 선택지**를 정한다.
          - 해당 프로젝트 유형의 모범 사례
          - 유사한 구현에서 흔히 쓰이는 패턴
          - 위험 감소(보안, 성능, 유지보수성)
          - spec에서 드러난 명시적 프로젝트 목표나 제약과의 정합성
       - **권장 선택지**를 맨 위에 눈에 띄게 제시하고 명확한 근거(왜 이것이 최선인지 설명하는 1~2문장)를 덧붙인다.
       - 형식: `**Recommended:** Option [X] - <reasoning>`
       - 그다음 모든 선택지를 Markdown 표로 렌더링한다.

       | Option | Description |
       |--------|-------------|
       | A | <Option A description> |
       | B | <Option B description> |
       | C | <Option C description> (add D/E as needed up to 5) |
       | Short | Provide a different short answer (<=5 words) (Include only if free-form alternative is appropriate) |

       - 표 다음에 다음 문구를 추가한다: `You can reply with the option letter (e.g., "A"), accept the recommendation by saying "yes" or "recommended", or provide your own short answer.`
    - 단답형(의미 있는 개별 선택지가 없는 경우):
       - 모범 사례와 맥락을 바탕으로 **제안 답변**을 제시한다.
       - 형식: `**Suggested:** <your proposed answer> - <brief reasoning>`
       - 그다음 출력한다: `Format: Short answer (<=5 words). You can accept the suggestion by saying "yes" or "suggested", or provide your own answer.`
    - 사용자가 답한 뒤:
       - 사용자가 "yes", "recommended", "suggested"로 답하면 앞서 제시한 권장안/제안을 답변으로 사용한다.
       - 그렇지 않으면 답변이 하나의 선택지에 대응하는지, 또는 5단어 이하 제약에 맞는지 검증한다.
       - 모호하면 빠르게 다시 확인한다(같은 질문으로 계속 집계하며 다음 질문으로 넘어가지 않는다).
       - 만족스러운 답을 얻으면 작업 메모리에 기록하고(아직 디스크에 쓰지 않는다) 대기열의 다음 질문으로 넘어간다.
    - 다음 경우에 질문을 멈춘다.
       - 모든 핵심 모호성이 일찍 해소된 경우(남은 대기열 항목이 불필요해짐), 또는
       - 사용자가 완료 신호를 보낸 경우("done", "good", "no more"), 또는
       - 질문을 5개 한 경우.
    - 대기열에 있는 이후 질문을 미리 드러내지 않는다.
    - 시작 시점에 유효한 질문이 하나도 없으면 핵심 모호성이 없다고 즉시 보고한다.

6. 답변이 하나 수락될 **때마다** 통합한다(점진적 업데이트 방식).
    - spec의 메모리 내 표현(시작할 때 한 번 불러옴)과 원본 파일 내용을 함께 유지한다.
    - 이 세션에서 처음 통합하는 답변의 경우:
       - `## Clarifications` 섹션이 있는지 확인한다(없으면 spec 템플릿 기준으로 최상위 맥락/개요 섹션 바로 다음에 만든다).
       - 그 아래에 오늘 날짜의 `### Session YYYY-MM-DD` 하위 제목을 만든다(없는 경우).
    - 수락 직후 글머리표 줄을 추가한다: `- Q: <question> → A: <final answer>`.
    - 그런 다음 즉시 가장 적절한 섹션에 명확화 내용을 반영한다.
       - 기능 모호성 → Functional Requirements의 글머리표를 수정하거나 추가한다.
       - 사용자 상호작용/행위자 구분 → User Stories 또는 Actors 하위 섹션(있는 경우)에 명확해진 역할, 제약, 시나리오를 반영한다.
       - 데이터 형태/엔터티 → Data Model을 수정한다(필드, 타입, 관계 추가). 순서를 유지하고, 추가된 제약은 간결하게 적는다.
       - 비기능 제약 → Success Criteria > Measurable Outcomes에 측정 가능한 기준을 추가/수정한다(모호한 형용사를 메트릭이나 명시적 목표치로 바꾼다).
       - 엣지 케이스/부정 흐름 → Edge Cases / Error Handling 아래에 새 글머리표를 추가한다(템플릿에 해당 플레이스홀더가 있으면 그 하위 섹션을 만든다).
       - 용어 충돌 → spec 전체에서 용어를 통일한다. 꼭 필요할 때만 `(formerly referred to as "X")`를 한 번 덧붙여 원래 용어를 남긴다.
    - 명확화로 인해 앞서 있던 모호한 문장이 무효가 되면 중복으로 남기지 말고 그 문장을 교체한다. 낡고 모순되는 문장을 남기지 않는다.
    - 컨텍스트 손실 위험을 줄이기 위해 통합할 때마다 spec 파일을 저장한다(원자적 덮어쓰기).
    - 서식을 보존한다. 관련 없는 섹션의 순서를 바꾸지 말고 제목 계층을 그대로 유지한다.
    - 삽입하는 각 명확화는 최소한으로, 테스트 가능하게 유지한다(서술이 장황해지지 않게 한다).

7. 검증(쓰기를 할 **때마다**, 그리고 마지막에 한 번 더 수행):
   - Clarifications 세션에는 수락된 답변마다 정확히 하나의 글머리표가 있다(중복 없음).
   - 질문한(수락된) 질문은 총 5개 이하다.
   - 수정된 섹션에 새 답변이 해소하려던 모호한 플레이스홀더가 남아 있지 않다.
   - 모순되는 이전 문장이 남아 있지 않다(이제 무효가 된 대안 선택지가 제거되었는지 스캔한다).
   - Markdown 구조가 유효하다. 새로 추가할 수 있는 제목은 `## Clarifications`, `### Session YYYY-MM-DD`뿐이다.
   - 용어 일관성: 수정된 모든 섹션에서 같은 표준 용어를 사용한다.

8. 수정된 spec을 `FEATURE_SPEC`에 다시 쓴다.

9. **Spec 품질 checklist 재검증**(있는 경우):
   - `FEATURE_DIR/checklists/requirements.md`가 있는지 확인한다.
   - 없으면 이 단계를 조용히 건너뛴다.
   - 있으면:
     1. checklist 파일을 읽는다.
     2. 코드 펜스 밖에 있는 GitHub 작업 목록 체크박스 줄을 모두 찾는다. 즉 `- [ ]`, `- [x]`, `- [X]`에 해당하는 줄이다(대소문자 구분 없음, 중첩 항목을 위한 앞쪽 공백 허용). 그 밖의 내용(제목, 메모, 체크박스가 아닌 글머리표, 메타데이터)은 모두 무시한다.
     3. 각 체크박스 줄의 현재 표시 상태(체크됨 또는 체크 안 됨)와 항목 텍스트를 변경 전 스냅샷 목록에 기록한다.
     4. 각 체크박스 항목을 **수정된** spec(7단계에서 방금 저장한 버전) 기준으로 다시 평가한다.
     5. 각 체크박스 항목은 체크 상태가 실제로 바뀌는 경우에만 수정한다.
        - 항목이 이제 통과하는데 체크되어 있지 않았다면: `[ ]`를 `[x]`로 바꾼다.
        - 항목이 이제 실패하는데 체크되어 있었다면: `[x]`/`[X]`를 `[ ]`로 바꾼다.
        - 상태가 그대로면: 표시를 그대로 둔다(외형상의 diff를 피하기 위해 기존 대소문자를 유지한다).
     6. 수정된 checklist 파일을 저장한다. **상태가 바뀐 체크박스 줄의 `[ ]`/`[x]` 표시 부분만 토글한다.** 불필요한 diff를 피하기 위해 그 밖의 모든 파일 내용(제목, 메타데이터, 메모, 줄 순서, 공백)은 그대로 유지해야 한다.
     7. 변경 전 스냅샷과 현재 상태를 비교해 완료 보고에 쓸 세 가지 목록을 계산한다.
        - **새로 통과**: 체크 안 됨에서 체크됨으로 바뀐 항목.
        - **회귀**: 체크됨에서 체크 안 됨으로 바뀐 항목.
        - **여전히 미체크**: 계속 체크되지 않은 항목.
     8. 변경 전/후 통과 수를 체크된 항목 수/전체 체크박스 항목 수로 기록한다(예: "12/16 → 15/16 items passing").

동작 규칙:

- 의미 있는 모호성을 찾지 못하면(또는 가능한 질문이 모두 영향이 작으면) "No critical ambiguities detected worth formal clarification."라고 응답하고 다음 단계로 진행할 것을 제안한다.
- spec 파일이 없으면 사용자에게 먼저 `/speckit-specify`를 실행하라고 안내한다(여기서 새 spec을 만들지 않는다).
- 질문은 총 5개를 절대 넘지 않는다(한 질문에 대한 재확인은 새 질문으로 세지 않는다).
- 기능의 명확성을 가로막는 경우가 아니면 추측성 기술 스택 질문은 피한다.
- 사용자의 조기 종료 신호("stop", "done", "proceed")를 존중한다.
- 커버리지가 충분해 질문을 하지 않았다면 간결한 커버리지 요약(모든 범주 Clear)을 출력한 뒤 다음 단계로 넘어갈 것을 제안한다.
- 질문 한도에 도달했는데 영향이 큰 미해결 범주가 남아 있으면 Deferred 아래에 근거와 함께 명시적으로 표시한다.

우선순위 판단을 위한 맥락: $ARGUMENTS

## 필수 실행 후 hook

**사용자에게 완료를 보고하기 전에 이 섹션을 반드시 완료해야 한다(MUST).**

프로젝트 루트에 `.specify/extensions.yml`이 있는지 확인한다.
- 파일이 없거나 `hooks.after_clarify` 아래에 등록된 hook이 없으면 완료 보고로 건너뛴다.
- 파일이 있으면 읽고 `hooks.after_clarify` 키 아래의 항목을 찾는다.
- YAML을 파싱할 수 없거나 유효하지 않으면 조용히 건너뛰지 않는다. `.specify/extensions.yml`을 읽을 수 없었다는 사실(파서 오류 포함)과, 거기에 등록된 필수(`optional: false`) hook을 포함해 어떤 hook도 확인하지 못했다는 사실을 사용자에게 알린 뒤 완료 보고로 넘어간다.
- `enabled`가 명시적으로 `false`인 hook은 제외한다. `enabled` 필드가 없는 hook은 기본적으로 활성화된 것으로 간주한다.
- 남은 각 hook에 대해 hook의 `condition` 표현식을 해석하거나 평가하려고 시도하지 **않는다**.
  - hook에 `condition` 필드가 없거나 null/빈 값이면 실행 가능한 hook으로 간주한다.
  - hook에 비어 있지 않은 `condition`이 정의되어 있으면 해당 hook을 건너뛰고, condition 평가는 HookExecutor 구현에 맡긴다.
- hook 명령 이름으로 명령 호출을 구성할 때는 점(`.`)을 하이픈(`-`)으로 바꾼다. 예: `speckit.git.commit` → `/speckit-git-commit`.
- 실행 가능한 각 hook에 대해 `optional` 플래그에 따라 다음을 출력한다.
  - **필수 hook** (`optional: false`) — **각 필수 hook마다 `EXECUTE_COMMAND:`를 반드시 출력해야 한다(MUST)**:
    ```
    ## Extension Hooks

    **Automatic Hook**: {extension}
    Executing: `/{command}`
    EXECUTE_COMMAND: {command}
    ```
    위 블록을 출력한 뒤에는 hook을 실제로 호출하고(MUST), 끝날 때까지 기다린 다음 계속 진행해야 한다. 이 에이전트/세션에서 해당 명령을 직접 실행할 때와 같은 방식으로 실행한다(호출 방식은 위에 표시된 리터럴 `{command}` id와 다를 수 있다. 예를 들어 skills 모드 에이전트는 `/skill:speckit-...` 또는 `$speckit-...` 형태로 실행한다). 블록을 출력하는 것만으로는 hook이 실행되지 않는다.
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

완료를 보고한다(질문 루프가 끝났거나 조기 종료된 뒤):
- 질문하고 답을 받은 질문 수.
- 수정된 spec의 경로.
- 수정한 섹션(이름 목록).
- Spec 품질 checklist 상태(`FEATURE_DIR/checklists/requirements.md`를 재검증한 경우): 변경 전/후 통과 수를 보여 주고(예: "Spec Quality Checklist: 12/16 → 15/16 items passing"), 상태가 바뀐 항목을 모두 나열한다. 새로 체크된 항목(체크 안 됨 → 체크됨)과 회귀 항목(체크됨 → 체크 안 됨)을 모두 포함한다. 체크되지 않은 항목이 남아 있으면 주의가 필요한 영역으로 나열한다.
- 분류 체계의 각 범주와 상태를 나열한 커버리지 요약 표. 상태는 Resolved(Partial/Missing이었다가 해결됨), Deferred(질문 한도를 초과했거나, 남은 항목이 구체적으로 구현 방법·기술 스택 비교·작업 분해에 관한 것), Clear(이미 충분함), Outstanding(여전히 Partial/Missing이지만 영향이 작음) 중 하나다.
- Outstanding 또는 Deferred가 남아 있으면 `/speckit-plan`으로 진행할지, plan 이후에 `/speckit-clarify`를 다시 실행할지 권장한다.
- 다음에 실행할 명령 제안.

## 완료 조건

- [ ] spec의 모호성을 찾아내고 명확화 내용을 spec 파일에 통합했다
- [ ] 수정된 spec 기준으로 spec 품질 checklist를 재검증했다(`FEATURE_DIR/checklists/requirements.md`가 있는 경우)
- [ ] 위의 필수 실행 후 hook 규칙에 따라 extension hook을 실행하거나 건너뛰었다
- [ ] 답변받은 질문, 수정한 섹션, checklist 상태, 커버리지 요약을 포함해 사용자에게 완료를 보고했다
