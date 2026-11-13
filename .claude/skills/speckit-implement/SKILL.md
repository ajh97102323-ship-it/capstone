---
name: "speckit-implement"
description: "tasks.md에 정의된 모든 작업을 처리·실행해 구현 plan을 수행한다."
argument-hint: "구현 지침 또는 작업 필터(선택)"
compatibility: "Requires spec-kit project structure with .specify/ directory"
metadata:
  author: "github-spec-kit"
  source: "templates/commands/implement.md"
user-invocable: true
disable-model-invocation: false
---


## 사용자 입력

```text
$ARGUMENTS
```

진행하기 전에 사용자 입력을 **MUST** 고려한다(비어 있지 않은 경우).

## 실행 전 점검

**extension hook 확인 (구현 전)**:
- 프로젝트 루트에 `.specify/extensions.yml`이 있는지 확인한다.
- 파일이 있으면 읽고 `hooks.before_implement` 키 아래의 항목을 찾는다.
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

1. 저장소 루트에서 `.specify/scripts/powershell/check-prerequisites.ps1 -Json -RequireTasks -IncludeTasks`를 실행하고 FEATURE_DIR과 AVAILABLE_DOCS 목록을 파싱한다. 모든 경로는 절대 경로여야 한다. "I'm Groot"처럼 인자에 작은따옴표가 들어가면 이스케이프 구문을 사용한다. 예: 'I'\''m Groot'(가능하면 큰따옴표 사용: "I'm Groot").

2. **checklist 상태 확인** (FEATURE_DIR/checklists/가 있는 경우):
   - checklist 표시는 읽기 전용 게이트로 취급한다. 체크박스 상태를 스캔하고 상태를 보고하며, 필요하면 진행 전에 묻는다. checklist 파일이나 표시를 수정하지 않는다(do NOT).
   - `checklists/requirements.md`는 `/speckit-specify`와 `/speckit-clarify`가 관리하는 기본 spec 품질 checklist다. `/speckit-checklist`가 생성한 사용자 정의 checklist는 리뷰어가 소유하는 요구사항 품질 리뷰 산출물이다.
   - 사용자 정의 checklist에서 `[x]`는 리뷰어가 해당 요구사항 품질 기준이 충족되었다고 판단했다는 뜻이다. 구현 작업이 완료되었다는 뜻이 아니다(does NOT).
   - checklists/ 디렉터리의 모든 checklist 파일을 스캔한다.
   - 각 checklist에 대해 다음을 센다:
     - 전체 항목: `- [ ]`, `- [X]`, `- [x]` 중 하나와 일치하는 모든 줄
     - 체크된 항목: `- [X]` 또는 `- [x]`와 일치하는 줄
     - 체크되지 않은 항목: `- [ ]`와 일치하는 줄
   - 상태 표를 만든다:

     ```text
     | Checklist | Total | Checked | Unchecked | Status |
     |-----------|-------|---------|-----------|--------|
     | ux.md     | 12    | 12      | 0         | ✓ PASS |
     | test.md   | 8     | 5       | 3         | ✗ FAIL |
     | security.md | 6   | 6       | 0         | ✓ PASS |
     ```

   - 전체 상태를 계산한다:
     - **PASS**: 모든 checklist에 체크되지 않은 항목이 0개
     - **FAIL**: 하나 이상의 checklist에 체크되지 않은 항목이 있음

   - **체크되지 않은 항목이 있는 checklist가 하나라도 있으면**:
     - 체크되지 않은 항목 수가 담긴 표를 보여 준다.
     - **STOP**하고 다음과 같이 묻는다: "Some checklists have unchecked items. Do you want to proceed with implementation anyway? (yes/no)"
     - 계속하기 전에 사용자의 응답을 기다린다.
     - 사용자가 "no", "wait", "stop"이라고 하면 실행을 중단한다.
     - 사용자가 "yes", "proceed", "continue"라고 하면 3단계로 진행한다.

   - **모든 checklist가 체크되어 있으면**:
     - 모든 checklist가 통과했음을 보여 주는 표를 표시한다.
     - 자동으로 3단계로 진행한다.

3. 구현 맥락을 불러와 분석한다:
   - **REQUIRED**: 전체 작업 목록과 실행 계획을 위해 tasks.md를 읽는다.
   - **REQUIRED**: 기술 스택, 아키텍처, 파일 구조를 위해 plan.md를 읽는다.
   - **IF EXISTS**: 엔티티와 관계를 위해 data-model.md를 읽는다.
   - **IF EXISTS**: API 명세와 테스트 요구사항을 위해 contracts/를 읽는다.
   - **IF EXISTS**: 기술적 결정과 제약을 위해 research.md를 읽는다.
   - **IF EXISTS**: 거버넌스 제약을 위해 .specify/memory/constitution.md를 읽는다.
   - **IF EXISTS**: 통합 시나리오를 위해 quickstart.md를 읽는다.

4. **프로젝트 설정 검증**:
   - **REQUIRED**: 실제 프로젝트 설정에 맞춰 ignore file을 생성/검증한다:

   **감지 및 생성 로직**:
   - 다음 명령이 성공하는지 확인해 저장소가 git 저장소인지 판단한다(그렇다면 .gitignore를 생성/검증):

     ```sh
     git rev-parse --git-dir 2>/dev/null
     ```

   - Dockerfile*이 있거나 plan.md에 Docker가 있으면 → .dockerignore를 생성/검증한다.
   - .eslintrc*가 있으면 → .eslintignore를 생성/검증한다.
   - eslint.config.*가 있으면 → 설정의 `ignores` 항목이 필요한 패턴을 포함하는지 확인한다.
   - .prettierrc*가 있으면 → .prettierignore를 생성/검증한다.
   - .npmrc 또는 package.json이 있으면 → .npmignore를 생성/검증한다(배포하는 경우).
   - terraform 파일(*.tf)이 있으면 → .terraformignore를 생성/검증한다.
   - .helmignore가 필요하면(helm chart가 있는 경우) → .helmignore를 생성/검증한다.

   **ignore file이 이미 있으면**: 필수 패턴이 들어 있는지 검증하고, 빠진 핵심 패턴만 추가한다.
   **ignore file이 없으면**: 감지된 기술에 맞는 전체 패턴 세트로 생성한다.

   **기술별 공통 패턴** (plan.md의 기술 스택 기준):
   - **Node.js/JavaScript/TypeScript**: `node_modules/`, `dist/`, `build/`, `*.log`, `.env*`
   - **Python**: `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `dist/`, `*.egg-info/`
   - **Java**: `target/`, `*.class`, `*.jar`, `.gradle/`, `build/`
   - **C#/.NET**: `bin/`, `obj/`, `*.user`, `*.suo`, `packages/`
   - **Go**: `*.exe`, `*.test`, `vendor/`, `*.out`
   - **Ruby**: `.bundle/`, `log/`, `tmp/`, `*.gem`, `vendor/bundle/`
   - **PHP**: `vendor/`, `*.log`, `*.cache`, `*.env`
   - **Rust**: `target/`, `debug/`, `release/`, `*.rs.bk`, `*.rlib`, `*.prof*`, `.idea/`, `*.log`, `.env*`
   - **Kotlin**: `build/`, `out/`, `.gradle/`, `.idea/`, `*.class`, `*.jar`, `*.iml`, `*.log`, `.env*`
   - **C++**: `build/`, `bin/`, `obj/`, `out/`, `*.o`, `*.so`, `*.a`, `*.exe`, `*.dll`, `.idea/`, `*.log`, `.env*`
   - **C**: `build/`, `bin/`, `obj/`, `out/`, `*.o`, `*.a`, `*.so`, `*.exe`, `*.dll`, `autom4te.cache/`, `config.status`, `config.log`, `.idea/`, `*.log`, `.env*`
   - **Swift**: `.build/`, `DerivedData/`, `*.swiftpm/`, `Packages/`
   - **R**: `.Rproj.user/`, `.Rhistory`, `.RData`, `.Ruserdata`, `*.Rproj`, `packrat/`, `renv/`
   - **Universal**: `.DS_Store`, `Thumbs.db`, `*.tmp`, `*.swp`, `.vscode/`, `.idea/`

   **도구별 패턴**:
   - **Docker**: `node_modules/`, `.git/`, `Dockerfile*`, `.dockerignore`, `*.log*`, `.env*`, `coverage/`
   - **ESLint**: `node_modules/`, `dist/`, `build/`, `coverage/`, `*.min.js`
   - **Prettier**: `node_modules/`, `dist/`, `build/`, `coverage/`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`
   - **Terraform**: `.terraform/`, `*.tfstate*`, `*.tfvars`, `.terraform.lock.hcl`
   - **Kubernetes/k8s**: `*.secret.yaml`, `secrets/`, `.kube/`, `kubeconfig*`, `*.key`, `*.crt`

5. tasks.md 구조를 파싱해 다음을 추출한다:
   - **작업 phase**: Setup, Tests, Core, Integration, Polish
   - **작업 의존성**: 순차 실행과 병렬 실행 규칙
   - **작업 세부사항**: ID, 설명, 파일 경로, 병렬 표시 [P]
   - **실행 흐름**: 순서와 의존성 요구사항

6. 작업 계획에 따라 구현을 실행한다:
   - **phase 단위 실행**: 다음 phase로 넘어가기 전에 각 phase를 완료한다.
   - **의존성 준수**: 순차 작업은 순서대로 실행하고, 병렬 작업 [P]는 함께 실행할 수 있다.
   - **TDD 방식 준수**: 테스트 작업을 그에 대응하는 구현 작업보다 먼저 실행한다.
   - **파일 기준 조율**: 같은 파일을 건드리는 작업은 순차적으로 실행해야 한다.
   - **검증 체크포인트**: 다음으로 진행하기 전에 각 phase의 완료를 검증한다.

7. 구현 실행 규칙:
   - **Setup 우선**: 프로젝트 구조, 의존성, 설정을 초기화한다.
   - **코드보다 테스트 먼저**: contract, 엔티티, 통합 시나리오에 대한 테스트를 작성해야 하는 경우
   - **핵심 개발**: 모델, 서비스, CLI 명령, 엔드포인트를 구현한다.
   - **통합 작업**: 데이터베이스 연결, 미들웨어, 로깅, 외부 서비스
   - **마무리와 검증**: 단위 테스트, 성능 최적화, 문서화

8. 진행 상황 추적과 오류 처리:
   - 작업을 하나 완료할 때마다 진행 상황을 보고한다.
   - 병렬이 아닌 작업이 실패하면 실행을 중단한다.
   - 병렬 작업 [P]는 성공한 작업을 계속 진행하고, 실패한 작업은 보고한다.
   - 디버깅에 필요한 맥락을 담은 명확한 오류 메시지를 제공한다.
   - 구현을 진행할 수 없으면 다음 단계를 제안한다.
   - **IMPORTANT** 완료한 작업은 tasks 파일에서 반드시 [X]로 표시한다.

9. 완료 검증:
   - 필요한 작업이 모두 완료되었는지 검증한다.
   - 구현된 feature가 원래 명세와 일치하는지 확인한다.
   - 테스트가 통과하고 커버리지가 요구사항을 충족하는지 검증한다.
   - 구현이 기술 plan을 따르는지 확인한다.

참고: 이 명령은 tasks.md에 완전한 작업 분해가 있다고 가정한다. 작업이 불완전하거나 없으면 먼저 `/speckit-tasks`를 실행해 작업 목록을 다시 생성하도록 제안한다.

## 필수 실행 후 hook

**사용자에게 완료를 보고하기 전에 이 섹션을 반드시 완료해야 한다(MUST).**

프로젝트 루트에 `.specify/extensions.yml`이 있는지 확인한다.
- 파일이 없거나 `hooks.after_implement` 아래에 등록된 hook이 없으면 완료 보고로 건너뛴다.
- 파일이 있으면 읽고 `hooks.after_implement` 키 아래의 항목을 찾는다.
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

완료한 작업의 요약과 함께 최종 상태를 보고한다.

## 완료 조건

- [ ] tasks.md의 모든 작업이 완료되고 `[X]`로 표시되었다
- [ ] 구현이 명세, plan, 테스트 커버리지에 비추어 검증되었다
- [ ] 위의 필수 실행 후 hook 규칙에 따라 extension hook이 실행되었거나 건너뛰어졌다
- [ ] 완료한 작업의 요약과 함께 사용자에게 완료를 보고했다
