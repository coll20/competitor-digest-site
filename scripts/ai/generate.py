#!/usr/bin/env python3
"""
Global AI digest generator — English tech/finance RSS feeds + OpenAI writing.
5 fixed areas + CEO top3 + TechFin insight + recap + a Korean detail page.

Env: OPENAI_API_KEY, OPENAI_MODEL, TODAY(opt)   (no Naver needed)
Usage: python generate.py [--dry-run | --no-openai]
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import digestlib as L  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SUB = os.path.join(REPO, "ai")
ARCHIVE_DIR = os.path.join(SUB, "archive")
MANIFEST = os.path.join(ARCHIVE_DIR, "manifest.json")

esc = L.esc
log = L.log


# ------------------------------------------------------------------ RSS fetch
def _txt(el):
    return (el.text or "").strip() if el is not None else ""


def parse_any_date(s):
    s = (s or "").strip()
    if not s:
        return None
    d = L.parse_pub(s)
    if d:
        return d
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(L.KST)
    except Exception:
        return None


def fetch_feed(url):
    """Return [{title,url,desc,date}] from an RSS2.0 or Atom feed."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (digest)"})
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read()
        root = ET.fromstring(raw)
    except Exception as e:
        log(f"    ! feed failed {url}: {e}")
        return []
    out = []
    # RSS 2.0
    for it in root.iter("item"):
        link = _txt(it.find("link"))
        d = parse_any_date(_txt(it.find("pubDate")))
        out.append({"title": _txt(it.find("title")), "url": link,
                    "desc": re.sub(r"<.*?>", "", _txt(it.find("description")))[:500], "date": d})
    # Atom
    ns = "{http://www.w3.org/2005/Atom}"
    for it in root.iter(ns + "entry"):
        link = ""
        for ln in it.findall(ns + "link"):
            if ln.get("rel") in (None, "alternate") and ln.get("href"):
                link = ln.get("href"); break
        d = parse_any_date(_txt(it.find(ns + "updated")) or _txt(it.find(ns + "published")))
        summ = _txt(it.find(ns + "summary")) or _txt(it.find(ns + "content"))
        out.append({"title": _txt(it.find(ns + "title")), "url": link,
                    "desc": re.sub(r"<.*?>", "", summ)[:500], "date": d})
    return out


def gather(feeds, window_days, today):
    start = today - dt.timedelta(days=window_days)
    seen, cands = set(), []
    for f in feeds:
        for it in fetch_feed(f):
            u = (it["url"] or "").strip()
            if not u or u in seen:
                continue
            host = u.split("/")[2].lower() if "://" in u else ""
            if any(b in host for b in L.BLOCKED_HOSTS):
                continue
            if it["date"] and it["date"] < start:
                continue
            seen.add(u)
            it["date_str"] = it["date"].strftime("%Y-%m-%d") if it["date"] else ""
            cands.append(it)
    cands.sort(key=lambda x: x.get("date_str", ""), reverse=True)
    return cands


# ------------------------------------------------------------------ OpenAI
SYSTEM_PROMPT = """You are a Korean editor for TechFin Ratings writing a daily GLOBAL AI tech digest.
You receive VERIFIED English news candidates (each a real article URL) from tech/finance RSS feeds,
split into NEW (not in yesterday's digest) and ALREADY_COVERED.

Write in KOREAN. Rules:
- Use ONLY the urls in the provided candidates. NEVER invent/modify a URL. Drop non-AI/off-topic items.
- Classify each selected item into exactly one area: frontier / infra / agents / finance / policy.
- SELECTION: 영역당 최대 2~3개, 전체 최대 10개. 같은 사건 중복 매체는 1개로 합쳐 최선 URL 1개만.
  finance(금융·신용·핀테크 AI)는 최우선 — 가능하면 2건 이상 확보.
- Each selected item = card: title_ko, title_en(원제), summary_ko(2-3문장), global_meaning_ko(1문장),
  techfin_insight_ko(1문장, TechFin Ratings 자산 관점 함의: 월세무/상거래데이터·CPS·GNN부도예측·EWS·크레디뷰·AI진단),
  ko_detail_ko(6~8문장 자체 작성 한글 상세 해설 — 원문 전문 번역 아님=저작권 안전).
- ceo_top3: 테크핀 관점 가장 중요한 3개(prefer NEW; fill ALREADY_COVERED w/ cumulative=true). 각 url은 카드 중 하나와 같게.
- insight: 4-5 synthesis bullets {tag, text}.
- recap: 1-line summaries of ALREADY_COVERED (max 12).
- headline <=120 Korean chars; conclusion = '한 줄 결론'.
- Every card/ceo/recap carries source_name (매체명) + real url + date(YYYY-MM-DD).
Be conservative; do not fabricate. 글로벌 영문 1차 소스가 primary."""

CARD_PROPS = {
    "area": {"type": "string", "enum": ["frontier", "infra", "agents", "finance", "policy"]},
    "url": {"type": "string"}, "title_ko": {"type": "string"}, "title_en": {"type": "string"},
    "source_name": {"type": "string"}, "date": {"type": "string"},
    "date_class": {"type": "string", "enum": ["fresh", "near"]},
    "summary_ko": {"type": "string"}, "global_meaning_ko": {"type": "string"},
    "techfin_insight_ko": {"type": "string"}, "ko_detail_ko": {"type": "string"},
}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["cards", "ceo_top3", "insight", "recap", "headline", "conclusion"],
    "properties": {
        "cards": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": list(CARD_PROPS.keys()), "properties": CARD_PROPS}},
        "ceo_top3": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["title_ko", "url", "date", "source_name", "desc_ko", "urgency", "cumulative"],
            "properties": {
                "title_ko": {"type": "string"}, "url": {"type": "string"}, "date": {"type": "string"},
                "source_name": {"type": "string"}, "desc_ko": {"type": "string"},
                "urgency": {"type": "string", "enum": ["high", "midhigh", "low"]},
                "cumulative": {"type": "boolean"}}}},
        "insight": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["tag", "text"],
            "properties": {"tag": {"type": "string"}, "text": {"type": "string"}}}},
        "recap": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["area", "url", "title_ko", "date", "source_name", "summary_ko"],
            "properties": {
                "area": {"type": "string"}, "url": {"type": "string"}, "title_ko": {"type": "string"},
                "date": {"type": "string"}, "source_name": {"type": "string"}, "summary_ko": {"type": "string"}}}},
        "headline": {"type": "string"}, "conclusion": {"type": "string"},
    },
}
URG = {"high": "High", "midhigh": "Mid-High", "low": "Low"}


# ------------------------------------------------------------------ render
def assign_anchors(cards, areas):
    """Deterministic anchor per card: area+index. Returns {url: anchor} and ordered per-area."""
    by, anchor_of = {}, {}
    for c in cards:
        by.setdefault(c["area"], []).append(c)
    for a in areas:
        for i, c in enumerate(by.get(a["id"], []), 1):
            anchor_of[c["url"]] = f'{a["id"]}-{i}'
    return by, anchor_of


def render_main(today, ws, data, areas, archived, anchor_of):
    by = {}
    for c in data.get("cards", []):
        by.setdefault(c["area"], []).append(c)
    kohref = f"/ai/archive/{today}-ko.html"

    eyebrow = (f'<span class="eyebrow archived">📅 ARCHIVED · {today}</span>' if archived
               else f'<span class="eyebrow">🟢 LATEST · {today}</span>')
    title = (f"{today} 글로벌 AI 기술 동향 다이제스트" if archived
             else "글로벌 AI 기술 동향 다이제스트 (최신)")
    page_date = today if archived else ""
    footer = (f'Generated {today} · <a href="/ai/">← 최신 AI 다이제스트로</a> · <a href="/">경쟁사 동향 다이제스트</a>'
              if archived else f'Generated {today} · 매일 KST 오전 6시 자동 갱신 · <a href="/">경쟁사 동향 다이제스트</a>')

    nav = "".join(f'      <li><a href="#{a["id"]}">{a["emoji"]} {a["name"].split(" ·")[0].split(" &")[0]}</a></li>\n' for a in areas)

    ceo = ""
    for i, it in enumerate(data.get("ceo_top3", [])[:3], 1):
        cum = " (누적)" if it.get("cumulative") else ""
        anc = anchor_of.get(it["url"])
        kobtn = f'\n            <div class="card-links"><a class="ko-btn" href="{kohref}#{anc}">🇰🇷 한글로 읽기</a></div>' if anc else ""
        ceo += f'''        <li class="ceo-item">
          <div class="ceo-num">{i}</div>
          <div class="ceo-body">
            <div class="title"><a href="{esc(it["url"])}" target="_blank" rel="noopener">{esc(it["title_ko"])}</a> <span style="color:var(--text-dim);font-weight:500;font-size:13px;">({esc(it["date"])}){cum}</span><span class="src-tag">{esc(it["source_name"])}</span></div>
            <div class="desc">{esc(it["desc_ko"])}</div>{kobtn}
          </div>
          <span class="urgency {esc(it["urgency"])}">{URG.get(it["urgency"],"Mid")}</span>
        </li>
'''
    if not ceo:
        ceo = '        <li class="ceo-item"><div class="ceo-body"><div class="desc">오늘 신규 동향 없음 — 하단 누적 참조.</div></div></li>\n'

    sections = ""
    for a in areas:
        body = ""
        for c in by.get(a["id"], []):
            anc = anchor_of.get(c["url"], a["id"])
            badge = " 🆕" if c["date_class"] == "fresh" else ""
            body += f'''      <article class="card" id="{anc}">
        <div class="card-meta"><span class="source-chip">{esc(c["source_name"])}</span><span class="date-chip {esc(c["date_class"])}">{esc(c["date"])}{badge}</span></div>
        <h3 class="card-title"><a href="{esc(c["url"])}" target="_blank" rel="noopener">{esc(c["title_ko"])}</a></h3>
        <p class="card-summary">{esc(c["summary_ko"])}</p>
        <div class="card-impact"><strong>글로벌 의미:</strong> {esc(c["global_meaning_ko"])}</div>
        <div class="card-insight"><strong>💡 테크핀 연관:</strong> {esc(c["techfin_insight_ko"])}</div>
        <div class="card-links"><a class="ko-btn" href="{kohref}#{anc}">🇰🇷 한글로 읽기</a></div>
      </article>
'''
        if not body:
            body = '      <div class="empty-state">이번 윈도우 내 이 영역의 신규 동향 없음 — 하단 누적 참조.</div>\n'
        sections += f'''    <section id="{a["id"]}" class="company">
      <div class="company-head">
        <span class="company-num">{a["emoji"]}</span>
        <h2 class="company-name">{esc(a["name"])}</h2>
      </div>
{body}    </section>

'''

    ins = ""
    for it in data.get("insight", []):
        ins += f'        <li class="insight-item"><span class="tag">{esc(it["tag"])}</span>{esc(it["text"])}</li>\n'
    if not ins:
        ins = '        <li class="insight-item">이번 주 종합 함의 항목 없음.</li>\n'

    aname = {a["id"]: a["name"].split(" ·")[0].split(" &")[0] for a in areas}
    aemoji = {a["id"]: a["emoji"] for a in areas}
    recap = ""
    for r in data.get("recap", [])[:12]:
        recap += f'''        <li><strong>{aemoji.get(r["area"],"")} {esc(aname.get(r["area"], r["area"]))}</strong> <a class="recap-link" href="{esc(r["url"])}" target="_blank" rel="noopener">{esc(r["title_ko"])}</a> <span>{esc(r["source_name"])} · {esc(r["date"])}</span></li>
'''
    if not recap:
        recap = "        <li>이번 주 누적 항목 없음.</li>\n"

    src_seen, src = set(), ""
    for c in data.get("cards", []):
        if c["url"] in src_seen:
            continue
        src_seen.add(c["url"])
        src += f'''        <li><a href="{esc(c["url"])}" target="_blank" rel="noopener">{esc(c.get("title_en") or c["title_ko"])} — {esc(c["source_name"])}</a><span class="src-date">{esc(c["date"])}</span></li>
'''

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(today)} 글로벌 AI 기술 동향 다이제스트 — {esc(data.get("headline",""))}">
<link rel="stylesheet" href="/ai/styles.css">
</head>
<body data-page-date="{page_date}">
<div class="app">

  <button class="sidebar-toggle" type="button">목차 / 아카이브 ▾</button>

  <aside class="sidebar" aria-label="목차 및 아카이브">
    <div class="sidebar-brand">AI TECH INTEL</div>
    <div class="sidebar-title">글로벌 AI 기술 동향 다이제스트</div>
    <a class="sidebar-switch" href="/">← 경쟁사 동향 다이제스트로</a>
    <a class="sidebar-switch" href="/fsc/">🏛️ 금융위원회 동향으로 →</a>
    <a class="sidebar-switch" href="/douzone/">🏢 더존비즈온 동향으로 →</a>

    <h3>이 페이지에서</h3>
    <ul class="sidebar-nav">
      <li><a href="#ceo">🎯 오늘의 핵심 3</a></li>
{nav}      <li><a href="#insight">💡 테크핀 인사이트</a></li>
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
      <h1>글로벌 AI 기술 동향 다이제스트</h1>
      <p class="meta">기간: <strong>{ws} ~ {today}</strong> · 5개 영역: 프론티어 모델 · 인프라/반도체 · 에이전트/오픈소스 · 금융 AI · 정책/규제</p>
    </header>

    <div class="notice">
      <strong>글로벌 기술 동향 우선.</strong> 전 세계 프론티어 랩·인프라·금융 AI·규제 흐름을 영역별로 정리합니다. 모든 항목에 <strong>출처 매체</strong>를 표기하고 <strong>💡 테크핀 연관</strong> 인사이트를 답니다. 각 항목은 <strong>🇰🇷 한글로 읽기</strong>로 상세 해설을 제공합니다. 이전 다이제스트 항목은 하단 <strong>이번 주 누적</strong>으로 이동했습니다.
    </div>

    <section id="ceo" class="ceo-brief" aria-labelledby="ceo-title">
      <h2 id="ceo-title"><span class="icon">🎯</span> 오늘의 핵심 3</h2>
      <p class="subtitle">테크핀레이팅스 관점에서 가장 중요한 3가지</p>
      <ol class="ceo-list">
{ceo}      </ol>
      <div class="ceo-conclusion"><strong>한 줄 결론 —</strong> {esc(data.get("conclusion",""))}</div>
    </section>

{sections}    <section id="insight" class="insight-section" aria-labelledby="insight-title">
      <h2 id="insight-title">💡 테크핀레이팅스 인사이트</h2>
      <p class="subtitle">이번 주 글로벌 AI 동향이 우리 회사 자산에 던지는 함의</p>
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
      <h2>Sources (실제 기사 URL)</h2>
      <ul>
{src}      </ul>
    </section>

    <footer class="page-footer">
      {footer}
    </footer>

  </main>
</div>
<script src="/ai/sidebar.js"></script>
</body>
</html>
'''


def render_ko(today, ws, data, areas, anchor_of):
    by = {}
    for c in data.get("cards", []):
        by.setdefault(c["area"], []).append(c)
    secs = ""
    for a in areas:
        cards = by.get(a["id"], [])
        if not cards:
            continue
        entries = ""
        for c in cards:
            anc = anchor_of.get(c["url"], a["id"])
            paras = "".join(f"<p>{esc(p.strip())}</p>" for p in re.split(r"(?<=[.다])\s+(?=[A-Z가-힣])", c["ko_detail_ko"]) if p.strip()) or f"<p>{esc(c['ko_detail_ko'])}</p>"
            entries += f'''      <article class="ko-entry" id="{anc}">
        <div class="ko-entry-head"><span class="source-chip">{esc(c["source_name"])}</span><span class="date-chip near">{esc(c["date"])}</span><a class="ko-orig" href="{esc(c["url"])}" target="_blank" rel="noopener">원문 보기 ↗</a></div>
        <h3 class="ko-title">{esc(c["title_ko"])}</h3>
        <div class="ko-body">{paras}</div>
        <div class="card-insight"><strong>💡 테크핀 연관:</strong> {esc(c["techfin_insight_ko"])}</div>
      </article>
'''
        secs += f'''    <section class="company">
      <div class="company-head"><span class="company-num">{a["emoji"]}</span><h2 class="company-name">{esc(a["name"])}</h2></div>
{entries}    </section>
'''
    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{today} AI 다이제스트 — 한글 상세</title>
<meta name="description" content="{today} 글로벌 AI 기술 동향 한글 상세 — {esc(data.get('headline',''))}">
<link rel="stylesheet" href="/ai/styles.css">
</head>
<body>
<div class="ko-wrap">

  <header class="hero">
    <span class="eyebrow ko-eyebrow">🇰🇷 한글 상세 · {today}</span>
    <h1>글로벌 AI 기술 동향 — 한글 상세 해설</h1>
    <p class="meta">기간: <strong>{ws} ~ {today}</strong> · 카드 한국어 해설 · 테크핀레이팅스 인사이트 포함</p>
    <nav class="ko-backlinks">
      <a class="ko-btn" href="/ai/archive/{today}.html">← 카드 요약본으로</a>
      <a class="ko-btn ghost" href="/ai/">최신 AI 다이제스트</a>
    </nav>
  </header>

  <div class="notice">
    본문 한글은 전문 번역이 아니라 <strong>테크핀레이팅스 자체 작성 요약·해설</strong>이며 정확한 원문은 각 항목 '원문 보기' 링크를 참고하시기 바랍니다.
  </div>

{secs}
  <footer class="page-footer">
    한글 상세본 · 자체 작성 · {today} · <a href="/ai/archive/{today}.html">카드 요약본</a> · <a href="/ai/">최신 AI 다이제스트</a> · <a href="/">경쟁사 동향</a>
  </footer>

</div>
</body>
</html>
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-openai", action="store_true")
    args = ap.parse_args()

    cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    areas = cfg["areas"]
    today = L.today_str()
    today_dt = dt.datetime.strptime(today, "%Y-%m-%d").replace(tzinfo=L.KST)
    ws = (today_dt - dt.timedelta(days=cfg["window_days"] - 1)).strftime("%Y-%m-%d")

    pset, prev_date = L.prev_urls(ARCHIVE_DIR, MANIFEST, today)
    log(f"[*] today={today} prev={prev_date} prev_urls={len(pset)}")

    cands = gather(cfg["feeds"], cfg["window_days"], today_dt)
    log(f"[*] {len(cands)} feed items in window; verifying…")
    new, covered, allowed = [], [], set()
    for c in cands:
        ok, why = L.verify_url(c["url"])
        if not ok:
            continue
        allowed.add(c["url"])
        (covered if c["url"] in pset else new).append(c)
    log(f"[*] verified NEW={len(new)} ALREADY_COVERED={len(covered)}")

    if args.dry_run:
        for n in new[:40]:
            log(f"   NEW {n.get('date_str','')} {n['title'][:60]} {n['url']}")
        return

    if args.no_openai:
        data = {"cards": [], "ceo_top3": [], "insight": [], "recap": [],
                "headline": f"{today} AI 동향 정리.", "conclusion": "자동 생성(LLM 미사용)."}
    else:
        payload = {"today": today, "prev_digest_date": prev_date,
                   "NEW": [{"url": x["url"], "title": x["title"], "date": x.get("date_str", ""), "desc": x["desc"]} for x in new],
                   "ALREADY_COVERED": [{"url": x["url"], "title": x["title"], "date": x.get("date_str", "")} for x in covered]}
        log("[*] OpenAI composing…")
        data = L.openai_compose(SYSTEM_PROMPT, payload, SCHEMA, "ai_digest")
        data = L.enforce_url_whitelist(data, allowed, ["cards", "ceo_top3", "recap"])

    _, anchor_of = assign_anchors(data.get("cards", []), areas)
    with open(os.path.join(ARCHIVE_DIR, f"{today}.html"), "w", encoding="utf-8") as f:
        f.write(render_main(today, ws, data, areas, True, anchor_of))
    with open(os.path.join(SUB, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_main(today, ws, data, areas, False, anchor_of))
    with open(os.path.join(ARCHIVE_DIR, f"{today}-ko.html"), "w", encoding="utf-8") as f:
        f.write(render_ko(today, ws, data, areas, anchor_of))
    L.update_manifest(MANIFEST, today, f"글로벌 AI 기술 동향 다이제스트 — {today}",
                      data.get("headline", f"{today} AI 동향"))
    log(f"[✓] wrote ai archive/{today}.html + ko + index + manifest "
        f"(cards={len(data.get('cards',[]))} ceo={len(data.get('ceo_top3',[]))} recap={len(data.get('recap',[]))})")


if __name__ == "__main__":
    main()
