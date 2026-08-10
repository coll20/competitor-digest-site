# CLAUDE.md

네 개의 일일 다이제스트를 호스팅하는 **정적 웹사이트 + 자동 생성 파이프라인**.
콘텐츠는 매일 **GitHub Actions에서 도는 Python 스크립트**가 생성한다 — 결정론적으로 뉴스를 수집하고
**OpenAI API**로 한국어 다이제스트를 작성한 뒤, GitHub에 push하면 GitHub Actions가 Netlify에 자동 배포한다.

> **이 repo는 네 개의 다이제스트를 호스팅한다.** ① 루트(`/`) = 경쟁사(한국 신용평가/데이터 5개사),
> ② `/ai` = 글로벌 AI 기술 동향, ③ `/fsc` = 금융위원회(FSC) 동향, ④ `/douzone` = 더존비즈온 그룹 동향.
> 넷 다 같은 Netlify 사이트·`deploy.yml`·notify 인프라를 공유하고, 각자 **별도의 GitHub Actions 워크플로 + 생성 스크립트**를 가진다.

> ⚠️ **2026-06-29 전면 리팩토링.** 과거에는 Anthropic "routine"(클라우드 스케줄 에이전트)이 생성했으나,
> 조용한 실패(로그 없음)·할루시네이션 문제로 **전부 GitHub Actions + OpenAI 파이프라인으로 교체**했다.
> 옛 Anthropic 루틴 5개(생성 4 + 백스톱)는 모두 `enabled:false`로 비활성화됨. 아래는 전부 **새 구조** 기준이다.

## Live & Infra
- **Live**: https://competitor-digest-jay-1779945070.netlify.app
- **Repo**: https://github.com/coll20/competitor-digest-site (branch: `main`)
- **Netlify site id**: `5d37f5df-c388-4d99-916e-ec7f44e5e666`
- **Stack**: 정적 HTML/CSS/Vanilla JS(빌드 없음) + 생성/알림은 Python, 자동화는 GitHub Actions.
- **로컬 클론**: `/home/jaykwon/projects/33rd-agent/digest-site`

## 일일 타임라인 (전부 GitHub Actions cron)
```
04:00 KST  douzone.yml    → scripts/douzone/generate.py   (Naver 뉴스)
05:00 KST  fsc.yml        → scripts/fsc/generate.py       (fsc.go.kr 게시판 직접)
06:00 KST  ai.yml         → scripts/ai/generate.py        (영문 RSS 피드)
07:00 KST  competitor.yml → scripts/competitor/generate.py(Naver 뉴스)
              └ 각자: 수집 → URL검증 → 전일 대비 dedup → OpenAI 작성 → 템플릿 렌더
                → verify_links 게이트 → ADMIN_PAT로 push("Daily ... digest: <date>")
              ↓ (push가 deploy.yml 트리거)
           deploy.yml → Netlify 배포 (~1.5분, 변경 HTML에 verify_links 게이트)
              ↓ (경쟁사 "Daily digest:" 배포 성공 시에만)
~07:06 KST notify.yml → 카카오톡 + Gmail (4 manifest 4섹션 1통)
07:50 KST  check-digests.yml → 4 manifest 신선도 점검, 누락 시 Gmail 경보(워치독)
```

## 생성 파이프라인 (4개 공통 구조)
**핵심 원칙: LLM은 글쓰기만. URL 발견·검증·HTML 렌더는 전부 결정론적 Python.**
(이게 옛 루틴의 두 실패 근원 — 할루시네이션·조용한 실패 — 을 제거한다.)

1. **수집(fetch)** — 디제스트별 소스에서 후보 기사를 결정론적으로 긁는다(아래 소스 표).
2. **URL 검증(verify)** — 각 후보를 HTTP GET, 200·실기사 본문·홈루트 리다이렉트 아님 확인. blog/cafe/검색 호스트 제외.
3. **dedup** — 전일 archive의 URL set과 대조 → NEW / ALREADY_COVERED.
4. **OpenAI 작성** — 검증된 후보만 넘겨 분류·요약·카드·CEO·recap 작성(구조화 JSON, `response_format=json_schema`).
   넘긴 URL set 안에서만 인용하도록 강제 + 코드가 화이트리스트 밖 URL을 한 번 더 제거(`enforce_url_whitelist`).
5. **렌더(render)** — JSON을 HTML 템플릿에 끼워넣는다(LLM이 raw HTML을 쓰지 않음 = 마크업 오류 0).
6. **게이트** — `verify_links.py`로 인용 링크가 개별 기사/게시물인지 결정론 점검(루트/목록/검색/blog면 FAIL).
7. **commit + push** — 변경 시에만 push(`NO_CHANGES`면 실패). 5회 재시도(rebase). **`ADMIN_PAT`로 push해야**
   deploy.yml/notify.yml이 트리거된다(기본 `GITHUB_TOKEN` push는 다른 워크플로를 안 깨움).

## 디제스트별 뉴스 소스 & 설정
| 디제스트 | 경로 | 뉴스 소스 | 설정 파일 | 워크플로 | 커밋 메시지 접두 |
|---|---|---|---|---|---|
| 경쟁사 | `/` | 네이버 뉴스 검색 API | `scripts/competitor/companies.json` | `competitor.yml` | `Daily digest:` ← **notify 트리거** |
| 더존 | `/douzone` | 네이버 뉴스 검색 API | `scripts/douzone/config.json` | `douzone.yml` | `Daily Douzone digest:` |
| FSC | `/fsc` | fsc.go.kr 9개 게시판 직접 파싱 | `scripts/fsc/config.json` | `fsc.yml` | `Daily FSC digest:` |
| AI | `/ai` | 영문 테크/금융 RSS 7개 | `scripts/ai/config.json` | `ai.yml` | `Daily AI digest:` |

- **공유 라이브러리**: `scripts/lib/digestlib.py`(naver 수집·verify_url·prev_urls·update_manifest·openai_compose·화이트리스트 가드).
- **회사/카테고리/게시판/피드 추가·제거는 각 `config.json`만 수정**하면 된다(코드 수정 불필요). 사이드바 앵커도 config 기반 자동 생성.
- 경쟁사/더존: `match`(회사명 변형) 토큰으로 제목·요약 관련성 필터 → 키워드 노이즈 제거. OpenAI가 추가 선별(카테고리/회사당 ≤3~4, 전체 ≤12~15, 동일사건 통합).
- FSC: 게시판 목록 페이지의 `<li>` 블록에서 게시물 `id·title·date` 파싱 → 개별 게시물 URL(`fsc.go.kr/noXXXX/{id}`) 인용. 제재정보(sanction)는 금감원(fss.or.kr) 호스팅이라 `fetch:false`+`board_url`로 링크만(스크랩 안 함).
- AI: RSS(RSS2.0·Atom 모두) 파싱 → 5영역 분류 + 한글 상세 페이지(`ai/archive/<date>-ko.html`, 자체 작성 해설=저작권 안전) + ko 앵커 무결성. finance 영역 최우선.

## 모델 / 비용
- **모델**: GitHub Secret `OPENAI_MODEL`(현재 `gpt-5.1`). 미설정 시 코드 기본값 `gpt-5.1`. 모델 바꾸려면 이 Secret만 교체.
- 1회 실행 = 후보 수십~110건(제목+짧은 요약) 입력 + 구조화 출력 1콜. 실제 토큰량은 OpenAI 대시보드 참조.

## 페이지 콘텐츠 구조 (공통)
1. 🎯 **CEO 5분 브리핑 / 오늘의 핵심** — TOP-3, urgency 배지 + 한 줄 결론
2. **섹션들** — 경쟁사 5사 / 더존 6카테고리 / FSC 9게시판 / AI 5영역. 신규 없으면 정직 empty-state
3. (FSC·더존·AI) 💡 **업계/테크핀 함의 종합**
4. 📚 **이번 주 누적**(recap) — 전일 기수록 항목 1줄 요약
5. **Sources** — 기사 원문 링크
6. (AI) 🇰🇷 **한글 상세 페이지** + 각 카드 '한글로 읽기' 버튼

## 어떻게 수정하나
- **콘텐츠 소스 변경**(회사/카테고리/게시판/피드): 해당 `scripts/<name>/config.json`만 수정 → commit → push. 다음 cron부터 적용.
- **수동 즉시 실행**: `gh workflow run <name>.yml --repo coll20/competitor-digest-site` (예: `competitor.yml`). workflow_dispatch.
  - 로컬 테스트: `cd digest-site && OPENAI_API_KEY=… NAVER_CLIENT_ID=… NAVER_CLIENT_SECRET=… OPENAI_MODEL=gpt-5.1 python scripts/<name>/generate.py [--dry-run|--no-openai]`. (로컬은 파일만 쓰고 push 안 함. `--dry-run`=수집·검증만, `--no-openai`=빈 empty-state 생성.)
- **당일 백필**(생성 실패로 오늘치가 비었을 때): **반드시 순차·이 순서로** — 경쟁사를 마지막에 둬야 그 배포로 트리거되는 notify가 4섹션 모두 채워진 상태로 나간다(동시 실행은 push 충돌 위험).
  ```bash
  for wf in douzone.yml fsc.yml ai.yml competitor.yml; do
    gh workflow run $wf --repo coll20/competitor-digest-site
    sleep 10
    id=$(gh run list --repo coll20/competitor-digest-site --workflow=$wf --limit 1 --json databaseId -q '.[0].databaseId')
    gh run watch $id --repo coll20/competitor-digest-site --exit-status || break
  done
  ```
  각 4~11분, 총 20~30분. `TODAY`는 KST 당일 기준이라 **과거 날짜 백필은 불가**(당일 안에만 유효). 끝나면 notify 로그(`KakaoTalk sent`/`Gmail sent`)와 라이브 4종 manifest의 오늘 날짜를 반드시 검증 — 생성 success ≠ 발송·배포 성공.
- **디자인/구조 변경**: 각 `generate.py`의 render 함수(템플릿 문자열) 수정. 또는 공유 CSS(`styles.css`, `ai/styles.css` 등).
- **스케줄 변경**: 각 워크플로의 `schedule.cron`(UTC). 발송 요일을 바꾸려면 경쟁사 cron을 바꾸면 됨(notify는 경쟁사 배포에 종속).

## 필요한 GitHub Secrets
| Secret | 용도 |
|---|---|
| `OPENAI_API_KEY` | 4개 생성 스크립트 — OpenAI 작성 |
| `OPENAI_MODEL` | 모델명(현재 `gpt-5.1`) |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 경쟁사·더존 — 네이버 뉴스 검색 API |
| `ADMIN_PAT` | 4개 생성 워크플로 checkout/push(이 토큰으로 push해야 deploy/notify 트리거) + notify의 Kakao secret 갱신 |
| `NETLIFY_AUTH_TOKEN` | deploy.yml — Netlify CLI |
| `KAKAO_REST_API_KEY` / `KAKAO_REFRESH_TOKEN` | notify.py — 카카오톡 |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` / `GMAIL_EXTRA_RECIPIENTS` | notify.py·워치독 — Gmail(BCC 수신자) |
> ⚠️ 옛 Anthropic 루틴 프롬프트에 평문 GitHub PAT가 박혀 있었으나 이제 루틴이 비활성화돼 무관. 새 파이프라인은 토큰을 GitHub Secret으로만 쓴다.

## 알림 파이프라인 (이벤트 기반)
`notify.yml`은 cron이 아니라 **`workflow_run`(배포 완료) 이벤트**로 발송된다. `notify.py`가 네 manifest(경쟁사+AI+FSC+더존) 최신 항목을 읽어 카카오톡 + Gmail(To: coll20, BCC: 추가 수신자) 1통 4섹션 발송.
- **트리거**: "Deploy to Netlify"가 성공하고 그 커밋 메시지가 `Daily digest:`로 시작할 때만(=경쟁사 07:00 배포). → ~07:06 KST 즉시 발송. 다른 digest 커밋(`Daily AI/FSC/Douzone digest:`)·수동 push는 발송 안 함(job-level `if` 필터).
- **신선도 가드(2026-06-28)**: 섹션 manifest 최신 date ≠ 오늘(KST)이면 카카오·Gmail에 `⚠️ 미갱신` 플래그 후 발송(staleness 방지).
- Kakao refresh_token rotate 시 `ADMIN_PAT`로 GitHub Secret 자동 갱신.

## 주간 발송 — `weekly-notify.yml` / `weekly_notify.py` (2026-07-20 신설)
주간 전략 리포트(별도 로컬 시스템, 아래 '관련 시스템' 참조)의 발행 성공 시 로컬 러너가 `gh workflow run weekly-notify.yml`로 트리거 → 데일리와 **같은 카카오/Gmail 시크릿**으로 발송(리포트 URL·총평·비밀번호 안내 포함). 카카오는 "나에게 보내기"(본인 한정), Gmail은 To+BCC. 입력: `-f url= -f label= -f date= -f headline=`. 로컬에 토큰을 두지 않고 refresh_token 자동 회전을 공유하기 위한 설계.

## 결정론적 게이트 — `.github/scripts/verify_links.py`
인용 링크(카드 제목·CEO·recap·Sources·kr-src·ko-orig)가 목록/루트/검색/blog URL이면 `exit 1`. 네비게이션(board-link·sidebar-switch·ko-btn·footer·empty-state 내부 링크)은 예외. `deploy.yml`이 변경된 *.html에 대해 실행 → FAIL이면 배포 차단(→notify도 차단). 각 `generate.py`도 push 전 자체 실행.

## 워치독 — `check-digests.yml` (07:50 KST)
4개 manifest 최신 date가 오늘(KST)인지 점검, 누락 시 Gmail 경보 + GH Actions 빨간 X. provider 무관(생성 방식과 독립). `check_digests.py`.

## 파일 맵
```
scripts/
  lib/digestlib.py                 # 4개 공유 헬퍼
  competitor/{config.json,generate.py}
  douzone/{config.json,generate.py}
  fsc/{config.json,generate.py}
  ai/{config.json,generate.py}
.github/
  workflows/{competitor,douzone,fsc,ai}.yml   # 생성(cron, OpenAI)
  workflows/deploy.yml             # push→Netlify(+verify_links 게이트)
  workflows/notify.yml             # 경쟁사 배포완료→카톡+Gmail
  workflows/weekly-notify.yml      # 주간 전략 리포트 발송(workflow_dispatch, 로컬 러너가 트리거)
  workflows/check-digests.yml      # 07:50 워치독
  scripts/verify_links.py          # 인용링크 게이트
  scripts/notify.py                # Kakao+Gmail+secret 갱신
  scripts/weekly_notify.py         # 주간 리포트 Kakao+Gmail
  scripts/check_digests.py         # 신선도 점검
index.html · archive/<date>.html · archive/manifest.json · styles.css · sidebar.js   # 경쟁사(루트)
ai/ · fsc/ · douzone/             # 각 디제스트(index·archive·manifest·styles·sidebar; ai는 <date>-ko.html도)
```

## 트러블슈팅
| 증상 | 진단 | 조치 |
|---|---|---|
| 특정 digest 안 갱신 | `gh run list --workflow=<name>.yml` 로그 확인(전 단계 로그 보임) | 수집 0건이면 config의 queries/feeds/match 점검; OpenAI 에러면 키/모델/쿼터; push 실패면 ADMIN_PAT |
| **4종 전부 동시 실패 ①** | 로그에 `openai.RateLimitError: 429 … insufficient_quota` | **OpenAI 크레딧 소진**(07-10·07-27 실제 장애). platform.openai.com 결제/충전 → (키 교체 시 `gh secret set OPENAI_API_KEY`) → 위 백필 절차. 4개가 같은 키를 쓰므로 한 번에 다 죽음 |
| **4종 전부 동시 실패 ②** | 로그에 `openai.AuthenticationError: 401 … ip_not_authorized` | **조직 IP allowlist가 GH Actions 러너 차단**(07-21 실제 장애). 키 재발급으론 해결 안 됨(제한이 조직/프로젝트 단위) — **IP 제한 없는 별도 OpenAI 프로젝트의 키**로 교체(project-level coverage가 org-level을 override) → 백필 |
| 카톡/메일 안 옴 | notify.yml 실패 또는 경쟁사 배포가 "Daily digest:"로 안 됐는지 | notify 로그 → Kakao refresh_token·GMAIL_APP_PASSWORD 확인 |
| notify가 "skipped" | ⚠ **정상** — 더존/FSC/AI 배포에도 workflow_run은 걸리지만 커밋 접두 검사에서 걸러짐 | 하루 4번 중 경쟁사 배포 1건만 success면 정상. 4건 다 skipped면 경쟁사 커밋 접두 확인 |
| check-digests가 "failure" | ⚠ **오작동 아님** — 누락 감지 시 경보 메일 발송 후 의도적으로 exit 1 | 로그에 경보 발송 완료가 있으면 워치독은 정상. 진짜 문제는 누락된 생성 워크플로 쪽 |
| 배포 실패 "citation link" | verify_links 게이트가 루트/목록/검색/blog 인용 발견 | 로그의 bad URL을 개별 기사 URL로 교체 또는 항목 제거(보통 config·프롬프트 튜닝) |
| 07:50 경보 메일 | 워치독이 오늘치 누락 감지 | 해당 digest 워크플로 로그 확인 후 `gh workflow run <name>.yml`로 수동 보충 |
| 메일만 안 옴 | Gmail App Password revoke 가능성 | myaccount.google.com/apppasswords 재발급 → secret 갱신 |

## 운영 caveat (실측 기반)
- **GitHub Actions schedule은 부하 시간대 ~1시간 지연이 상시**(07-10 실측: 경쟁사 22:00→23:10 UTC 발화). 07:50 워치독 경보가 08~09시에 와도 이상 아님. 생성이 밀리면 notify·워치독도 연쇄로 밀림.
- **OpenAI 조직 IP allowlist는 GH Actions와 양립 불가** — 러너 대역이 CIDR 7,000+개·매주 갱신이라 등록 불가(OpenAI 한도 5,000). 이 repo의 키는 반드시 **IP 제한 없는 별도 프로젝트**에서 발급·유지할 것.
- **OpenAI 크레딧은 조용히 소진된다** — 4종이 키 하나를 공유하므로 잔액 0 = 그날 브리핑 전멸(워치독은 사후 감지). 예방책은 platform.openai.com의 usage-limit 이메일 알림뿐.
- **manifest `label` 필드**는 수동 override 전용(사이드바 표시명). 생성 스크립트는 다른 엔트리의 label을 보존한다.
- **네이버 검색 API**(openapi.naver.com)는 정식 REST API라 어디서든 동작(무료 일 25,000회). 반환 `originallink`=실제 언론사 기사 URL.

## 관련 시스템 (이 repo를 소비하는 것들)
- **주간 전략 리포트**(매주 월, techfin-weekly-strategy-2607.netlify.app): 로컬(WSL) 시스템이 이 repo의 4종 다이제스트 1주일치를 읽어 사내 현안과 교차 분석. 발송만 이 repo의 `weekly-notify.yml`을 빌려 씀.
- **다이제스트 워크에이전트**(techfin-levelup.netlify.app, private repo `coll20/techfin-workagent`): 매일 08:40 KST GH Actions가 `DIGEST_PAT`으로 이 repo를 체크아웃해 당일 뉴스를 추출·개인화. 08:40인 이유 = 이 repo의 cron ~1h 지연을 회피.

## 작업 로그
- **2026-07-27**: **OpenAI 크레딧 재소진 장애 → 충전·백필 (복구 완료).** 07-10과 동일 패턴 — `429 insufficient_quota`로 07-25 경쟁사부터 실패, 07-26~27 4종 전멸(워치독 경보는 정상 발송). 크레딧 충전 → curl 실호출 검증 → 순차 백필(더존→FSC→AI→경쟁사) → notify 카톡+Gmail 발송 확인. **07-25·07-26 이틀치는 결번**(TODAY=KST 당일 기준이라 과거 백필 불가).
- **2026-07-21**: **OpenAI 조직 IP allowlist 장애 → 별도 프로젝트 키 교체·백필 (복구 완료).** 4종 전부 `401 ip_not_authorized`(장애 직전 조직 레벨 IP allowlist 활성화가 원인). 같은 조직 키 재발급은 실패(제한이 키 단위가 아님), GH 러너 대역 등록도 불가(CIDR 7,208 vs 한도 5,000) → **IP 제한 없는 별도 프로젝트에서 키 발급**으로 해결, 백필·notify 검증 완료.
- **2026-07-20**: **`weekly-notify.yml`/`weekly_notify.py` 신설** — 주간 전략 리포트 발송을 이 repo의 Actions로 수행(데일리와 카카오/Gmail 시크릿 공유, refresh_token 자동 회전 일원화).
- **2026-07-10**: **OpenAI 크레딧 소진 장애 → 키 교체·백필 (복구 완료).** 4종 전부 `429 insufficient_quota`. 신규 키 교체 → 순차 백필 17분 → notify 발송 확인. 트러블슈팅 표의 '4종 동시 실패'·'워치독 failure≠오작동'·'notify skipped=정상' 항목과 백필 절차가 이 장애의 산물. 스케줄 ~1h 지연도 이날 실측.
- **2026-06-29**: **전체 시스템 리팩토링 — Anthropic 루틴 → GitHub Actions + OpenAI**
  - 계기: 옛 Anthropic 루틴들이 06-27~29 전부 생성 실패(루틴은 fire되나 push 0건). 근본 원인은 push 단계가 아니라 생성 단계(불투명 루틴의 조용한 실패). 사용자가 전면 리팩토링 결정.
  - 새 구조: 4개 digest 각각 GitHub Actions cron + Python 스크립트. 수집(Naver/fsc.go.kr/RSS)은 결정론적, OpenAI는 글쓰기만, 렌더도 코드. 공유 `digestlib.py`. verify_links 게이트·화이트리스트 가드·NO_CHANGES 실패·하드닝 push 유지. 4개 전부 로컬 + GH dispatch로 실환경 검증(competitor production·douzone·fsc·ai 모두 success).
  - 06-29 비상 백필(옛 시스템 06-27~29 누락분)도 수행. 옛 루틴 5개 비활성화. 워치독 09:00→07:50 KST. FSC 제재정보 보드 FSS URL 교정.
  - 모델 `gpt-5.1`(Secret `OPENAI_MODEL`), 뉴스피드 키 = `NAVER_CLIENT_ID/SECRET`.
  - 후속 여지: 같은 사건 다매체 중복 카드(제목 유사도 dedup v2), AI finance 피드 보강.
- (이전 이력은 git 히스토리 및 로컬 마스터 노트 참조 — 옛 Anthropic 루틴/프롬프트 기반이라 현재 구조와 무관.)
