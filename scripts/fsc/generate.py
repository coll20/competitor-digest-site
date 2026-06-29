#!/usr/bin/env python3
"""
FSC (금융위원회) digest generator — fetches fsc.go.kr boards directly (not Naver),
OpenAI writes per-board cards + industry implications. Same architecture as others.

Env: OPENAI_API_KEY, OPENAI_MODEL, TODAY(opt)  (no Naver needed)
Usage: python generate.py [--dry-run | --no-openai]
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import digestlib as L  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SUB = os.path.join(REPO, "fsc")
ARCHIVE_DIR = os.path.join(SUB, "archive")
MANIFEST = os.path.join(ARCHIVE_DIR, "manifest.json")
FSC = "https://www.fsc.go.kr"

esc = L.esc
log = L.log

POST_RE = re.compile(r'href="(/no\d+/(\d+))[^"]*"\s+title="([^"]*)"')
DAY_RE = re.compile(r'class="day">\s*(\d{4}-\d{2}-\d{2})')


def fetch_board(board, window_start, today):
    """Parse a board list page → [{board_id, board_name, url, post_id, title, date}] within window."""
    url = FSC + board["path"]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (digest)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", "ignore")
    except Exception as e:
        log(f"    ! board fetch failed {board['id']}: {e}")
        return []
    out, seen = [], set()
    for li in html.split("<li>"):
        m = POST_RE.search(li)
        if not m:
            continue
        path, pid, title = m.group(1), m.group(2), m.group(3)
        d = DAY_RE.search(li)
        date = d.group(1) if d else ""
        if date and (date < window_start or date > today):
            continue
        if pid in seen:
            continue
        seen.add(pid)
        title = re.sub(r"\s+", " ", title).replace("&quot;", '"').replace("&amp;", "&").strip()
        out.append({"board_id": board["id"], "board_name": board["name"],
                    "url": f"{FSC}{board['path']}/{pid}", "post_id": pid,
                    "title": title, "date": date})
    return out


SYSTEM_PROMPT = """You are a Korean editor writing a daily digest of South Korea's 금융위원회(FSC) 알림마당
for a credit-bureau / fintech audience. You receive VERIFIED posts (real fsc.go.kr post URLs) grouped by
board, split into NEW (not in yesterday's digest) and ALREADY_COVERED.

Write in KOREAN. Rules:
- Use ONLY the urls in the provided posts. NEVER invent/modify a URL.
- For each NEW post worth showing, write a card: summary 2-3 sentences + industry_implication (1 sentence,
  신용평가/기업데이터/핀테크 업계 함의). Keep the post's board_id.
- SELECTION: 보도자료·보도설명·새소식·금융위/증선위 의결 위주로 뉴스가치 있는 것. 게시판당 최대 3개, 전체 최대 12개.
- ⚠️ PDF/이미지 위주 게시판(금융위/증선위 의결, 금융지표, 카드뉴스)은 제목·안건명만 보수적으로 요약(첨부문서 추측·날조 금지).
- A board with zero selected NEW posts → no card (renderer shows honest empty-state with the board link).
- ceo_top3: 3 most important for the industry (prefer NEW; fill ALREADY_COVERED w/ cumulative=true).
- insight: 4-5 synthesis bullets {tag, text} (신용평가·기업데이터·핀테크 업계 함의 종합).
- recap: 1-line summaries of ALREADY_COVERED (max 12).
- headline <=120 Korean chars; conclusion = '한 줄 결론'.
- Every card/ceo/recap carries source_name (default "금융위원회") + real url + date.
Be conservative; never fabricate post contents you were not given."""

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["cards", "ceo_top3", "insight", "recap", "headline", "conclusion"],
    "properties": {
        "cards": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["board_id", "url", "title", "date", "date_class", "source_name", "summary", "industry_implication"],
            "properties": {
                "board_id": {"type": "string"}, "url": {"type": "string"}, "title": {"type": "string"},
                "date": {"type": "string"}, "date_class": {"type": "string", "enum": ["fresh", "near"]},
                "source_name": {"type": "string"}, "summary": {"type": "string"},
                "industry_implication": {"type": "string"}}}},
        "ceo_top3": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["title", "url", "date", "source_name", "desc", "urgency", "cumulative"],
            "properties": {
                "title": {"type": "string"}, "url": {"type": "string"}, "date": {"type": "string"},
                "source_name": {"type": "string"}, "desc": {"type": "string"},
                "urgency": {"type": "string", "enum": ["high", "midhigh", "mid", "low"]},
                "cumulative": {"type": "boolean"}}}},
        "insight": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["tag", "text"],
            "properties": {"tag": {"type": "string"}, "text": {"type": "string"}}}},
        "recap": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["board_id", "url", "title", "date", "source_name", "summary"],
            "properties": {
                "board_id": {"type": "string"}, "url": {"type": "string"}, "title": {"type": "string"},
                "date": {"type": "string"}, "source_name": {"type": "string"}, "summary": {"type": "string"}}}},
        "headline": {"type": "string"}, "conclusion": {"type": "string"},
    },
}

URG = {"high": "High", "midhigh": "Mid-High", "mid": "Mid", "low": "Low"}


def render_page(today, data, boards, archived):
    by = {}
    for c in data.get("cards", []):
        by.setdefault(c["board_id"], []).append(c)
    bmeta = {b["id"]: b for b in boards}

    eyebrow = (f'<span class="eyebrow archived">🗄️ ARCHIVED · {today}</span>' if archived
               else f'<span class="eyebrow">🟢 LATEST · {today}</span>')
    title = (f"금융위원회 동향 다이제스트 ({today})" if archived
             else "금융위원회 동향 다이제스트 (최신)")
    page_date = today if archived else ""

    nav = "".join(f'      <li><a href="#{b["id"]}">{b["emoji"]} {b["name"]}</a></li>\n' for b in boards)

    ceo = ""
    for i, it in enumerate(data.get("ceo_top3", [])[:3], 1):
        cum = " (누적)" if it.get("cumulative") else ""
        ceo += f'''        <li class="ceo-item">
          <div class="ceo-num">{i}</div>
          <div class="ceo-body">
            <div class="title"><a href="{esc(it["url"])}" target="_blank" rel="noopener">{esc(it["title"])}</a> <span style="color:var(--text-dim);font-weight:500;font-size:13px;">({esc(it["date"])}){cum}</span><span class="src-tag">{esc(it["source_name"])}</span></div>
            <div class="desc">{esc(it["desc"])}</div>
          </div>
          <span class="urgency {esc(it["urgency"])}">{URG.get(it["urgency"],"Mid")}</span>
        </li>
'''
    if not ceo:
        ceo = '        <li class="ceo-item"><div class="ceo-body"><div class="desc">오늘 신규 동향 없음 — 하단 누적 참조.</div></div></li>\n'

    sections = ""
    for b in boards:
        body = ""
        for k in by.get(b["id"], []):
            badge = " 🆕" if k["date_class"] == "fresh" else ""
            body += f'''      <article class="card">
        <div class="card-meta"><span class="source-chip">{esc(b["name"])} · {esc(k["source_name"])}</span><span class="date-chip {esc(k["date_class"])}">{esc(k["date"])}{badge}</span></div>
        <h3 class="card-title"><a href="{esc(k["url"])}" target="_blank" rel="noopener">{esc(k["title"])}</a></h3>
        <p class="card-summary">{esc(k["summary"])}</p>
        <div class="card-insight"><strong>💡 업계 함의:</strong> {esc(k["industry_implication"])}</div>
      </article>
'''
        if not body:
            body = f'      <div class="empty-state">이번 윈도우 내 신규 게시물 미확인. 최신: <a href="{FSC}{b["path"]}" target="_blank" rel="noopener">{esc(b["name"])} 게시판 ↗</a></div>\n'
        sections += f'''    <section id="{b["id"]}" class="company">
      <div class="company-head">
        <span class="company-num">{b["emoji"]}</span>
        <h2 class="company-name">{esc(b["name"])}</h2>
        <span class="company-sub">{esc(b["sub"])}</span>
        <a class="board-link" href="{FSC}{b["path"]}" target="_blank" rel="noopener">게시판 전체 ↗</a>
      </div>
{body}    </section>

'''

    ins = ""
    for it in data.get("insight", []):
        ins += f'        <li class="insight-item"><span class="tag">{esc(it["tag"])}</span>{esc(it["text"])}</li>\n'
    if not ins:
        ins = '        <li class="insight-item">이번 주 종합 함의 항목 없음.</li>\n'

    bname = {b["id"]: b["name"] for b in boards}
    recap = ""
    for r in data.get("recap", [])[:12]:
        recap += f'''        <li><strong>{esc(bname.get(r["board_id"], r["board_id"]))}</strong> · <a class="recap-link" href="{esc(r["url"])}" target="_blank" rel="noopener">{esc(r["title"])}</a>: {esc(r["summary"])} <span style="color:var(--text-dim);font-size:12px;">({esc(r["source_name"])} · {esc(r["date"])})</span></li>
'''
    if not recap:
        recap = "        <li>이번 주 누적 항목 없음.</li>\n"

    src_seen, src = set(), ""
    for it in (data.get("ceo_top3", []) + data.get("cards", []) + data.get("recap", [])):
        if it["url"] in src_seen:
            continue
        src_seen.add(it["url"])
        src += f'''        <li><a href="{esc(it["url"])}" target="_blank" rel="noopener">{esc(it["title"])} ({esc(it["source_name"])})</a><span class="src-date">{esc(it["date"])}</span></li>
'''

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(today)} 금융위원회(FSC) 알림마당 일일 동향 — {esc(data.get("headline",""))}">
<link rel="stylesheet" href="/fsc/styles.css">
</head>
<body data-page-date="{page_date}">
<div class="app">

  <button class="sidebar-toggle" type="button">목차 / 아카이브 ▾</button>

  <aside class="sidebar" aria-label="목차 및 아카이브">
    <div class="sidebar-brand">FSC WATCH</div>
    <div class="sidebar-title">금융위원회 동향 다이제스트</div>
    <a class="sidebar-switch" href="/">📊 경쟁사 동향 다이제스트로 →</a>
    <a class="sidebar-switch" href="/ai/">🤖 글로벌 AI 기술 동향으로 →</a>
    <a class="sidebar-switch" href="/douzone/">🏢 더존비즈온 동향으로 →</a>

    <h3>이 페이지에서</h3>
    <ul class="sidebar-nav">
      <li><a href="#ceo">🎯 오늘의 핵심</a></li>
{nav}      <li><a href="#insight">💡 업계 함의 종합</a></li>
      <li><a href="#recap">📚 이번 주 누적</a></li>
      <li><a href="#sources">Sources</a></li>
    </ul>

    <h3>일자별 아카이브</h3>
    <ul class="archive-list" id="archive-list"></ul>
    <p class="archive-empty" id="archive-empty">로드 중…</p>
  </aside>

  <main class="content">

    <header class="hero">
      {eyebrow}
      <h1>금융위원회 동향 다이제스트</h1>
      <p class="meta">기준일: <strong>{today}</strong> · 금융위 알림마당 9개 게시판: 보도자료 · 보도설명 · 새소식 · 금융위/증선위 의결 · 제재정보 · 금융시장동향 · 금융지표 · 카드뉴스</p>
    </header>

    <div class="notice">
      <strong>금융위원회 알림마당 일일 모니터링.</strong> <strong>금융위원회(FSC)</strong> 알림마당의 신규 게시물을 게시판별로 정리하고, 각 항목에 <strong>신용평가·핀테크 업계 함의</strong>를 답니다. 모든 항목은 <strong>원문(fsc.go.kr) 개별 게시물</strong>로 직접 연결됩니다. 이전 다이제스트에서 다룬 항목은 하단 <strong>이번 주 누적</strong>으로 이동합니다.
    </div>

    <section id="ceo" class="ceo-brief" aria-labelledby="ceo-title">
      <h2 id="ceo-title"><span class="icon">🎯</span> 오늘의 핵심</h2>
      <p class="subtitle">신용평가·핀테크 업계 관점에서 {today} 기준 가장 중요한 항목</p>
      <ol class="ceo-list">
{ceo}      </ol>
      <div class="ceo-conclusion"><strong>한 줄 결론 —</strong> {esc(data.get("conclusion",""))}</div>
    </section>

{sections}    <section id="insight" class="insight-section" aria-labelledby="insight-title">
      <h2 id="insight-title">💡 신용평가·핀테크 업계 함의 종합</h2>
      <p class="subtitle">금융위 동향이 신용평가·기업데이터·핀테크 업계에 던지는 함의</p>
      <ul class="insight-list">
{ins}      </ul>
    </section>

    <section id="recap" class="company">
      <div class="company-head">
        <span class="company-num">📚</span>
        <h2 class="company-name">이번 주 누적 주요 동향</h2>
        <span class="company-sub">이전 다이제스트에서 이미 다룬 항목 — 1줄 요약</span>
      </div>
      <ul class="recap-list">
{recap}      </ul>
    </section>

    <section id="sources" class="sources">
      <h2>Sources (원문 링크 · fsc.go.kr 개별 게시물)</h2>
      <ul>
{src}      </ul>
    </section>

    <footer class="page-footer">
      Generated {today} · 매일 KST 오전 5시 자동 갱신 · 출처: <a href="https://www.fsc.go.kr/no010101" target="_blank" rel="noopener">금융위원회 알림마당</a> · <a href="/">경쟁사 동향</a> · <a href="/ai/">글로벌 AI 동향</a>
    </footer>

  </main>
</div>
<script src="/fsc/sidebar.js"></script>
</body>
</html>
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-openai", action="store_true")
    args = ap.parse_args()

    cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    boards = cfg["boards"]
    today = L.today_str()
    window_start = (dt.datetime.strptime(today, "%Y-%m-%d") - dt.timedelta(days=cfg["window_days"])).strftime("%Y-%m-%d")

    pset, prev_date = L.prev_urls(ARCHIVE_DIR, MANIFEST, today)
    log(f"[*] today={today} window_start={window_start} prev={prev_date} prev_urls={len(pset)}")

    posts, allowed = [], set()
    for b in boards:
        items = fetch_board(b, window_start, today)
        log(f"[*] {b['id']}: {len(items)} posts in window")
        for it in items:
            allowed.add(it["url"])
            posts.append(it)
    new = [p for p in posts if p["url"] not in pset]
    covered = [p for p in posts if p["url"] in pset]
    log(f"[*] total posts={len(posts)}  NEW={len(new)}  ALREADY_COVERED={len(covered)}")

    if args.dry_run:
        for p in new:
            log(f"   NEW [{p['board_id']}] {p['date']} {p['title'][:60]} {p['url']}")
        return

    if args.no_openai:
        data = {"cards": [], "ceo_top3": [], "insight": [], "recap": [],
                "headline": f"{today} 금융위 신규 게시물 정리.", "conclusion": "자동 생성(LLM 미사용)."}
    else:
        payload = {"today": today, "prev_digest_date": prev_date,
                   "NEW": [{"board_id": p["board_id"], "board_name": p["board_name"], "url": p["url"],
                            "title": p["title"], "date": p["date"]} for p in new],
                   "ALREADY_COVERED": [{"board_id": p["board_id"], "url": p["url"], "title": p["title"],
                                        "date": p["date"]} for p in covered]}
        log("[*] OpenAI composing…")
        data = L.openai_compose(SYSTEM_PROMPT, payload, SCHEMA, "fsc_digest")
        data = L.enforce_url_whitelist(data, allowed, ["cards", "ceo_top3", "recap"])

    with open(os.path.join(ARCHIVE_DIR, f"{today}.html"), "w", encoding="utf-8") as f:
        f.write(render_page(today, data, boards, archived=True))
    with open(os.path.join(SUB, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_page(today, data, boards, archived=False))
    L.update_manifest(MANIFEST, today, f"금융위원회 동향 다이제스트 — {today}",
                      data.get("headline", f"{today} 금융위 동향"))
    log(f"[✓] wrote fsc archive/{today}.html + index.html + manifest "
        f"(cards={len(data.get('cards',[]))} ceo={len(data.get('ceo_top3',[]))} recap={len(data.get('recap',[]))})")


if __name__ == "__main__":
    main()
