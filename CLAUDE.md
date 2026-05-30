# CLAUDE.md

경쟁사 주간 동향 다이제스트 사이트. 한국 신용평가/기업데이터 5개사를 매일 추적하는 **정적 웹사이트**다. 콘텐츠는 사람이 아니라 **스케줄된 원격 Claude 루틴**이 매일 생성·커밋하고, GitHub Actions가 Netlify에 자동 배포한다.

## Live & Infra
- **Live**: https://competitor-digest-jay-1779945070.netlify.app
- **Repo**: https://github.com/coll20/competitor-digest-site (branch: `main`)
- **Netlify site id**: `5d37f5df-c388-4d99-916e-ec7f44e5e666`
- **Stack**: 순수 HTML/CSS/Vanilla JS (빌드 단계 없음). 알림은 Python, 자동화는 GitHub Actions.

## Target companies (5)
| id | 회사 | num | subtitle |
|----|------|-----|----------|
| nice | NICE신용평가 / NICE평가정보 | 01 | NICE 그룹 |
| kodata | 한국평가데이터 (KODATA) | 02 | 구 한국기업데이터(KED) |
| kcb | KCB (코리아크레딧뷰로) | 03 | — |
| kcs | 한국평가정보 (KCS) | 04 | 국내 최초 전업 개인사업자 CB |
| ecredible | 이크레더블 (eCredible) | 05 | Fitch / 한국기업평가 자회사 |

## File map
- `index.html` — 최신(LATEST) 다이제스트
- `archive/<date>.html` — 일자별 아카이브 (예: `archive/2026-05-29.html`)
- `archive/manifest.json` — 아카이브 인덱스 (사이드바가 읽음)
- `styles.css` — 다크 테마 스타일
- `sidebar.js` — 목차/아카이브 목록 렌더 + 모바일 토글
- `netlify.toml` — `publish="."`, 보안 헤더
- `.github/workflows/deploy.yml` — push → Netlify 프로덕션 배포
- `.github/workflows/notify.yml` + `.github/scripts/notify.py` — 매일 카카오톡 + Gmail 알림

## 페이지 콘텐츠 구조
1. 🎯 **CEO 5분 브리핑** — TOP-3, urgency 배지(high/midhigh/low) + 한 줄 결론
2. **회사별 섹션 5개** — NEW 항목만 카드로, 없으면 empty-state
3. 📚 **이번 주 누적 주요 동향** (recap) — 이전 다이제스트에서 이미 다룬 항목 1줄 요약
4. **Sources** — 기사 원문 링크 목록

## 어떻게 수정하나
정적 파일이라 **GitHub 파일을 고쳐 `main`에 push하면 `deploy.yml`이 ~2분 내 Netlify에 반영**한다 (Netlify를 직접 만질 필요 없음).
- **일회성 수정**: `index.html` / `archive/*.html` 직접 편집 → commit → push.
- **영구 수정** (매일 자동 생성분에도 유지돼야 하는 변경): 아래 **생성 루틴** 프롬프트도 함께 고쳐야 한다. 안 그러면 다음 자동 생성분이 덮어쓴다.

## 생성 루틴 (매일 자동 생성의 정체)
매일 오전 7시(KST) 콘텐츠는 **스케줄된 원격 Claude 루틴**이 만든다. 커밋 작성자: `Daily Digest Routine <routine@anthropic.com>`.
- **루틴 ID**: `trig_01HHXYVgdgB7HToq4SrFaPZk`
- **cron**: `0 22 * * *` (UTC) = **07:00 KST**
- **model**: `claude-sonnet-4-6`
- **동작 흐름**: (STEP 4) 5개사 멀티채널 웹 리서치 → (STEP 5) 전날 아카이브 대비 중복제거 → (STEP 6~8) `index.html` + `archive/<today>.html` 작성 → (STEP 9) `manifest.json` 갱신 → (STEP 10) `git push`.
- **STEP 4 검색 채널 (2026-05-30 확장)**: 회사당 후보 기사를 **폭넓게(≥5개 목표, 상한 없음)** 수집한다. 첫 히트에서 멈추지 않는다.
  - (A) **WebSearch** — 회사당 4~6개 다양한 쿼리(정식명+약칭+영문명+주제어 조합).
  - (B) **네이버 포털 뉴스 검색 — 필수** — `https://search.naver.com/search.naver?where=news&query={검색어}&sort=1&pd=4` (최신순/최근 1개월). 회사당 최소 2개 검색어(정식명+약칭).
  - (C) 보조 채널 — Google News, 공식 뉴스룸/보도자료, 상장사 DART 공시.
  - (D) 후보 URL을 WebFetch로 사실·날짜 확인 후 URL 기준 dedup. 모든 후보에 REAL source_url + 보도일자 기록.
- **빈 날 방지 fallback (2026-05-30 신설, STEP 6)**: 7일 윈도우 내 신규 0건인 회사는 **최근 8~14일 백업 풀**에서 미보도 항목을 NEW 카드로 노출(`near` 날짜칩). 14일간 정말 아무것도 없을 때만 empty-state. → "전 회사 빈칸" 반복 방지.
- recap 표시 상한: **최대 15개** (2026-05-30, 기존 10개에서 상향).
- **핵심**: 루틴은 **전날 아카이브를 구조 템플릿**으로 삼는다 (`Keep ALL structure. Replace ONLY content`). 따라서 오늘 아카이브의 구조를 바꾸면 다음날 생성분에도 자연스럽게 전파된다.
- **프롬프트 수정 방법** (다른 컴퓨터에서도): Claude Code에서 `/schedule` 스킬 → `RemoteTrigger`(action `get`/`update`)로 이 루틴의 `job_config.ccr.events[].data.message.content`를 편집. 또는 웹 UI: https://claude.ai/code/routines
- ⚠️ **보안**: 루틴 프롬프트에 push용 GitHub PAT가 평문으로 들어 있다(2곳: INFRA 안내 + STEP 1 clone 명령). **이 토큰은 이 저장소에 절대 커밋하지 말 것.** 노출이 우려되면 rotate 후 루틴 프롬프트만 갱신.

## 아카이브 네이밍 컨벤션
- **정규 일자**: `2026-05-29` → `archive/2026-05-29.html`
- **같은 날 수동 변형**: 날짜에 접미사를 붙이고 `label` 필드로 표기. 예) `2026-05-28-rerun` + `label: "오전 버전"`, `2026-05-29-night` + `label: "밤 버전"`
- **manifest 항목**: `{date, title, headline, label?}`, `date` 내림차순 정렬, 2-space pretty-print.
- `sidebar.js`는 날짜를 `YYYY-MM-DD` 접두만 표시(`it.date.match(/^\d{4}-\d{2}-\d{2}/)`)하고 `label`이 있으면 ` (label)`을 덧붙인다. `label`이 달린 변형은 목록 최상단이어도 `/`가 아니라 자기 아카이브 페이지로 링크된다.
- 루틴은 자동 생성 항목에 `label`을 붙이지 않으며, **수동 `label` 항목은 보존**한다 (manifest STEP 9 정책).

## 알림 파이프라인
`notify.yml`: **22:30 UTC (07:30 KST)** 매일. `notify.py`가 manifest 최신 항목(날짜+headline)을 읽어 카카오톡(나에게 보내기) + Gmail HTML 메일을 발송. 카카오 refresh_token이 rotate되면 `ADMIN_PAT`로 GitHub Secret을 자동 갱신.
필요한 **GitHub Secrets**: `NETLIFY_AUTH_TOKEN`, `KAKAO_REST_API_KEY`, `KAKAO_REFRESH_TOKEN`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `GMAIL_EXTRA_RECIPIENTS`, `ADMIN_PAT`.

## 작성 컨벤션
- 사용자 노출 텍스트는 **전부 한국어**.
- 뉴스 **날조 금지**. Sources에는 실제로 fetch한 URL만 싣는다.
- 중복 제거는 보수적으로 (애매하면 ALREADY_COVERED로 분류해 recap으로).
- **본문 인라인 링크 (필수)**: CEO TOP-3 / 회사 카드 / recap 각 항목은 하단 Sources와 별개로 원문 기사 인라인 링크를 가진다.
  - CEO/카드: 제목 텍스트를 `<a href target="_blank" rel="noopener">`로 감싼다 (`(날짜)` span은 링크 밖).
  - recap: 사건 요약 문구를 `<a class="recap-link" ...>`로 감싼다.
  - 스타일은 `styles.css`에 정의됨(`.ceo-body .title a`, `.card-title a`, `a.recap-link`). URL 없으면 링크 생략(날조 금지).

## 로컬 클론 / 동기화
- 이 저장소는 로컬 `/home/jaykwon/projects/27th-agent`에 클론돼 있다 (origin = `coll20/competitor-digest-site`).
- `.claude/`는 **`.gitignore`에 등록**돼 있다 — 로컬 `settings.local.json`에 PAT가 평문으로 있어 절대 커밋 금지.
- 로컬에서 push: 토큰을 git config에 저장하지 않고 일회성으로만 사용 → `git -c credential.helper= push "https://x-access-token:<PAT>@github.com/coll20/competitor-digest-site.git" HEAD:main`.

## 작업 로그
- **2026-05-28**: 사이트 v1 부트스트랩, Netlify 배포 워크플로, 매일 알림(카카오+Gmail) 추가.
- **2026-05-29**: 본문 항목에 원문 기사 **인라인 링크** 추가(CEO·recap). 영구 규칙은 생성 루틴 프롬프트의 새 `STEP 8.5 · INLINE SOURCE LINKS`에 반영. 테스트 아카이브 `2026-05-29 (밤 버전)` 추가. `sidebar.js` 날짜 표시 정규화 및 `label` 변형 링크 처리.
- **2026-05-30**:
  - **검색 채널 대폭 확장** — 생성 루틴 STEP 4를 멀티채널(회사당 4~6개 쿼리 + **네이버 포털 뉴스 검색 필수** + Google News/공식 뉴스룸/DART 보조)로 재작성. 회사당 후보 ≥5개 목표.
  - **빈 날 방지 fallback 신설** — STEP 6에 7일 내 신규 0건 시 8~14일 백업 풀에서 항목을 끌어오는 정책 추가. recap 상한 10→15.
  - **테스트 실행 검증** — 새 프롬프트로 1회 수동 실행(`RemoteTrigger run`). 결과: 전 회사 빈칸이던 5/30이 KCB(카카오페이 스코어 주금공 도입)·이크레더블(한기평 IFRS18 리포트) 카드로 채워지고 Sources 12개, 가짜/검색페이지 링크 0개 확인. → 정식 5/30 다이제스트로 채택.
  - **GitHub PAT 로테이션** — 노출 우려로 토큰 교체(신규 만료 2027-05-29). 교체 위치 2곳: ① 원격 루틴 프롬프트, ② 로컬 `.claude/settings.local.json`. 새 토큰 권한 = **Contents R/W 만**(Secrets 권한 불필요 — Secret 갱신은 별도 `ADMIN_PAT` 담당). **기존(노출) 토큰은 아직 revoke 안 함 — 사용자가 추후 폐기 예정.**
  - 로컬 저장소 클론 + `.claude/` gitignore 등록.
