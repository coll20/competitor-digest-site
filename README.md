# Daily Digest Automation

매일 새벽, 4종의 뉴스 다이제스트를 **자동 생성·발행·알림**하는 end-to-end 파이프라인입니다.

- **Live**: https://competitor-digest-jay-1779945070.netlify.app
- 경쟁사(`/`) · 글로벌 AI 동향(`/ai`) · 금융위원회(`/fsc`) · 더존비즈온 그룹(`/douzone`)

GitHub Actions cron이 Python 스크립트로 뉴스를 수집·검증하고, OpenAI API로 한국어 다이제스트를 작성한 뒤, Netlify에 정적 사이트로 배포하고 카카오톡·이메일로 알립니다.

## 핵심 설계 원칙

> **LLM은 글쓰기만 한다. URL 발견·검증·HTML 렌더는 전부 결정론적 코드가 한다.**

LLM 기반 자동화의 두 가지 고질적 실패 — **할루시네이션**(존재하지 않는 기사 인용)과 **조용한 실패**(로그 없이 생성 누락) — 를 구조적으로 제거하기 위한 원칙입니다.

- 기사 URL은 코드가 수집하고 HTTP로 실재를 검증한 것만 LLM에 전달
- LLM 출력은 구조화 JSON(`response_format=json_schema`)으로만 받고, 화이트리스트 밖 URL은 코드가 한 번 더 제거
- HTML은 코드가 템플릿으로 렌더 (LLM이 마크업을 쓰지 않음)
- 배포 전 `verify_links.py` 게이트: 인용 링크가 목록/검색/블로그 페이지면 배포 차단
- 모든 단계가 GitHub Actions 로그에 남음 + 별도 워치독이 매일 발행 여부를 사후 점검

## 일일 타임라인 (KST)

```
04:00  douzone.yml    ─┐
05:00  fsc.yml         ├─ 수집 → URL 검증 → 전일 대비 dedup → OpenAI 작성(JSON)
06:00  ai.yml          │  → 템플릿 렌더 → verify_links 게이트 → push
07:00  competitor.yml ─┘
         ↓ push가 deploy.yml 트리거 → Netlify 배포
~07:06 notify.yml      경쟁사 배포 성공 시 카카오톡 + Gmail 1통(4섹션)
07:50  check-digests.yml  4종 manifest 신선도 점검, 누락 시 경보 메일(워치독)
```

## 다이제스트별 구성

| 다이제스트 | 경로 | 뉴스 소스 | 설정 파일 |
|---|---|---|---|
| 경쟁사 | `/` | 네이버 뉴스 검색 API | `scripts/competitor/companies.json` |
| 더존 | `/douzone` | 네이버 뉴스 검색 API | `scripts/douzone/config.json` |
| FSC | `/fsc` | fsc.go.kr 게시판 직접 파싱 | `scripts/fsc/config.json` |
| AI | `/ai` | 영문 테크/금융 RSS 7개 | `scripts/ai/config.json` |

모니터링 대상(회사·카테고리·게시판·피드)의 추가/제거는 각 `config.json`만 수정하면 됩니다. 사이드바 앵커도 config 기반으로 자동 생성됩니다.

## 저장소 구조

```
scripts/
  lib/digestlib.py          # 4종 공유 라이브러리(수집·검증·dedup·OpenAI·manifest)
  competitor/ douzone/ fsc/ ai/   # 다이제스트별 config + generate.py
.github/
  workflows/                # 생성 4종(cron) + deploy + notify + weekly-notify + 워치독
  scripts/
    verify_links.py         # 인용 링크 결정론 게이트 (배포 차단)
    notify.py               # 카카오톡 + Gmail 알림 (+ Kakao refresh_token 자동 rotate)
    weekly_notify.py        # 주간 리포트 알림 (별도 시스템에서 workflow_dispatch로 트리거)
    check_digests.py        # 신선도 워치독
index.html · archive/ · ai/ · fsc/ · douzone/   # 발행된 정적 사이트 (일자별 아카이브)
```

## 기술 스택

- **정적 사이트**: HTML/CSS/Vanilla JS (빌드 도구 없음), 일자별 아카이브 + `manifest.json`
- **생성**: Python (표준 라이브러리 중심) + OpenAI API
- **자동화**: GitHub Actions (cron·workflow_run 이벤트 체인), Netlify CLI 배포
- **알림**: Kakao REST API (refresh_token 자동 회전 → GitHub Secret 갱신), Gmail SMTP

## 설정 (fork해서 쓰는 경우)

코드에는 자격증명이 없습니다. 전부 GitHub Actions Secrets로 주입합니다:

| Secret | 용도 |
|---|---|
| `OPENAI_API_KEY` / `OPENAI_MODEL` | 다이제스트 작성 |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 네이버 뉴스 검색 API |
| `ADMIN_PAT` | 생성 워크플로 push용 PAT — 기본 `GITHUB_TOKEN` push는 후속 워크플로(deploy/notify)를 트리거하지 않으므로 필수 |
| `NETLIFY_AUTH_TOKEN` | Netlify 배포 |
| `KAKAO_REST_API_KEY` / `KAKAO_REFRESH_TOKEN` | 카카오톡 알림 |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` / `GMAIL_EXTRA_RECIPIENTS` | 이메일 알림 |
| `WEEKLY_PASSWORD` | 주간 리포트 알림 메시지에 포함할 접속 안내(선택) |

로컬 테스트:

```bash
export OPENAI_API_KEY=… NAVER_CLIENT_ID=… NAVER_CLIENT_SECRET=… OPENAI_MODEL=gpt-5.1
python3 scripts/competitor/generate.py --dry-run    # 수집·검증만
python3 scripts/competitor/generate.py --no-openai  # 빈 empty-state 렌더
python3 scripts/competitor/generate.py              # 전체 (파일만 생성, push 안 함)
```

## 운영에서 배운 것들

- **GitHub Actions cron은 혼잡 시간대 ~1시간 지연이 상시**입니다. 지연을 전제로 후속 시스템을 설계해야 합니다.
- **OpenAI 조직 IP allowlist는 GH Actions와 양립 불가** — 러너 대역이 CIDR 7,000+개·매주 갱신이라 등록이 불가능합니다. IP 제한 없는 별도 프로젝트의 키를 쓰는 것이 해법입니다(project-level coverage가 org-level을 override).
- **API 크레딧은 조용히 소진됩니다.** 여러 파이프라인이 키 하나를 공유하면 잔액 0 = 전체 동시 실패. 사후 감지(워치독)와 별개로 provider의 usage-limit 알림 설정이 유일한 예방책입니다.
- 실패한 날의 백필은 **순차 실행**으로 — 알림을 트리거하는 파이프라인을 마지막에 두어야 모든 섹션이 채워진 알림이 한 번만 나갑니다.

자세한 운영 문서는 [CLAUDE.md](CLAUDE.md)를 참고하세요.
