# CLAUDE.md

경쟁사 주간 동향 다이제스트 사이트. 한국 신용평가/기업데이터 5개사를 매일 추적하는 **정적 웹사이트**다. 콘텐츠는 사람이 아니라 **스케줄된 원격 Claude 루틴**이 매일 생성·커밋하고, GitHub Actions가 Netlify에 자동 배포한다.

> **이 repo는 두 개의 다이제스트를 호스팅한다.** ① 루트(`/`) = 경쟁사 주간 동향(5개사), ② `/ai` = 글로벌 AI 기술 동향. 둘 다 같은 Netlify 사이트·deploy.yml·notify 인프라를 공유하며, 각자 별도의 생성 루틴을 가진다. 아래 문서는 주로 경쟁사 다이제스트 기준이며, AI 다이제스트 전용 내용은 **`## AI 기술 동향 다이제스트 (/ai)`** 섹션 참조.

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
- **동작 흐름**: (STEP 4) 5개사 멀티채널 웹 리서치 → (STEP 5) 전날 아카이브 대비 중복제거 → (STEP 6~8) `index.html` + `archive/<today>.html` 작성(출처 매체 표기 포함) → (STEP 9) `manifest.json` 갱신 → (STEP 9.5) **배포 직전 모든 기사 URL 전수 검증**(HTTP 200 + 실제 기사 본문 + 제목 키워드 일치, 실패 항목 제거) → (STEP 10) `git push`.
- **STEP 4 검색 채널 (2026-05-30 확장)**: 회사당 후보 기사를 **폭넓게(≥5개 목표, 상한 없음)** 수집한다. 첫 히트에서 멈추지 않는다.
  - (A) **WebSearch** — 회사당 4~6개 다양한 쿼리(정식명+약칭+영문명+주제어 조합).
  - (B) **네이버 포털 뉴스 검색 — 필수** — `https://search.naver.com/search.naver?where=news&query={검색어}&sort=1&pd=4` (최신순/최근 1개월). 회사당 최소 2개 검색어(정식명+약칭).
  - (C) 보조 채널 — Google News, 공식 뉴스룸/보도자료, 상장사 DART 공시.
  - (D) 후보 URL을 WebFetch로 사실·날짜 확인 후 URL 기준 dedup. 모든 후보에 REAL source_url + 보도일자 기록.
- **빈 날 방지 fallback (2026-05-30 신설, STEP 6)**: 7일 윈도우 내 신규 0건인 회사는 **최근 8~14일 백업 풀**에서 미보도 항목을 NEW 카드로 노출(`near` 날짜칩). 14일간 정말 아무것도 없을 때만 empty-state. → "전 회사 빈칸" 반복 방지.
- recap 표시 상한: **최대 15개** (2026-05-30, 기존 10개에서 상향).
- **핵심**: 루틴은 **전날 아카이브를 구조 템플릿**으로 삼는다 (`Keep ALL structure. Replace ONLY content`). 따라서 오늘 아카이브의 구조를 바꾸면 다음날 생성분에도 자연스럽게 전파된다.
- **프롬프트 수정 방법** (다른 컴퓨터에서도): Claude Code에서 `/schedule` 스킬 → `RemoteTrigger`(action `get`/`update`)로 이 루틴의 `job_config.ccr.events[].data.message.content`를 편집. 또는 웹 UI: https://claude.ai/code/routines
  - ⚠️ **update body 스키마 주의**: `events[]` 원소는 `{"data":{"message":{"role":"user","content":"..."}, ...}}` 형식이어야 한다. `event_type` 필드를 넣으면 v2 변환 에러(`unknown field "event_type"`)로 400 거부됨. get으로 받은 구조를 그대로 두고 `content`만 교체할 것. (간헐적으로 첫 update가 400 날 수 있으니 동일 형식으로 1회 재시도.)
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
- **출처 매체 표기 (필수, 2026-05-30)**: 모든 항목에 언론사/매체명을 노출한다.
  - 카드: 제목 위 `card-meta`에 `<span class="source-chip">{매체명}</span>` + `date-chip`.
  - CEO TOP-3: 제목 뒤 `<span class="src-tag">{매체명}</span>`.
  - recap: 끝 span에 `({매체명} · {날짜} 최초 보도)`.
  - Sources: `{기사 제목} — {매체명}` 형식. 관련 스타일(`.card-meta`/`.source-chip`/`.src-tag`)은 `styles.css`에 정의됨.
- **링크 무결성 (필수, 2026-05-30)**: 모든 링크는 개별 기사의 완전한 실제 URL만. 검색결과 페이지(`search.naver.com`)·목록 페이지(`korearatings.com/cms` 등 기사 본문 아님)·잘린/플레이스홀더 URL·날조 URL 금지. 배포 직전 전수 검증(아래 STEP 9.5).

## 로컬 클론 / 동기화
- 이 저장소는 로컬 `/home/jaykwon/projects/27th-agent`에 클론돼 있다 (origin = `coll20/competitor-digest-site`).
- `.claude/`는 **`.gitignore`에 등록**돼 있다 — 로컬 `settings.local.json`에 PAT가 평문으로 있어 절대 커밋 금지.
- 로컬에서 push: 토큰을 git config에 저장하지 않고 일회성으로만 사용 → `git -c credential.helper= push "https://x-access-token:<PAT>@github.com/coll20/competitor-digest-site.git" HEAD:main`.

## AI 기술 동향 다이제스트 (/ai)
글로벌 AI 기술 동향을 매일 정리하는 두 번째 다이제스트. 같은 repo·Netlify·deploy·notify 인프라 위에서 `/ai` 경로로 서빙된다.
- **Live**: https://competitor-digest-jay-1779945070.netlify.app/ai/
- **파일**: `ai/index.html`(최신), `ai/archive/<date>.html`(아카이브), `ai/archive/manifest.json`, `ai/styles.css`(틸/인디고 테마, 자체 완결형), `ai/sidebar.js`(`/ai/archive/manifest.json` fetch, `/ai/`로 링크).
- **생성 루틴 ID**: `trig_01FJQEYTS9m2b9cB3a2qp14J` (이름: "Daily Global AI Tech Digest (테크핀 인사이트 포함)")
  - **cron**: `0 21 * * *` (UTC) = **06:00 KST** — 경쟁사 루틴(07:00 KST)보다 1시간 먼저 실행해 07:30 알림 전 둘 다 준비됨. push는 `git pull --rebase` 후 수행(경쟁사 루틴과 충돌 방지).
  - **model**: `claude-sonnet-4-6`, env `env_012Eb5mv4x1BeWNXF8NxBfz9` (경쟁사 루틴과 공유).
- **콘텐츠 구조**: 🎯 오늘의 핵심 3(CEO 스타일) → **5개 고정 영역** 카드(🌐 frontier / 🔧 infra / 🧩 agents / 🏦 finance / 📜 policy) → 💡 **테크핀레이팅스 인사이트**(동향이 회사 자산에 주는 함의 4~5개 종합) → 📚 이번 주 누적(recap) → Sources.
  - 핵심 차별점: **글로벌 동향 우선**(영문 1차 소스), 모든 항목에 **출처 매체+인라인 링크+💡 테크핀 연관 인사이트**, finance 영역 최우선.
  - 테크핀 자산(월단위 세무·상거래 데이터, CPS 491, GNN 부도예측, EWS, D-Pay, AI 경영진단, 사기탐지, 은행 CSS 납품)에 동향을 연결하는 인사이트가 핵심 가치.
- **dedup·링크검증**: 경쟁사 루틴과 동일하게 전날 AI 아카이브 대비 NEW/ALREADY_COVERED 분류 → recap, 그리고 배포 직전 STEP 9.5 전 URL 검증(HTTP 200 + 실제 기사 본문 + 키워드 일치, 검색·목록 페이지/깨진 링크 제거).
- **한글 상세 + 🇰🇷 한글로 읽기 (2026-06-02)**: 각 카드/CEO에 `🇰🇷 한글로 읽기` 버튼 → `ai/archive/<date>-ko.html`(각 항목 6~10문장 **자체 작성 한글 상세본**, 원문 전문 번역 아님=저작권 안전 + 항목별 `원문 보기` 링크). 영문 1차=primary, 같은 사건의 **검증된** 국내 한글 보도가 있으면 `card-meta`에 `🇰🇷 국내 보도`(`.kr-src`) 보조 칩. 앵커 규칙 area+순번(frontier-1…). 스타일 `.ko-wrap`/`.ko-entry`/`.ko-btn`/`.kr-src`는 `ai/styles.css`. 루틴 프롬프트에 STEP 4(국내보조·blog금지)·6(ko_detail_ko·source_url_kr·anchor_id)·8.5(버튼/칩)·**8.6(한글 페이지 생성)**·9.5(국내URL·앵커 검증) 영구 반영. ⚠️ ko 페이지는 manifest 미포함(사이드바 비표시).
- **크로스링크**: 경쟁사 페이지 사이드바에 `.sidebar-switch`로 `/ai`행, AI 페이지 사이드바에 `/`행 링크 상호 연결.
- **알림 통합**: `notify.py`가 두 manifest(`/archive/manifest.json` + `/ai/archive/manifest.json`)를 모두 읽어 **1통**에 두 섹션(경쟁사 + AI)으로 카카오톡·Gmail 발송. AI manifest 없으면 경쟁사만 발송(graceful).
- **프롬프트 수정**: `/schedule` 스킬 또는 `RemoteTrigger get/update`로 이 루틴의 `job_config.ccr.events[].data.message.content` 편집. ⚠️ create/update 스키마: `session_context`는 `job_config.ccr` **안에** 위치(model/allowed_tools 포함), `events[].data`에 `uuid/session_id/type/parent_tool_use_id` 필요.
- ⚠️ 프롬프트에 push용 GitHub PAT 평문 포함(경쟁사 루틴과 동일 토큰). 이 repo에 커밋 금지.

## 작업 로그
- **2026-06-02**:
  - **글로벌 AI 기술 동향 다이제스트(`/ai`) 추가** — 5개 영역 카드 + 테크핀 인사이트 섹션, 자체 테마 CSS/sidebar, 창간호 시드(12개 항목 전수 링크검증), 생성 루틴 `trig_01FJQEYTS9m2b9cB3a2qp14J`(06:00 KST), `notify.py`를 두 다이제스트 통합 1통 발송으로 확장, 양 사이트 크로스링크.
  - **AI 한글 상세 기능** — `🇰🇷 한글로 읽기` 버튼 + `ai/archive/<date>-ko.html`(자체 작성 한글 상세본) + 글로벌 1차/국내 보조 링크(`🇰🇷 국내 보도`). AI 루틴에 영구 반영(STEP 4·6·8.5·8.6·9.5). 시드 국내 보도칩 2건(앤트로픽 금융에이전트=ZDNet, EU AI법=디지털투데이).
  - **경쟁사 루틴 STEP 4 검색 개편(rev2)** — 사용자 피드백(기관명 중심으로 더 많이)으로 시작. 1차 시도(rev1 "이름만 검색")가 **브랜드명 단독 WebSearch=회사 홈페이지·주식·채용 페이지만 반환**임을 수동 테스트로 발견(루틴이 또 전 회사 "신규 없음") → **rev2**로 정정: "회사명+뉴스성 키워드 + 네이버/구글뉴스(뉴스 인덱스)" 발견 + **2차 언급 기사**(타기관 헤드라인 속 경쟁사: 예 케이뱅크+NICE 공동출시) 포착 + blog/cafe 인용 금지 + 가벼운 관련성 필터. 계기: NICE 산학연구포럼 기사(ddaily/newsfreezone, 5/29)가 rev1에서 누락된 케이스.
  - **운영 gotcha 발견** — ① 수동 `RemoteTrigger run`은 상태/로그 조회 불가(`get`의 `last_fired_at`은 cron 정기실행만 갱신; 수동 run은 push해도 안 바뀜) → 결과 확인은 GitHub 원격 HEAD 폴링(새 "Daily digest" 커밋). "no changes"면 push 없음. ② `blog.naver.com`/`cafe.naver.com`은 WebFetch 불가 → 검증 불가 → 인용 금지.
- **2026-05-28**: 사이트 v1 부트스트랩, Netlify 배포 워크플로, 매일 알림(카카오+Gmail) 추가.
- **2026-05-29**: 본문 항목에 원문 기사 **인라인 링크** 추가(CEO·recap). 영구 규칙은 생성 루틴 프롬프트의 새 `STEP 8.5 · INLINE SOURCE LINKS`에 반영. 테스트 아카이브 `2026-05-29 (밤 버전)` 추가. `sidebar.js` 날짜 표시 정규화 및 `label` 변형 링크 처리.
- **2026-05-30**:
  - **검색 채널 대폭 확장** — 생성 루틴 STEP 4를 멀티채널(회사당 4~6개 쿼리 + **네이버 포털 뉴스 검색 필수** + Google News/공식 뉴스룸/DART 보조)로 재작성. 회사당 후보 ≥5개 목표.
  - **빈 날 방지 fallback 신설** — STEP 6에 7일 내 신규 0건 시 8~14일 백업 풀에서 항목을 끌어오는 정책 추가. recap 상한 10→15.
  - **테스트 실행 검증** — 새 프롬프트로 1회 수동 실행(`RemoteTrigger run`). 결과: 전 회사 빈칸이던 5/30이 KCB(카카오페이 스코어 주금공 도입)·이크레더블(한기평 IFRS18 리포트) 카드로 채워지고 Sources 12개, 가짜/검색페이지 링크 0개 확인. → 정식 5/30 다이제스트로 채택.
  - **GitHub PAT 로테이션** — 노출 우려로 토큰 교체(신규 만료 2027-05-29). 교체 위치 2곳: ① 원격 루틴 프롬프트, ② 로컬 `.claude/settings.local.json`. 새 토큰 권한 = **Contents R/W 만**(Secrets 권한 불필요 — Secret 갱신은 별도 `ADMIN_PAT` 담당). **기존(노출) 토큰은 아직 revoke 안 함 — 사용자가 추후 폐기 예정.**
  - 로컬 저장소 클론 + `.claude/` gitignore 등록.
  - **출처 매체 전 항목 표기** — 카드 `source-chip`, CEO `src-tag`, recap·Sources 매체명. `styles.css`에 `.card-meta`/`.source-chip`/`.src-tag` 스타일 추가.
  - **링크 무결성 버그픽스** — 테스트 실행분에서 이크레더블 "한국기업평가 IFRS18 이슈리포트" 카드가 실제 기사가 아니라 `korearatings.com/cms` **목록 페이지**를 링크하고 있었음(사용자 발견). 해당 항목 제거. 추가로 가짜 NICE 기사(fntimes 빈 페이지)·무관 기사(etnews CJ ENM)·깨진 링크(venturesquare 410·wowtale 403)도 제거.
  - **배포 직전 URL 전수 검증 도입** — 본문·Sources의 모든 URL을 HTTP 200 + 실제 기사 본문 + 제목 키워드 일치로 검증한 뒤에만 배포. 5/30분 9개 URL 전수 통과 확인 후 배포.
  - **루틴 프롬프트에 영구 반영 완료** — STEP 4(B)에 네이버 검색페이지 URL 금지 규칙, STEP 6/7에 `source_name` 필드, STEP 8.5에 출처 매체 표기(src-tag/source-chip) 규칙, STEP 9.5(배포 직전 링크 전수 검증) 신설, STEP 11 Link check 리포트, QUALITY BAR 갱신. RemoteTrigger update 200 + 응답 본문으로 반영 확인(updated_at 2026-05-30 13:09 UTC). 다음 07:00 KST 자동 실행부터 적용.
