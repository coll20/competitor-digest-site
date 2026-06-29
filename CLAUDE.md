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
  workflows/check-digests.yml      # 07:50 워치독
  scripts/verify_links.py          # 인용링크 게이트
  scripts/notify.py                # Kakao+Gmail+secret 갱신
  scripts/check_digests.py         # 신선도 점검
index.html · archive/<date>.html · archive/manifest.json · styles.css · sidebar.js   # 경쟁사(루트)
ai/ · fsc/ · douzone/             # 각 디제스트(index·archive·manifest·styles·sidebar; ai는 <date>-ko.html도)
```

## 트러블슈팅
| 증상 | 진단 | 조치 |
|---|---|---|
| 특정 digest 안 갱신 | `gh run list --workflow=<name>.yml` 로그 확인(전 단계 로그 보임) | 수집 0건이면 config의 queries/feeds/match 점검; OpenAI 에러면 키/모델/쿼터; push 실패면 ADMIN_PAT |
| 카톡/메일 안 옴 | notify.yml 실패 또는 경쟁사 배포가 "Daily digest:"로 안 됐는지 | notify 로그 → Kakao refresh_token·GMAIL_APP_PASSWORD 확인 |
| 배포 실패 "citation link" | verify_links 게이트가 루트/목록/검색/blog 인용 발견 | 로그의 bad URL을 개별 기사 URL로 교체 또는 항목 제거(보통 config·프롬프트 튜닝) |
| 07:50 경보 메일 | 워치독이 오늘치 누락 감지 | 해당 digest 워크플로 로그 확인 후 `gh workflow run <name>.yml`로 수동 보충 |

## 작업 로그
- **2026-06-29**: **전체 시스템 리팩토링 — Anthropic 루틴 → GitHub Actions + OpenAI**
  - 계기: 옛 Anthropic 루틴들이 06-27~29 전부 생성 실패(루틴은 fire되나 push 0건). 근본 원인은 push 단계가 아니라 생성 단계(불투명 루틴의 조용한 실패). 사용자가 전면 리팩토링 결정.
  - 새 구조: 4개 digest 각각 GitHub Actions cron + Python 스크립트. 수집(Naver/fsc.go.kr/RSS)은 결정론적, OpenAI는 글쓰기만, 렌더도 코드. 공유 `digestlib.py`. verify_links 게이트·화이트리스트 가드·NO_CHANGES 실패·하드닝 push 유지. 4개 전부 로컬 + GH dispatch로 실환경 검증(competitor production·douzone·fsc·ai 모두 success).
  - 06-29 비상 백필(옛 시스템 06-27~29 누락분)도 수행. 옛 루틴 5개 비활성화. 워치독 09:00→07:50 KST. FSC 제재정보 보드 FSS URL 교정.
  - 모델 `gpt-5.1`(Secret `OPENAI_MODEL`), 뉴스피드 키 = `NAVER_CLIENT_ID/SECRET`.
  - 후속 여지: 같은 사건 다매체 중복 카드(제목 유사도 dedup v2), AI finance 피드 보강.
- (이전 이력은 git 히스토리 및 로컬 마스터 노트 참조 — 옛 Anthropic 루틴/프롬프트 기반이라 현재 구조와 무관.)
