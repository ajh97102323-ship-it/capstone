---
name: "speckit-checklist"
description: "사용자 요구에 따라 현재 기능에 맞는 맞춤 checklist를 생성한다."
argument-hint: "checklist의 도메인 또는 중점 영역"
compatibility: "Requires spec-kit project structure with .specify/ directory"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/checklist.md"
user-invocable: true
disable-model-invocation: false
---


## Checklist의 목적: "Unit Tests for English"(자연어 요구사항을 위한 단위 테스트)

**핵심 개념(CRITICAL CONCEPT)**: checklist는 **요구사항 작성에 대한 단위 테스트**다. 특정 도메인에서 요구사항의 품질, 명확성, 완전성을 검증한다.

**검증(verification)·테스트 용도가 아니다**:

- ❌ "버튼이 제대로 클릭되는지 확인한다"가 아니다
- ❌ "오류 처리가 동작하는지 테스트한다"가 아니다
- ❌ "API가 200을 반환하는지 확인한다"가 아니다
- ❌ 코드·구현이 spec과 일치하는지 점검하는 것이 아니다

**요구사항 품질 검증 용도다**:

- ✅ "모든 카드 유형에 대해 시각적 계층 요구사항이 정의되어 있는가?" (완전성)
- ✅ "'눈에 띄는 표시'가 구체적인 크기·위치로 정량화되어 있는가?" (명확성)
- ✅ "hover 상태 요구사항이 모든 상호작용 요소에서 일관적인가?" (일관성)
- ✅ "키보드 탐색에 대한 접근성 요구사항이 정의되어 있는가?" (범위)
- ✅ "로고 이미지 로드에 실패했을 때 어떻게 되는지 spec이 정의하는가?" (엣지 케이스)

**비유**: spec이 영어(자연어)로 쓴 코드라면 checklist는 그 코드의 단위 테스트 스위트다. 구현이 동작하는지가 아니라 요구사항이 잘 쓰였는지, 완전한지, 모호하지 않은지, 구현할 준비가 되었는지를 테스트한다.

**소유권과 체크박스 수명 주기**:

- 이 명령이 생성하는 맞춤 checklist는 리뷰어가 소유하는 요구사항 품질 리뷰 산출물이다.
- `[x]`는 리뷰어가 해당 요구사항 품질 기준이 충족되었다고 판단했다는 뜻이다.
- `[x]`는 구현 작업이 완료되었다는 뜻이 아니다(does NOT).
- 이 명령은 checklist 항목을 생성하거나 덧붙인다. 생성한 항목을 `[x]`로 표시해서는 안 된다(MUST NOT).
- agent는 리뷰어가 명시적으로 요청했을 때에만 항목 평가를 도울 수 있다.
- `checklists/requirements.md`는 `/speckit-specify`와 `/speckit-clarify`가 관리하는 별도의 내장 spec 품질 checklist다. 그 예외를 여기서 생성하는 맞춤 checklist에 적용하지 않는다.

## 사용자 입력

```text
$ARGUMENTS
```

진행하기 전에 사용자 입력(비어 있지 않다면)을 반드시 고려해야 한다(**MUST**).

## 실행 전 점검

**extension hook 확인(checklist 생성 전)**:
- 프로젝트 루트에 `.specify/extensions.yml`이 있는지 확인한다.
- 있으면 읽고 `hooks.before_checklist` 키 아래의 항목을 찾는다
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

    Wait for the result of the hook command before proceeding to the Execution Steps.
    ```
    위 블록을 출력한 뒤에는 반드시(MUST) hook을 실제로 호출하고, 끝날 때까지 기다린 다음 계속 진행한다. 이 agent/세션에서 직접 명령을 실행할 때와 같은 방식으로 실행한다(호출 방식은 위에 표시된 리터럴 `{command}` id와 다를 수 있다. 예를 들어 skills 모드 agent는 `/skill:speckit-...` 또는 `$speckit-...`로 실행한다). 블록을 출력하는 것만으로는 hook이 실행되지 않는다.
- 등록된 hook이 없거나 `.specify/extensions.yml`이 없으면 조용히 건너뛴다

## 실행 단계 (Execution Steps)

1. **준비**: repo 루트에서 `.specify/scripts/powershell/check-prerequisites.ps1 -Json -Template checklist-template`을 실행하고 JSON을 파싱해 FEATURE_DIR, AVAILABLE_DOCS 목록, TEMPLATE_CONTENT를 얻는다.
   - 모든 파일 경로는 절대 경로여야 한다.
   - "I'm Groot"처럼 인자에 작은따옴표가 있으면 이스케이프 구문을 쓴다. 예: 'I'\''m Groot' (가능하면 큰따옴표: "I'm Groot").

2. **있다면(IF EXISTS)**: 프로젝트 원칙과 거버넌스 제약을 파악하기 위해 `.specify/memory/constitution.md`를 불러온다.

3. **의도 명확화(동적)**: 맥락에 맞는 초기 명확화 질문을 최대 세 개까지 도출한다(미리 만들어 둔 목록은 쓰지 않는다). 질문은 반드시(MUST) 다음을 지킨다:
   - 사용자의 표현 + spec/plan/tasks에서 추출한 신호를 바탕으로 생성한다
   - checklist 내용을 실질적으로 바꾸는 정보만 묻는다
   - 답이 `$ARGUMENTS`에 이미 분명히 나와 있는 질문은 개별적으로 생략한다
   - 범위보다 정밀성을 우선한다

   생성 알고리즘:
   1. 신호 추출: 기능 도메인 키워드(예: 인증, 지연 시간, UX, API), 위험 지표("critical", "must", "compliance"), 이해관계자 힌트("QA", "review", "security team"), 명시적 산출물("a11y", "rollback", "contracts").
   2. 신호를 후보 중점 영역(최대 4개)으로 묶고 관련도순으로 정렬한다.
   3. 명시되지 않았다면 예상 대상과 시점(작성자, 리뷰어, QA, 릴리스)을 파악한다.
   4. 빠진 차원 탐지: 범위의 폭, 깊이·엄격도, 위험 강조점, 제외 경계, 측정 가능한 인수 기준.
   5. 다음 유형 중에서 골라 질문을 구성한다:
      - 범위 구체화(예: "X, Y와의 통합 접점까지 포함해야 하나요, 아니면 로컬 모듈의 정확성으로 한정해야 하나요?")
      - 위험 우선순위(예: "다음 잠재 위험 영역 중 어떤 것에 필수 게이트 점검을 적용해야 하나요?")
      - 깊이 조정(예: "가벼운 커밋 전 점검 목록인가요, 공식 릴리스 게이트인가요?")
      - 대상 설정(예: "작성자 혼자 쓰나요, PR 리뷰 중 동료도 쓰나요?")
      - 경계 제외(예: "이번에는 성능 튜닝 항목을 명시적으로 제외할까요?")
      - 시나리오 유형 공백(예: "복구 흐름이 발견되지 않았습니다. 롤백·부분 실패 경로도 범위에 포함되나요?")

   질문 형식 규칙:
   - 선택지를 제시할 때는 다음 열로 된 간결한 표를 만든다: Option | Candidate | Why It Matters
   - 선택지는 최대 A–E로 제한한다. 자유 응답이 더 명확하면 표를 생략한다
   - 사용자가 이미 말한 내용을 다시 말하게 하지 않는다
   - 추측성 범주를 만들지 않는다(환각 금지). 확실하지 않으면 명시적으로 묻는다: "X가 범위에 포함되는지 확인해 주세요."

   상호작용이 불가능할 때의 기본값:
   - 깊이: Standard
   - 대상: 코드 관련이면 Reviewer (PR), 그 외에는 Author
   - 중점: 관련도 상위 2개 클러스터

   질문을 출력한다(Q1/Q2/Q3로 표시). 답변을 받은 뒤 시나리오 유형(Alternate / Exception / Recovery / Non-Functional 도메인) 중 2개 이상이 여전히 불명확하면, 각각 한 줄 근거(예: "복구 경로 위험 미해결")를 붙여 겨냥한 후속 질문을 최대 두 개(Q4/Q5)까지 더 할 수 있다(MAY). 질문은 총 다섯 개를 넘지 않는다. 사용자가 추가 질문을 명시적으로 거절하면 더 묻지 않는다.

4. **사용자 요청 이해**: `$ARGUMENTS` + 명확화 답변을 결합한다:
   - checklist 주제를 도출한다(예: security, review, deploy, ux)
   - 사용자가 언급한 명시적 필수 항목을 정리한다
   - 선택된 중점 영역을 범주 골격에 대응시킨다
   - 빠진 맥락은 spec/plan/tasks에서 추론한다(환각하지 않는다(do NOT))

5. **기능 맥락 불러오기**: FEATURE_DIR에서 읽는다:
   - spec.md: 기능 요구사항과 범위
   - plan.md(있다면): 기술 세부 사항, 의존성
   - tasks.md(있다면): 구현 작업

   **맥락 로딩 전략**:
   - 활성 중점 영역과 관련된 필요한 부분만 불러온다(파일 전체를 쏟아붓지 않는다)
   - 긴 섹션은 간결한 시나리오·요구사항 bullet로 요약하는 것을 우선한다
   - 점진적 공개를 쓴다: 공백이 발견될 때에만 추가로 조회한다
   - 원본 문서가 크면 원문을 그대로 넣지 말고 중간 요약 항목을 만든다

6. **checklist 생성** - TEMPLATE_CONTENT를 구조 템플릿으로 삼아 "요구사항을 위한 단위 테스트"를 만든다:
   - `FEATURE_DIR/checklists/` 디렉터리가 없으면 만든다
   - 고유한 checklist 파일 이름을 정한다:
     - 도메인을 기준으로 짧고 설명적인 이름을 쓴다(예: `ux.md`, `api.md`, `security.md`)
     - 형식: `[domain].md`
   - 파일 처리 방식:
     - 파일이 없으면: 새 파일을 만들고 항목 번호를 CHK001부터 매긴다
     - 파일이 있으면: 기존 파일에 새 항목을 덧붙이고, 마지막 CHK ID에서 이어서 번호를 매긴다(예: 마지막 항목이 CHK015면 새 항목은 CHK016부터 시작)
   - 기존 checklist 내용은 절대 삭제하거나 교체하지 않는다. 항상 보존하고 덧붙인다
   - 새로 생성한 항목은 모두 체크하지 않은 상태(`[ ]`)로 둔다. 체크박스 상태는 리뷰어의 몫이다

   **핵심 원칙 - 구현이 아니라 요구사항을 테스트한다**:
   모든 checklist 항목은 반드시(MUST) 요구사항 자체를 다음 기준으로 평가한다:
   - **완전성(Completeness)**: 필요한 요구사항이 모두 있는가?
   - **명확성(Clarity)**: 요구사항이 모호하지 않고 구체적인가?
   - **일관성(Consistency)**: 요구사항끼리 서로 맞아떨어지는가?
   - **측정 가능성(Measurability)**: 요구사항을 객관적으로 검증할 수 있는가?
   - **범위(Coverage)**: 모든 시나리오·엣지 케이스를 다루는가?

   **범주 구조** - 요구사항 품질 차원별로 항목을 묶는다:
   - **Requirement Completeness** (필요한 요구사항이 모두 문서화되어 있는가?)
   - **Requirement Clarity** (요구사항이 구체적이고 모호하지 않은가?)
   - **Requirement Consistency** (요구사항이 충돌 없이 맞아떨어지는가?)
   - **Acceptance Criteria Quality** (success criteria가 측정 가능한가?)
   - **Scenario Coverage** (모든 흐름·사례를 다루는가?)
   - **Edge Case Coverage** (경계 조건이 정의되어 있는가?)
   - **Non-Functional Requirements** (성능, 보안, 접근성 등이 명시되어 있는가?)
   - **Dependencies & Assumptions** (문서화되고 검증되었는가?)
   - **Ambiguities & Conflicts** (무엇을 명확히 해야 하는가?)

   **checklist 항목 작성법 - "Unit Tests for English"**:

   ❌ **잘못된 예** (구현을 테스트함):
   - "랜딩 페이지에 에피소드 카드 3개가 표시되는지 확인한다"
   - "데스크톱에서 hover 상태가 동작하는지 테스트한다"
   - "로고를 클릭하면 홈으로 이동하는지 확인한다"

   ✅ **올바른 예** (요구사항 품질을 테스트함):
   - "추천 에피소드의 정확한 개수와 레이아웃이 명시되어 있는가?" [Completeness]
   - "'눈에 띄는 표시'가 구체적인 크기·위치로 정량화되어 있는가?" [Clarity]
   - "hover 상태 요구사항이 모든 상호작용 요소에서 일관적인가?" [Consistency]
   - "모든 상호작용 UI에 대해 키보드 탐색 요구사항이 정의되어 있는가?" [Coverage]
   - "로고 이미지 로드에 실패했을 때의 대체 동작이 명시되어 있는가?" [Edge Cases]
   - "비동기 에피소드 데이터에 대한 로딩 상태가 정의되어 있는가?" [Completeness]
   - "서로 경쟁하는 UI 요소의 시각적 계층을 spec이 정의하는가?" [Clarity]

   **항목 구조**:
   각 항목은 다음 패턴을 따른다:
   - 요구사항 품질을 묻는 질문 형식
   - spec/plan에 쓰여 있는(또는 쓰여 있지 않은) 내용에 초점
   - 품질 차원을 대괄호 안에 포함 [Completeness/Clarity/Consistency/etc.]
   - 기존 요구사항을 점검할 때는 spec 섹션 `[Spec §X.Y]`를 참조
   - 누락된 요구사항을 점검할 때는 `[Gap]` 표시를 사용

   **품질 차원별 예시**:

   완전성(Completeness):
   - "모든 API 실패 모드에 대해 오류 처리 요구사항이 정의되어 있는가? [Gap]"
   - "모든 상호작용 요소에 대해 접근성 요구사항이 명시되어 있는가? [Completeness]"
   - "반응형 레이아웃에 대한 모바일 breakpoint 요구사항이 정의되어 있는가? [Gap]"

   명확성(Clarity):
   - "'빠른 로딩'이 구체적인 시간 임계값으로 정량화되어 있는가? [Clarity, Spec §NFR-2]"
   - "'관련 에피소드'의 선정 기준이 명시적으로 정의되어 있는가? [Clarity, Spec §FR-5]"
   - "'눈에 띄는'이 측정 가능한 시각적 속성으로 정의되어 있는가? [Ambiguity, Spec §FR-4]"

   일관성(Consistency):
   - "탐색 요구사항이 모든 페이지에서 서로 맞아떨어지는가? [Consistency, Spec §FR-10]"
   - "카드 컴포넌트 요구사항이 랜딩 페이지와 상세 페이지 사이에서 일관적인가? [Consistency]"

   범위(Coverage):
   - "데이터가 없는 상태(에피소드 없음) 시나리오에 대한 요구사항이 정의되어 있는가? [Coverage, Edge Case]"
   - "사용자 동시 상호작용 시나리오를 다루는가? [Coverage, Gap]"
   - "데이터 일부만 로드에 실패하는 경우에 대한 요구사항이 명시되어 있는가? [Coverage, Exception Flow]"

   측정 가능성(Measurability):
   - "시각적 계층 요구사항이 측정·테스트 가능한가? [Acceptance Criteria, Spec §FR-1]"
   - "'균형 잡힌 시각적 무게'를 객관적으로 검증할 수 있는가? [Measurability, Spec §FR-2]"

   **시나리오 분류와 범위** (요구사항 품질 중심):
   - 다음 시나리오에 대한 요구사항이 있는지 점검한다: Primary, Alternate, Exception/Error, Recovery, Non-Functional
   - 각 시나리오 유형에 대해 묻는다: "[시나리오 유형] 요구사항이 완전하고 명확하며 일관적인가?"
   - 시나리오 유형이 빠져 있으면: "[시나리오 유형] 요구사항이 의도적으로 제외되었는가, 아니면 누락되었는가? [Gap]"
   - 상태 변경이 일어나는 경우 복원력·롤백을 포함한다: "마이그레이션 실패에 대한 롤백 요구사항이 정의되어 있는가? [Gap]"

   **추적성 요구사항**:
   - 최소 기준: 항목의 80% 이상은 반드시(MUST) 추적 참조를 하나 이상 포함한다
   - 각 항목은 spec 섹션 `[Spec §X.Y]`를 참조하거나 다음 표시를 사용한다: `[Gap]`, `[Ambiguity]`, `[Conflict]`, `[Assumption]`
   - ID 체계가 없으면: "요구사항과 인수 기준의 ID 체계가 마련되어 있는가? [Traceability]"

   **문제 드러내기와 해결** (요구사항 품질 문제):
   요구사항 자체에 대해 질문한다:
   - 모호성: "'빠르다'는 용어가 구체적인 지표로 정량화되어 있는가? [Ambiguity, Spec §NFR-1]"
   - 충돌: "§FR-10과 §FR-10a 사이에 탐색 요구사항이 충돌하는가? [Conflict]"
   - 가정: "'팟캐스트 API를 항상 사용할 수 있다'는 가정이 검증되었는가? [Assumption]"
   - 의존성: "외부 팟캐스트 API 요구사항이 문서화되어 있는가? [Dependency, Gap]"
   - 정의 누락: "'시각적 계층'이 측정 가능한 기준으로 정의되어 있는가? [Gap]"

   **내용 통합**:
   - 소프트 상한: 후보 항목이 40개를 넘으면 위험·영향도순으로 우선순위를 정한다
   - 같은 요구사항 측면을 점검하는 거의 중복된 항목은 합친다
   - 영향이 낮은 엣지 케이스가 5개를 넘으면 항목 하나로 만든다: "요구사항에서 엣지 케이스 X, Y, Z를 다루는가? [Coverage]"

   **🚫 절대 금지** - 다음은 항목을 요구사항 테스트가 아닌 구현 테스트로 만든다:
   - ❌ "Verify", "Test", "Confirm", "Check" + 구현 동작으로 시작하는 모든 항목 (한국어 항목이면 구현 동작을 "확인한다", "검증한다", "테스트한다", "점검한다"로 맺는 항목도 같다. 한국어는 동사가 문장 끝에 오므로 시작이 아니라 끝을 본다)
   - ❌ 코드 실행, 사용자 행동, 시스템 동작에 대한 언급
   - ❌ "Displays correctly", "works properly", "functions as expected"
   - ❌ "Click", "navigate", "render", "load", "execute" (한국어: "클릭", "이동", "렌더링", "로드", "실행")
   - ❌ 테스트 케이스, 테스트 계획, QA 절차
   - ❌ 구현 세부 사항(프레임워크, API, 알고리즘)

   **✅ 필수 패턴(REQUIRED PATTERNS)** - 다음은 요구사항 품질을 테스트한다:
   - ✅ "[시나리오]에 대해 [요구사항 유형]이 정의·명시·문서화되어 있는가?"
   - ✅ "[모호한 용어]가 구체적인 기준으로 정량화·명확화되어 있는가?"
   - ✅ "[섹션 A]와 [섹션 B] 사이에서 요구사항이 일관적인가?"
   - ✅ "[요구사항]을 객관적으로 측정·검증할 수 있는가?"
   - ✅ "요구사항에서 [엣지 케이스/시나리오]를 다루는가?"
   - ✅ "spec이 [누락된 측면]을 정의하는가?"

7. **구조 참조**: 제목, 메타 섹션, 범주 제목, 소유권 안내, 노트 섹션, ID 형식은 `.specify/templates/checklist-template.md`의 표준 템플릿을 따라 checklist를 생성한다. 템플릿을 쓸 수 없으면 다음을 사용한다: H1 제목, 목적·생성일 메타 줄, `[x]`가 리뷰어의 요구사항 품질 승인을 뜻한다고 설명하는 소유권 안내, CHK001부터 전역으로 증가하는 ID를 가진 `- [ ] CHK### <requirement item>` 줄을 담은 `##` 범주 섹션, 그리고 `/speckit-implement`가 checklist 상태를 읽기만 하고 표시를 수정하지 않는다는 노트.

8. **보고**: checklist 파일의 전체 경로와 항목 수를 출력하고, 이번 실행에서 새 파일을 만들었는지 기존 파일에 덧붙였는지 요약한다. 다음을 요약한다:
   - 선택한 중점 영역
   - 깊이 수준
   - 사용 주체·시점
   - 반영한 사용자 지정 필수 항목

**중요**: `/speckit-checklist` 명령은 호출할 때마다 짧고 설명적인 checklist 파일 이름을 쓰며, 새 파일을 만들거나 기존 파일에 덧붙인다. 이렇게 하면 다음이 가능하다:

- 서로 다른 유형의 여러 checklist(예: `ux.md`, `test.md`, `security.md`)
- checklist의 목적을 드러내는 단순하고 기억하기 쉬운 파일 이름
- `checklists/` 폴더에서 쉽게 식별하고 탐색

어지러워지지 않도록 설명적인 유형 이름을 쓰고, 다 쓴 오래된 checklist는 정리한다.

## checklist 유형 예시와 샘플 항목

**UX 요구사항 품질:** `ux.md`

샘플 항목(구현이 아니라 요구사항을 테스트함):

- "시각적 계층 요구사항이 측정 가능한 기준으로 정의되어 있는가? [Clarity, Spec §FR-1]"
- "UI 요소의 개수와 위치가 명시적으로 지정되어 있는가? [Completeness, Spec §FR-1]"
- "상호작용 상태 요구사항(hover, focus, active)이 일관되게 정의되어 있는가? [Consistency]"
- "모든 상호작용 요소에 대해 접근성 요구사항이 명시되어 있는가? [Coverage, Gap]"
- "이미지 로드에 실패했을 때의 대체 동작이 정의되어 있는가? [Edge Case, Gap]"
- "'눈에 띄는 표시'를 객관적으로 측정할 수 있는가? [Measurability, Spec §FR-4]"

**API 요구사항 품질:** `api.md`

샘플 항목:

- "모든 실패 시나리오에 대해 오류 응답 형식이 명시되어 있는가? [Completeness]"
- "속도 제한 요구사항이 구체적인 임계값으로 정량화되어 있는가? [Clarity]"
- "인증 요구사항이 모든 엔드포인트에서 일관적인가? [Consistency]"
- "외부 의존성에 대해 재시도·타임아웃 요구사항이 정의되어 있는가? [Coverage, Gap]"
- "버전 관리 전략이 요구사항에 문서화되어 있는가? [Gap]"

**성능 요구사항 품질:** `performance.md`

샘플 항목:

- "성능 요구사항이 구체적인 지표로 정량화되어 있는가? [Clarity]"
- "모든 핵심 사용자 여정에 대해 성능 목표가 정의되어 있는가? [Coverage]"
- "다양한 부하 조건에서의 성능 요구사항이 명시되어 있는가? [Completeness]"
- "성능 요구사항을 객관적으로 측정할 수 있는가? [Measurability]"
- "고부하 시나리오에 대한 성능 저하 요구사항이 정의되어 있는가? [Edge Case, Gap]"

**보안 요구사항 품질:** `security.md`

샘플 항목:

- "보호 대상 리소스 전체에 대해 인증 요구사항이 명시되어 있는가? [Coverage]"
- "민감 정보에 대한 데이터 보호 요구사항이 정의되어 있는가? [Completeness]"
- "위협 모델이 문서화되어 있고 요구사항이 그에 맞춰져 있는가? [Traceability]"
- "보안 요구사항이 컴플라이언스 의무와 일관적인가? [Consistency]"
- "보안 실패·침해 대응 요구사항이 정의되어 있는가? [Gap, Exception Flow]"

## 반례: 하지 말아야 할 것

**❌ 잘못된 예 - 요구사항이 아니라 구현을 테스트한다:**

```markdown
- [ ] CHK001 - Verify landing page displays 3 episode cards [Spec §FR-001]
- [ ] CHK002 - Test hover states work correctly on desktop [Spec §FR-003]
- [ ] CHK003 - Confirm logo click navigates to home page [Spec §FR-010]
- [ ] CHK004 - Check that related episodes section shows 3-5 items [Spec §FR-005]
```

**✅ 올바른 예 - 요구사항 품질을 테스트한다:**

```markdown
- [ ] CHK001 - Are the number and layout of featured episodes explicitly specified? [Completeness, Spec §FR-001]
- [ ] CHK002 - Are hover state requirements consistently defined for all interactive elements? [Consistency, Spec §FR-003]
- [ ] CHK003 - Are navigation requirements clear for all clickable brand elements? [Clarity, Spec §FR-010]
- [ ] CHK004 - Is the selection criteria for related episodes documented? [Gap, Spec §FR-005]
- [ ] CHK005 - Are loading state requirements defined for asynchronous episode data? [Gap]
- [ ] CHK006 - Can "visual hierarchy" requirements be objectively measured? [Measurability, Spec §FR-001]
```

**핵심 차이:**

- 잘못된 예: 시스템이 올바르게 동작하는지 테스트한다
- 올바른 예: 요구사항이 올바르게 쓰였는지 테스트한다
- 잘못된 예: 동작을 검증(verification)한다
- 올바른 예: 요구사항 품질을 확인(validation)한다
- 잘못된 예: "X를 하는가?"
- 올바른 예: "X가 명확하게 명시되어 있는가?"

## 실행 후 점검

**extension hook 확인(checklist 생성 후)**:
프로젝트 루트에 `.specify/extensions.yml`이 있는지 확인한다.
- 있으면 읽고 `hooks.after_checklist` 키 아래의 항목을 찾는다
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
