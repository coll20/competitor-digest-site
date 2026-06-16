# CLAUDE.md

경쟁사 주간 동향 다이제스트 사이트. 한국 신용평가/기업데이터 5개사를 매일 추적하는 **정적 웹사이트**다. 콘텐츠는 사람이 아니라 **스케줄된 원격 Claude 루틴**이 매일 생성·커밋하고, GitHub Actions가 Netlify에 자동 배포한다.

> **이 repo는 네 개의 다이제스트를 호스팅한다.** ① 루트(`/`) = 경쟁사 주간 동향(5개사), ② `/ai` = 글로벌 AI 기술 동향, ③ `/fsc` = 금융위원회(FSC) 동향, ④ `/douzone` = 더존비즈온 그룹 동향(핀테크·데이터·AI 중심). 넷 다 같은 Netlify 사이트·deploy.yml·notify 인프라를 공유하며, 각자 별도의 생성 루틴을 가진다. 아래 문서는 주로 경쟁사 다이제스트 기준이며, AI 다이제스트는 **`## AI 기술 동향 다이제스트 (/ai)`**, 금융위 다이제스트는 **`## FSC 동향 다이제스트 (/fsc)`**, 더존 다이제스트는 **`## 더존비즈온 동향 다이제스트 (/douzone)`** 섹션 참조.

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
- `.github/workflows/deploy.yml` — push → (변경된 HTML 인용링크 게이트) → Netlify 프로덕션 배포
- `.github/scripts/verify_links.py` — 결정론적 인용링크 게이트. 카드/CEO/recap/Sources 인용이 목록·루트·검색·blog URL이면 FAIL → 배포 차단(따라서 notify도 차단). 네비게이션(board-link·sidebar-switch·footer·empty-state)은 예외. 변경된 *.html만 검사.
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

## 알림 파이프라인 (이벤트 기반 — 2026-06-05 변경)
`notify.yml`은 **cron이 아니라 `workflow_run`(배포 완료) 이벤트**로 발송된다. `notify.py`가 세 manifest(경쟁사+AI+FSC) 최신 항목(날짜+headline)을 읽어 카카오톡(나에게 보내기) + Gmail HTML 메일을 1통에 세 섹션으로 발송. 카카오 refresh_token이 rotate되면 `ADMIN_PAT`로 GitHub Secret을 자동 갱신.
- **트리거**: "Deploy to Netlify" 워크플로가 성공 완료되고, 그 커밋 메시지가 `Daily digest:`로 시작할 때만(=마지막 루틴인 **경쟁사 07:00 KST** 배포). → 사이트가 라이브된 직후 **~07:06 KST 즉시** 발송. AI/FSC/수동 푸시 배포에는 발송 안 함(job-level `if`로 필터, skip). 수동 발송은 `workflow_dispatch`.
- ⚠️ **왜 cron을 버렸나**: GitHub Actions의 `schedule` 트리거는 부하 시간대에 1~1.5h 지연돼 07:30 예정 알림이 실제론 08:30~09:14 KST에 도착했다(2026-06-05 실측). `workflow_run`은 지연이 거의 없어 배포 직후 발송된다.
- 경쟁사 루틴은 매일 index.html의 날짜(eyebrow/footer)를 갱신하므로 항상 diff→push→deploy가 발생 → "No changes로 알림 누락" 사실상 없음.
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

## 로컬 클론 / 동기화 (다른 PC에서 작업 시작하기)
- 이 저장소는 머신마다 다른 경로에 클론한다. 현재 주 작업 PC 기준 `/home/jaykwon/projects/33rd-agent/digest-site` (origin = `coll20/competitor-digest-site`). (구 경로 `27th-agent`은 폐기.)
- **새 PC 셋업**: ① `gh auth login`(account `coll20`, scope `repo`+`workflow`) → git push가 gh credential helper로 자동 인증됨. ② `git clone https://github.com/coll20/competitor-digest-site.git`. ③ 루틴 관리는 Claude Code의 `RemoteTrigger`/`/schedule`(claude.ai 계정 인증, PC 무관)로 어디서든 가능 — 별도 키 불필요. ④ 비상 수동 운영용 원본 시크릿(카카오·Gmail·PAT 원본값)은 이 repo에 없고, 로컬 전용 마스터 노트(주 PC의 `33rd-agent/CLAUDE.md`, git 비추적)에만 있다 — 필요 시 안전한 채널로 별도 전달.
- `.claude/`는 **`.gitignore`에 등록**돼 있다 — 로컬 `settings.local.json`에 PAT가 평문으로 있어 절대 커밋 금지.
- 로컬에서 push: gh 인증이 있으면 `git push origin HEAD:main`. gh 없이 토큰으로 일회성 push → `git -c credential.helper= push "https://x-access-token:<PAT>@github.com/coll20/competitor-digest-site.git" HEAD:main`.

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

## FSC 동향 다이제스트 (/fsc)
대한민국 **금융위원회(FSC) 알림마당**을 매일 모니터링하는 세 번째 다이제스트. 같은 repo·Netlify·deploy·notify 인프라 위에서 `/fsc` 경로로 서빙된다. 금융위는 신용평가·기업데이터·핀테크 업계의 직접 규제기관이다.
- **Live**: https://competitor-digest-jay-1779945070.netlify.app/fsc/
- **파일**: `fsc/index.html`(최신), `fsc/archive/<date>.html`(아카이브), `fsc/archive/manifest.json`, `fsc/styles.css`(네이비/골드 자체 테마), `fsc/sidebar.js`(`/fsc/archive/manifest.json` fetch, `/fsc/`로 링크).
- **모니터링 9개 게시판**: 📰 보도자료(`/no010101`) · 🗣️ 보도설명(`/no010102`) · 📢 새소식(`/no010105`) · 🏛️ 금융위 의결(`/no020101`) · ⚖️ 증선위 의결(`/no020102`) · 🚫 제재정보(`/no020103`, 상세는 주로 금감원 fss.or.kr) · 📈 금융시장동향(`/no030101`) · 📊 금융지표(`/no030102`) · 🎴 카드뉴스(`/no040101`).
- **생성 루틴 ID**: `trig_01SryyhJftXg4VH1suEHgeF3` (이름: "Daily FSC (금융위) Digest")
  - **cron**: `0 20 * * *` (UTC) = **05:00 KST** — AI(06:00)·경쟁사(07:00)보다 먼저 실행해 07:30 알림 전 셋 다 준비. push는 `git pull --rebase` 후 수행(다른 루틴과 충돌 방지).
  - **model**: `claude-sonnet-4-6`, env `env_012Eb5mv4x1BeWNXF8NxBfz9`(공유).
- **콘텐츠 구조**: 🎯 오늘의 핵심(TOP 3) → **9개 게시판 섹션** 카드(게시판칩 + 원문 제목 인라인 링크 + 2~3문장 자체 요약 + 💡 업계 함의) → 💡 **신용평가·핀테크 업계 함의 종합** → 📚 이번 주 누적(recap) → Sources.
  - 차별점: **금융위 원문(fsc.go.kr) 직접 링크**, post ID 기반 dedup(뉴스보다 정확), 각 항목에 신용평가/기업데이터/핀테크 업계 함의. PDF·이미지 위주 게시판(의결서·금융지표·카드뉴스)은 제목·안건명만 보수적 요약 + 링크(추측·날조 금지).
- **dedup·링크검증**: 전날 FSC 아카이브 대비 post URL/ID로 NEW/ALREADY_COVERED 분류 → recap, 배포 직전 STEP 9.5 전 URL 검증(HTTP 200 + 상세페이지 존재).
- **알림 통합**: `notify.py`가 세 manifest(`/archive` + `/ai/archive` + `/fsc/archive`)를 모두 읽어 **1통**에 세 섹션(경쟁사 + AI + 금융위)으로 발송. FSC manifest 없으면 해당 섹션만 생략(graceful).
- **크로스링크**: 경쟁사·AI 사이드바에 `/fsc` 행 추가, FSC 사이드바에 `/`·`/ai` 행. 루틴이 전날 아카이브를 템플릿으로 쓰므로 링크가 매일 보존·전파됨.
- **프롬프트 수정**: `/schedule` 스킬 또는 `RemoteTrigger get/update`로 이 루틴의 `job_config.ccr.events[].data.message.content` 편집. ⚠️ 게시판 추가/제거 시 STEP 4 board 목록 + STEP 8 sidebar anchors 동시 수정.
- ⚠️ 프롬프트에 push용 GitHub PAT 평문 포함(경쟁사/AI 루틴과 동일 토큰). 이 repo에 커밋 금지.

## 더존비즈온 동향 다이제스트 (/douzone)
**더존비즈온 그룹**(본사 + 계열사)을 **핀테크·기업데이터·AI·신용** 관점으로 매일 모니터링하는 네 번째 다이제스트. 같은 repo·Netlify·deploy·notify 인프라 위에서 `/douzone` 경로로 서빙된다. 더존비즈온은 ERP·세무 데이터 최대 보유사이자 **합작 신용평가사 테크핀레이팅스(더존·신한·SGI서울보증)의 모회사** — 기업데이터·CB 영역의 직접 경쟁자이자 데이터 공급·협력 파트너라는 양면성을 가진다.
- **Live**: https://competitor-digest-jay-1779945070.netlify.app/douzone/
- **파일**: `douzone/index.html`(최신), `douzone/archive/<date>.html`(아카이브), `douzone/archive/manifest.json`, `douzone/styles.css`(크림슨/앰버 자체 테마), `douzone/sidebar.js`(`/douzone/archive/manifest.json` fetch, `/douzone/`로 링크).
- **모니터링 6개 카테고리**: 🏢 실적·경영·전략(biz) · 💳 핀테크·금융(fintech) · 🗄️ 기업데이터·신용(data) · 🤖 AI·신사업(ai) · 🌐 플랫폼·ERP 위하고(platform) · 🤝 계열사·투자·M&A·파트너십(group). 회사 중심이라 경쟁사 다이제스트의 뉴스검색 방식 + AI/FSC의 주제별 섹션 구조를 결합.
- **생성 루틴 ID**: `trig_01X4BRezpqH5ftebw4NJnPad` (이름: "Daily Douzone (더존비즈온) Digest")
  - **cron**: `0 19 * * *` (UTC) = **04:00 KST** — FSC(05:00)·AI(06:00)·경쟁사(07:00)보다 먼저 실행해 07:06 알림 전 넷 다 준비. push는 `git pull --rebase` 후 수행(다른 루틴과 충돌 방지).
  - **model**: `claude-sonnet-4-6`, env `env_012Eb5mv4x1BeWNXF8NxBfz9`(공유).
- **콘텐츠 구조**: 🎯 오늘의 핵심(TOP 3) → 6개 카테고리 섹션 카드(매체칩 + 원문 인라인 링크 + 2~3문장 자체 요약 + 💡 테크핀 함의) → 💡 **테크핀레이팅스 함의 종합** → 📚 이번 주 누적(recap) → Sources.
  - 차별점: 경쟁사 루틴과 동일한 **멀티채널 뉴스검색**(회사명+뉴스성 키워드 + 네이버 뉴스 인덱스, 브랜드명 단독검색 금지, blog/cafe 인용 금지) + 배포 직전 STEP 9.5 전 URL 검증 + 모든 항목에 테크핀레이팅스 관점 함의.
  - ⚠️ **루틴 프롬프트에 박힌 날조방지 사실 3건**: ① 제4 인터넷은행('더존뱅크') 컨소시엄은 2025-03 예비인가 철회로 종료 → "인뱅 인가" 류 가짜 최신성 금지(fintech 섹션은 정직 empty-state 허용). ② 더존비즈온은 2026년 EQT파트너스 공개매수로 완전자회사화·자진 상장폐지(비상장 PE 전환). ③ 테크핀레이팅스=더존 계열사 본인 → '계열사 동향'으로 수록하되 함의는 자사 포지셔닝 관점.
- **dedup·링크검증**: 전날 더존 아카이브 대비 NEW/ALREADY_COVERED 분류 → recap, 배포 직전 STEP 9.5 전 URL 검증(HTTP 200 + 실제 기사 본문 + 키워드 일치).
- **최신성(recency-first) 정책 (2026-06-09 추가)**: STEP 4에서 후보를 보도일자로 `PRIMARY(≤7일)/BACKUP(8~30일)/DISCARD(30일 초과=폐기)` 3분류, STEP 6에서 카테고리 내 날짜 내림차순 + **30일 하드캡**(EQT 상폐 등 과거 대형 이벤트 카드 금지) + 전체 카드 최소 절반 7일 윈도우 내. ⚠️ 단 더존은 상장폐지 진행 중이라 6월 신규 보도가 객관적으로 매우 적음(2026-06-09 수동 16쿼리 검증 시 7일 윈도우 내 0건) — 정책이 맞아도 콘텐츠가 빈약할 수 있고, 그땐 정직한 empty-state/누적 강등이 맞다.
- **알림 통합**: `notify.py`가 네 manifest(`/archive` + `/ai/archive` + `/fsc/archive` + `/douzone/archive`)를 모두 읽어 **1통**에 네 섹션으로 발송. 더존 manifest 없으면 해당 섹션만 생략(graceful).
- **크로스링크**: 경쟁사·AI·FSC 사이드바에 `/douzone` 행 추가(index + 직전 archive 모두 — 루틴 템플릿 전파용), 더존 사이드바에 `/`·`/ai/`·`/fsc/` 행. 루틴이 전날 아카이브를 템플릿으로 쓰므로 매일 보존·전파됨.
- **프롬프트 수정**: `/schedule` 스킬 또는 `RemoteTrigger get/update`로 이 루틴의 `job_config.ccr.events[].data.message.content` 편집. ⚠️ 카테고리 추가/제거 시 STEP 8 sidebar anchors + 섹션 순서 동시 수정.
- ⚠️ 프롬프트에 push용 GitHub PAT 평문 포함(경쟁사/AI/FSC 루틴과 동일 토큰). 이 repo에 커밋 금지.

## 작업 로그
- **2026-06-16**:
  - **인용링크 무결성 사고 + 2중 방어 도입** — 사용자가 FSC 6/16 다이제스트의 "신정법 동의제도 개편 법률자문단 킥오프"(권대영 부위원장) 항목 링크를 눌렀더니 해당 보도자료가 없다고 제보. 진단: **사건 자체는 실제**(머니투데이·뉴스핌·이데일리 6/16 보도)였으나, FSC 루틴이 fsc.go.kr 개별 게시물을 특정 못 하자 **게시판 루트(/no010101, postId 없음)를 source_url로 박았고**, STEP 9.5가 'HTTP 200+키워드 포함'만 봐서(루트도 200·헤드라인 나열로 키워드 포함) 통과시킴. FSC 프롬프트에 board-root 강등 탈출구가 명시돼 있던 게 직접 원인. 경쟁사·AI·더존은 이미 개별기사 URL만 써서 무사(검증으로 확인).
  - **조치 ① 프롬프트(4개 전부)**: `CITATION URL DOCTRINE`(인용은 개별 기사/게시물만; 목록·루트·검색·홈·blog 금지; 못 구하면 제거/대체, 루트로 때우기 금지; 네비게이션 링크는 예외) 추가 + STEP 9.5를 '내용 일치 검증'(그 페이지가 이 사건을 실제로 다루는가) + `verify_links.py` PASS 필수로 강화. FSC는 board-root 탈출구 삭제 + 개별 게시물 없으면 검증된 언론사 기사로 대체 허용. RemoteTrigger update 4건 200, 임베디드 PAT 보존 확인.
  - **조치 ② 결정론적 게이트**: `.github/scripts/verify_links.py` 신설(stdlib만, 변경 HTML의 인용링크가 루트/목록/검색/blog면 exit 1). `deploy.yml`에 배포 직전 단계로 연결(변경된 *.html만 검사, fetch-depth:0). FAIL이면 배포 실패→notify도 차단(notify는 배포 성공 종속). LLM이 지시를 건너뛰어도 막히는 하드 가드.
- **2026-06-09**:
  - **더존 루틴 STEP 4·6 최신성(recency-first) 개편** — 사용자 피드백("기사가 너무 과거 것만 스크랩")으로 시작. 원인: 창간호~초기 자동생성분이 EQT 상폐(2~3월)·퓨리오사AI(2/19)·EY한영(3/31) 등 과거 milestone만 수집(WebSearch가 유명 과거 기사를 상단에 줌). **수정**: STEP 4에 RECENCY-FIRST 블록 신설 — 후보를 보도일자로 `PRIMARY(≤7일)/BACKUP(8~30일)/DISCARD(30일 초과=폐기)` 3분류, 네이버 최신순 상단부터 확보. STEP 6에 카테고리 내 **날짜 내림차순** + **30일 하드캡**(EQT 등 과거 대형 이벤트 카드 금지) + **전체 카드 최소 절반 7일 윈도우 내** 추가. STEP 7/11/QUALITY BAR도 일치. `RemoteTrigger update` 200 확인(임베디드 PAT 보존). 다음 04:00 KST 자동 실행부터 적용.
  - **오늘(6/09) 더존 페이지 수동 갱신** — 수동 `RemoteTrigger run`이 push 안 함(27분 폴링 무반응 → "no changes"/실패 추정) → 직접 WebSearch+서브에이전트(16쿼리)로 발굴·검증 후 페이지 재작성. 가장 오래된 2~3월 카드(EY한영·퓨리오사) 제거→recap 강등, **위하고 AI 에디션(5/21) 전면화** + EQT 6월 일정(6/25 매매정지·6/30 주식교환) + 레플릿 MOU(5/07). URL 12개 전수 HTTP 200 검증 후 push·배포 확인. ⚠️ **6/2~6/9 윈도우 내 신규 보도 객관적 0건**(더존 상장폐지 진행 중 IR 침묵) — 최신이 5/21까지인 건 콘텐츠 자체 한계.
  - **운영 gotcha 발견** — `search.naver.com`(네이버 뉴스 검색 결과 페이지)은 **로컬 Claude Code 환경에서 WebFetch 차단**("unable to fetch")(루틴=Anthropic 클라우드 환경에선 됨). 로컬 수동 발굴 시엔 WebSearch(개별 기사 URL)+한국 언론사 직접 노림+개별 URL만 WebFetch 검증으로 우회. WebSearch는 US-only라 한국 최신 뉴스 약함.
- **2026-06-08**:
  - **더존비즈온 그룹 동향 다이제스트(`/douzone`) 추가** — 4번째 다이제스트. 더존비즈온 본사+계열사를 핀테크·기업데이터·AI·신용 관점으로 모니터링. 6개 주제 카테고리(실적·경영 / 핀테크·금융 / 기업데이터·신용 / AI·신사업 / 플랫폼·ERP / 계열사·투자) + 오늘의 핵심 TOP3 + 테크핀레이팅스 함의 종합. 크림슨/앰버 자체 테마. 창간호 시드 8개 카드(EQT 공개매수·상장폐지, 위하고 AI 에디션, 테크핀레이팅스 월 재무제표, ONE AI 에이전틱, 레플릿 메이커톤, 종소세 교육, EQT 2차 공개매수, 롯데이노베이트 OmniEsol) — 전 항목 etnews/ZDNet 원문 WebFetch 검증. 생성 루틴 `trig_01X4BRezpqH5ftebw4NJnPad`(04:00 KST). `notify.py`를 네 다이제스트 통합 1통 발송으로 확장. 4-way 사이드바 크로스링크.
  - **리서치 정정사항(루틴 프롬프트에 영구 반영)**: 제4 인터넷은행(더존뱅크) 컨소시엄은 2025-03 철회로 종료(인뱅 인가 류 가짜 최신성 금지) / 더존비즈온은 2026년 EQT 공개매수로 비상장 PE 전환 / 테크핀레이팅스는 더존 핀테크 계열사 본인.
- **2026-06-05**:
  - **금융위원회(FSC) 동향 다이제스트(`/fsc`) 추가** — 3번째 다이제스트. 금융위 알림마당 9개 게시판(보도자료·보도설명·새소식·금융위/증선위 의결·제재정보·금융시장동향·금융지표·카드뉴스)을 매일 모니터링. 네이비/골드 자체 테마, 게시판별 섹션 + 오늘의 핵심 TOP3 + 업계 함의 종합. 창간호 시드(보도자료 6·보도설명 3·새소식 1·금융위 의결 1·금융시장동향 1 카드, 전 항목 fsc.go.kr 원문 검증). 생성 루틴 `trig_01SryyhJftXg4VH1suEHgeF3`(05:00 KST). `notify.py`를 세 다이제스트 통합 1통 발송으로 확장(경쟁사+AI+금융위). 3-way 사이드바 크로스링크.
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
