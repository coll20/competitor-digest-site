#!/usr/bin/env python3
"""
Douzone (더존비즈온) digest generator — deterministic Naver fetch + OpenAI writing.
Single entity, classified into 6 topic categories. Same architecture as competitor.

Env: NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, OPENAI_API_KEY, OPENAI_MODEL, TODAY(opt)
Usage: python generate.py [--dry-run | --no-openai]
"""
import argparse
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import digestlib as L  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SUB = os.path.join(REPO, "douzone")
ARCHIVE_DIR = os.path.join(SUB, "archive")
MANIFEST = os.path.join(ARCHIVE_DIR, "manifest.json")

esc = L.esc
log = L.log

SYSTEM_PROMPT = """You are a Korean editor for TechFin Ratings writing a daily digest about the 더존비즈온 group
(parent of TechFin Ratings) viewed through fintech / enterprise-data / AI / credit lenses.
You receive VERIFIED news candidates (each with a real article URL) about 더존비즈온 and affiliates,
split into NEW (not in yesterday's digest) and ALREADY_COVERED.

Write in KOREAN. Rules:
- Use ONLY the urls in the provided candidates. NEVER invent/modify a URL.
- Classify each selected item into exactly one category: biz / fintech / data / ai / platform / group.
- SELECTION (중요): 신규 후보가 많아도 '진짜 뉴스가치 있는 더존 그룹의 사건'만 카드로. 카테고리당 최대 3개,
  전체 최대 12개. 같은 사건을 여러 매체가 보도하면 1개 카드로 합치고 가장 신뢰도 높은 URL 1개만 쓴다.
  제외: 단순 주가·거래소 시세/수급 나열, 더존이 스쳐 지나가듯 언급된 기사, 광고·반복·무관 기사.
- 선택한 NEW 항목만 카드 (summary 2-3 sentences; techfin_implication = 1 sentence, TechFin Ratings 관점 함의).
- A category with zero selected items gets no card (renderer shows honest empty-state).
- ceo_top3: 3 most important items (prefer NEW; fill from ALREADY_COVERED with cumulative=true if needed).
- insight: 4-5 synthesis bullets {tag, text} on what the week means for TechFin Ratings assets
  (월 세무/상거래 데이터, CPS, GNN 부도예측, EWS, 크레디뷰, AI 경영진단).
- recap: 1-line summaries of ALREADY_COVERED items (max 12).
- headline <=120 Korean chars; conclusion = one '한 줄 결론'.
- Every card/ceo/recap carries source_name (매체명) + real url + date.

CRITICAL anti-fabrication facts (do NOT contradict; do NOT present as fresh news):
1. 더존비즈온은 2026년 EQT 공개매수로 자진 상장폐지/비상장 PE 전환(2~3월 사건). EQT/상폐/공개매수를 '오늘의 신규 호재'로 쓰지 말 것 — 6/30 주식교환 같은 일정 후속만 사실대로.
2. 제4 인터넷은행('더존뱅크') 컨소시엄은 2025-03 철회로 종료. '인뱅 인가' 류 가짜 최신성 금지(fintech 정직 empty-state 허용).
3. 테크핀레이팅스 = 더존 핀테크 계열사 본인 → '계열사 동향'으로 수록하되 함의는 자사 포지셔닝 관점.
Be conservative; do not fabricate. 더존은 신규 보도가 적을 수 있으니 빈 카테고리는 정직하게 비운다."""

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["cards", "ceo_top3", "insight", "recap", "headline", "conclusion"],
    "properties": {
        "cards": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["category", "url", "title", "date", "date_class", "source_name", "summary", "techfin_implication"],
            "properties": {
                "category": {"type": "string", "enum": ["biz", "fintech", "data", "ai", "platform", "group"]},
                "url": {"type": "string"}, "title": {"type": "string"}, "date": {"type": "string"},
                "date_class": {"type": "string", "enum": ["fresh", "near"]},
                "source_name": {"type": "string"}, "summary": {"type": "string"},
                "techfin_implication": {"type": "string"},
            }}},
        "ceo_top3": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["title", "url", "date", "source_name", "desc", "urgency", "cumulative"],
            "properties": {
                "title": {"type": "string"}, "url": {"type": "string"}, "date": {"type": "string"},
                "source_name": {"type": "string"}, "desc": {"type": "string"},
                "urgency": {"type": "string", "enum": ["high", "midhigh", "low"]},
                "cumulative": {"type": "boolean"},
            }}},
        "insight": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["tag", "text"],
            "properties": {"tag": {"type": "string"}, "text": {"type": "string"}}}},
        "recap": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["category", "url", "title", "date", "source_name", "summary"],
            "properties": {
                "category": {"type": "string"}, "url": {"type": "string"}, "title": {"type": "string"},
                "date": {"type": "string"}, "source_name": {"type": "string"}, "summary": {"type": "string"}}}},
        "headline": {"type": "string"}, "conclusion": {"type": "string"},
    },
}

URG = {"high": "High", "midhigh": "Mid-High", "low": "Low"}


def render_page(today, data, cats, archived):
    by = {}
    for c in data.get("cards", []):
        by.setdefault(c["category"], []).append(c)

    eyebrow = (f'<span class="eyebrow archived">🗄️ ARCHIVED · {today}</span>' if archived
               else f'<span class="eyebrow">🟢 LATEST · {today}</span>')
    title = (f"더존비즈온 동향 다이제스트 ({today})" if archived
             else "더존비즈온 동향 다이제스트 (최신)")
    page_date = today if archived else ""

    nav = "".join(f'      <li><a href="#{c["id"]}">{c["emoji"]} {c["name"]}</a></li>\n' for c in cats)

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
    for c in cats:
        body = ""
        for k in by.get(c["id"], []):
            badge = " 🆕" if k["date_class"] == "fresh" else ""
            body += f'''      <article class="card">
        <div class="card-meta"><span class="source-chip">{esc(k["source_name"])}</span><span class="date-chip {esc(k["date_class"])}">{esc(k["date"])}{badge}</span></div>
        <h3 class="card-title"><a href="{esc(k["url"])}" target="_blank" rel="noopener">{esc(k["title"])}</a></h3>
        <p class="card-summary">{esc(k["summary"])}</p>
        <div class="card-insight"><strong>💡 테크핀 함의:</strong> {esc(k["techfin_implication"])}</div>
      </article>
'''
        if not body:
            body = '      <div class="empty-state"><strong>이번 윈도우 내 검증 가능한 신규 보도 없음.</strong> 관련 누적 항목은 하단 <a href="#recap">📚 누적</a> 참조.</div>\n'
        sections += f'''    <section id="{c["id"]}" class="company">
      <div class="company-head">
        <span class="company-num">{c["emoji"]}</span>
        <h2 class="company-name">{esc(c["name"])}</h2>
        <span class="company-sub">{esc(c["sub"])}</span>
      </div>
{body}    </section>

'''

    ins = ""
    for it in data.get("insight", []):
        ins += f'        <li class="insight-item"><span class="tag">{esc(it["tag"])}</span>{esc(it["text"])}</li>\n'
    if not ins:
        ins = '        <li class="insight-item">이번 주 종합 함의 항목 없음.</li>\n'

    cat_name = {c["id"]: c["name"] for c in cats}
    recap = ""
    for r in data.get("recap", [])[:12]:
        recap += f'''        <li><strong>[{esc(cat_name.get(r["category"], r["category"]))}]</strong> <a class="recap-link" href="{esc(r["url"])}" target="_blank" rel="noopener">{esc(r["title"])}</a>: {esc(r["summary"])} <span>{esc(r["source_name"])} · {esc(r["date"])}</span></li>
'''
    if not recap:
        recap = "        <li>이번 주 누적 항목 없음.</li>\n"

    src_seen, src = set(), ""
    for it in (data.get("ceo_top3", []) + data.get("cards", []) + data.get("recap", [])):
        if it["url"] in src_seen:
            continue
        src_seen.add(it["url"])
        src += f'''        <li><a href="{esc(it["url"])}" target="_blank" rel="noopener">{esc(it["title"])} — {esc(it["source_name"])}</a><span class="src-date">{esc(it["date"])}</span></li>
'''

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(today)} 더존비즈온 및 계열사 동향 — 핀테크·기업데이터·AI 중심. {esc(data.get("headline",""))}">
<link rel="stylesheet" href="/douzone/styles.css">
</head>
<body data-page-date="{page_date}">
<div class="app">

  <button class="sidebar-toggle" type="button">목차 / 아카이브 ▾</button>

  <aside class="sidebar" aria-label="목차 및 아카이브">
    <div class="sidebar-brand">DOUZONE INTEL</div>
    <div class="sidebar-title">더존비즈온 동향 다이제스트</div>
    <a class="sidebar-switch" href="/">📊 경쟁사 동향 다이제스트로 →</a>
    <a class="sidebar-switch" href="/ai/">🤖 글로벌 AI 기술 동향으로 →</a>
    <a class="sidebar-switch" href="/fsc/">🏛️ 금융위원회 동향으로 →</a>

    <h3>이 페이지에서</h3>
    <ul class="sidebar-nav">
      <li><a href="#ceo">🎯 오늘의 핵심</a></li>
{nav}      <li><a href="#insight">💡 테크핀 함의 종합</a></li>
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
      <h1>더존비즈온 동향 다이제스트</h1>
      <p class="meta">대상: <strong>더존비즈온 + 계열사</strong> · 관점: <strong>핀테크·기업데이터·AI·신용</strong> 중심 · 기준일: <strong>{today}</strong></p>
    </header>

    <div class="notice">
      <strong>더존비즈온 그룹 일일 모니터링.</strong> 핀테크·기업데이터·AI·신용 관점으로 6개 카테고리에 정리하고, 각 항목에 <strong>💡 테크핀레이팅스 함의</strong>를 답니다. 모든 항목은 <strong>검증된 실제 기사 URL</strong>로 연결됩니다. 이전 다이제스트에서 다룬 항목은 하단 <strong>이번 주 누적</strong>으로 이동합니다.
    </div>

    <section id="ceo" class="ceo-brief" aria-labelledby="ceo-title">
      <h2 id="ceo-title"><span class="icon">🎯</span> 오늘의 핵심</h2>
      <p class="subtitle">테크핀레이팅스 관점에서 가장 중요한 3가지</p>
      <ol class="ceo-list">
{ceo}      </ol>
      <div class="ceo-conclusion"><strong>한 줄 결론 —</strong> {esc(data.get("conclusion",""))}</div>
    </section>

{sections}    <section id="insight" class="insight-section" aria-labelledby="insight-title">
      <h2 id="insight-title">💡 테크핀레이팅스 함의 종합</h2>
      <p class="subtitle">더존 그룹 동향이 테크핀레이팅스에 던지는 함의</p>
      <ul class="insight-list">
{ins}      </ul>
    </section>

    <section id="recap" class="company">
      <div class="company-head">
        <span class="company-num">📚</span>
        <h2 class="company-name">이번 주 누적 / 30일 이내 기수록 주요 동향</h2>
        <span class="company-sub">기수록 항목 — 1줄 요약</span>
      </div>
      <ul class="recap-list">
{recap}      </ul>
    </section>

    <section id="sources" class="sources">
      <h2>Sources</h2>
      <ul>
{src}      </ul>
    </section>

    <footer class="page-footer">
      Generated {today} · 매일 KST 오전 4시 자동 갱신 · 더존비즈온 그룹(핀테크·데이터·AI 중심) · <a href="/">경쟁사 동향</a> · <a href="/ai/">글로벌 AI 동향</a> · <a href="/fsc/">금융위 동향</a>
    </footer>

  </main>
</div>
<script src="/douzone/sidebar.js"></script>
</body>
</html>
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-openai", action="store_true")
    args = ap.parse_args()

    cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    cats = cfg["categories"]
    today = L.today_str()
    creds = (os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET"))
    if not all(creds):
        log("FATAL: NAVER creds missing"); sys.exit(2)

    pset, prev_date = L.prev_urls(ARCHIVE_DIR, MANIFEST, today)
    log(f"[*] today={today} prev={prev_date} prev_urls={len(pset)}")

    cands = L.naver_candidates(cfg["queries"], cfg["match"], creds, cfg["window_days"])
    log(f"[*] {len(cands)} candidates after window/host/name filter; verifying…")
    new, covered, allowed = [], [], set()
    for c in cands:
        ok, why = L.verify_url(c["url"])
        if not ok:
            log(f"    - drop {c['url']} ({why})"); continue
        allowed.add(c["url"])
        (covered if c["url"] in pset else new).append(c)
    log(f"[*] NEW={len(new)} ALREADY_COVERED={len(covered)}")

    if args.dry_run:
        for n in new:
            log(f"   NEW {n['date']} {n['title'][:64]} {n['url']}")
        return

    if args.no_openai:
        data = {"cards": [], "ceo_top3": [], "insight": [], "recap": [],
                "headline": f"{today} 더존 신규 보도 미확인.", "conclusion": "신규 없음 — 누적 참조."}
    else:
        payload = {"today": today, "prev_digest_date": prev_date,
                   "NEW": [{"url": x["url"], "title": x["title"], "date": x["date"], "desc": x["desc"]} for x in new],
                   "ALREADY_COVERED": [{"url": x["url"], "title": x["title"], "date": x["date"], "desc": x["desc"]} for x in covered]}
        log("[*] OpenAI composing…")
        data = L.openai_compose(SYSTEM_PROMPT, payload, SCHEMA, "douzone_digest")
        data = L.enforce_url_whitelist(data, allowed, ["cards", "ceo_top3", "recap"])

    with open(os.path.join(ARCHIVE_DIR, f"{today}.html"), "w", encoding="utf-8") as f:
        f.write(render_page(today, data, cats, archived=True))
    with open(os.path.join(SUB, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_page(today, data, cats, archived=False))
    L.update_manifest(MANIFEST, today, f"더존비즈온 동향 다이제스트 — {today}",
                      data.get("headline", f"{today} 더존 동향"))
    log(f"[✓] wrote douzone archive/{today}.html + index.html + manifest "
        f"(cards={len(data.get('cards',[]))} ceo={len(data.get('ceo_top3',[]))} recap={len(data.get('recap',[]))})")


if __name__ == "__main__":
    main()
