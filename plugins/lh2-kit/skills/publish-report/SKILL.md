---
name: publish-report
description: 최적화·검증 결과로 정적 결과 보고서(docs/index.html)를 다시 만들고 GitHub에 push해 Vercel 배포를 갱신한다. "보고서 갱신", "배포 다시", "웹 페이지 업데이트" 같은 요청에 쓴다.
---

# 결과 보고서 다시 배포

`docs/index.html`은 `reports/`·`models/`의 결과 JSON을 모아 만든 정적 페이지다. GitHub `main`에 push하면 Vercel이
자동으로 다시 배포한다(저장소 루트의 `vercel.json`이 `docs/`를 그대로 올린다).

## 순서

1. 결과가 최신인지 확인한다. 최적화를 다시 돌렸다면 `reports/opt_vol30/`과 `reports/opt_validate_<모델>/`이 갱신됐는지 본다.
2. 페이지 생성과 테스트
   ```powershell
   python -m report_site.build
   python -m pytest -q tests/test_report_site.py
   ```
3. 바뀐 파일만 확인하고 커밋한다. 비밀 값이 없는지 본다.
   ```powershell
   git status --short
   git diff --cached | Select-String "sk-ant|github_pat"
   ```
4. push는 사용자에게 확인을 받은 뒤 한다(외부 공개 작업).
   ```powershell
   git add docs; git commit -m "결과 보고서 갱신"; git push
   ```
5. 1~2분 뒤 Vercel 프로덕션 주소를 열어 요약 타일의 추천 N과 총비용이 `reports/opt_vol30/report.md`와 같은지 확인한다.

## 문제가 생기면

- Vercel 빌드 실패: Deployments → 실패한 배포 → Build Logs를 그대로 붙여 넣고 원인을 찾는다.
- push했는데 그대로: 되돌리기(Instant Rollback) 뒤라 자동 반영이 꺼졌을 수 있다. 프로덕션 타일 Manage에서 최신 배포를 올린다.
