#!/usr/bin/env python3
"""
Competitor digest generator (refactor 2026-06-29).

Replaces the flaky Anthropic "routine" with a deterministic, observable pipeline
that runs on GitHub Actions cron:

  fetch (Naver News API)  ->  verify URLs (HTTP)  ->  dedup vs yesterday
  ->  OpenAI writes prose ONLY (picks from the verified URL set)
  ->  drop any card whose URL is not in the verified set (hard guard)
  ->  render HTML from template (Python, not the LLM)  ->  write files

The LLM never finds URLs and never writes raw HTML — the two failure modes of
the old routine. URL discovery + verification + rendering are all deterministic.

Env:
  NAVER_CLIENT_ID, NAVER_CLIENT_SECRET   (news feed)
  OPENAI_API_KEY                         (writing)
  OPENAI_MODEL    (optional, default below — set to whatever model you have)
  TODAY           (optional YYYY-MM-DD override; default = Asia/Seoul today)

Usage:
  python generate.py             # full run, writes HTML + manifest
  python generate.py --dry-run   # fetch+verify+dedup only, prints candidates, no OpenAI, no writes
  python generate.py --no-openai # skip OpenAI; emit honest empty-state pages (still writes files)

Commit/push is handled by the GitHub Actions workflow, not this script.
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))   # digest-site/
ARCHIVE_DIR = os.path.join(REPO, "archive")
MANIFEST = os.path.join(ARCHIVE_DIR, "manifest.json")

KST = dt.timezone(dt.timedelta(hours=9))
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.1")  # ⚠ set to a model you actually have access to

BLOCKED_HOSTS = ("blog.naver.com", "cafe.naver.com", "post.naver.com",
                 "news.google.com", "search.naver.com")


# ----------------------------------------------------------------------------- utils
def log(msg):
    print(msg, flush=True)


def today_str():
    return os.environ.get("TODAY") or dt.datetime.now(KST).strftime("%Y-%m-%d")


def load_config():
    with open(os.path.join(HERE, "companies.json"), encoding="utf-8") as f:
        return json.load(f)


def esc(s):
    return html.escape(s or "", quote=True)


# ----------------------------------------------------------------------------- 1. fetch
def naver_news(query, client_id, client_secret, display=30, sort="date"):
    """Return list of {title, originallink, link, description, pubDate} from Naver News API."""
    url = "https://openapi.naver.com/v1/search/news.json?" + urllib.parse.urlencode(
        {"query": query, "display": display, "sort": sort})
    req = urllib.request.Request(url, headers={
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = []
    for it in data.get("items", []):
        out.append({
            "title": re.sub(r"<.*?>", "", it.get("title", "")).replace("&quot;", '"').replace("&amp;", "&"),
            "url": it.get("originallink") or it.get("link", ""),
            "naver_link": it.get("link", ""),
            "desc": re.sub(r"<.*?>", "", it.get("description", "")).replace("&quot;", '"').replace("&amp;", "&"),
            "pubDate": it.get("pubDate", ""),
        })
    return out


def parse_pub(pubdate):
    try:
        return parsedate_to_datetime(pubdate).astimezone(KST)
    except Exception:
        return None


def gather_candidates(company, cfg, creds):
    """Search all queries for a company, dedup by URL, keep within window, drop blocked hosts."""
    cid, csec = creds
    today = dt.datetime.strptime(today_str(), "%Y-%m-%d").replace(tzinfo=KST)
    window_start = today - dt.timedelta(days=cfg["window_days"])
    seen, cands = set(), []
    for q in company["queries"]:
        try:
            items = naver_news(q, cid, csec)
        except Exception as e:
            log(f"    ! naver query failed [{q}]: {e}")
            continue
        for it in items:
            u = it["url"].strip()
            if not u or u in seen:
                continue
            host = urllib.parse.urlsplit(u).netloc.lower()
            if any(b in host for b in BLOCKED_HOSTS):
                continue
            pub = parse_pub(it["pubDate"])
            if pub and pub < window_start:
                continue
            seen.add(u)
            it["date"] = pub.strftime("%Y-%m-%d") if pub else ""
            cands.append(it)
        time.sleep(0.12)  # be gentle to the API
    # newest first
    cands.sort(key=lambda x: x.get("date", ""), reverse=True)
    return cands


# ----------------------------------------------------------------------------- 2. verify
def verify_url(url, want_keywords=()):
    """GET the URL; return (ok, reason). ok=True means 200, not a root/redirect-to-home, has body."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (digest-verify)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            final = r.geturl()
            code = r.getcode()
            body = r.read(200000).decode("utf-8", "ignore")
    except Exception as e:
        return False, f"fetch error: {e}"
    if code != 200:
        return False, f"HTTP {code}"
    fp = urllib.parse.urlsplit(final)
    if fp.path in ("", "/") and not fp.query:
        return False, "redirected to homepage root"
    host = fp.netloc.lower()
    if any(b in host for b in BLOCKED_HOSTS):
        return False, f"resolved to blocked host {host}"
    if len(body) < 600:
        return False, "body too short (likely not an article)"
    return True, "ok"


# ----------------------------------------------------------------------------- 3. dedup
def prev_archive_path(prev_date):
    return os.path.join(ARCHIVE_DIR, f"{prev_date}.html") if prev_date else None


def read_manifest():
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    return []


def prev_urls():
    m = read_manifest()
    dates = sorted([x["date"] for x in m], reverse=True)
    if not dates:
        return set(), None
    p = prev_archive_path(dates[0])
    if not p or not os.path.exists(p):
        return set(), dates[0]
    with open(p, encoding="utf-8") as f:
        s = f.read()
    return set(re.findall(r'href="(https?://[^"]+)"', s)), dates[0]


# ----------------------------------------------------------------------------- 4. OpenAI compose
COMPOSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["cards", "ceo_top3", "recap", "headline", "conclusion"],
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["company_id", "url", "title", "date", "date_class",
                             "source_name", "summary", "impact", "impact_class", "action"],
                "properties": {
                    "company_id": {"type": "string"},
                    "url": {"type": "string"},
                    "title": {"type": "string"},
                    "date": {"type": "string"},
                    "date_class": {"type": "string", "enum": ["fresh", "near"]},
                    "source_name": {"type": "string"},
                    "summary": {"type": "string"},
                    "impact": {"type": "string"},
                    "impact_class": {"type": "string", "enum": ["threat", "opportunity", "neutral"]},
                    "action": {"type": "string"},
                },
            },
        },
        "ceo_top3": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["title", "url", "date", "source_name", "desc", "urgency", "cumulative"],
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "date": {"type": "string"},
                    "source_name": {"type": "string"},
                    "desc": {"type": "string"},
                    "urgency": {"type": "string", "enum": ["high", "midhigh", "low"]},
                    "cumulative": {"type": "boolean"},
                },
            },
        },
        "recap": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["company_id", "url", "title", "date", "source_name", "summary"],
                "properties": {
                    "company_id": {"type": "string"},
                    "url": {"type": "string"},
                    "title": {"type": "string"},
                    "date": {"type": "string"},
                    "source_name": {"type": "string"},
                    "summary": {"type": "string"},
                },
            },
        },
        "headline": {"type": "string"},
        "conclusion": {"type": "string"},
    },
}

SYSTEM_PROMPT = """You are a Korean competitive-intelligence editor for a credit-bureau/data company.
You will be given VERIFIED news candidates (each with a real article URL) for 5 Korean credit/data firms,
already split into NEW (not in yesterday's digest) and ALREADY_COVERED.

Write a daily digest in KOREAN. Rules:
- Use ONLY the urls present in the provided candidates. NEVER invent or modify a URL.
- NEW items become company cards (summary 2-3 sentences, impact 1 sentence, action 1 sentence).
  impact_class: threat (competitor gains) / opportunity / neutral.
- If a company has zero NEW candidates, produce NO card for it (the renderer shows an honest empty-state).
- ceo_top3: the 3 most strategically important items for our CEO. Prefer NEW; if fewer than 3 NEW exist,
  fill from ALREADY_COVERED and set cumulative=true for those.
- recap: 1-line summaries of the ALREADY_COVERED items (the running weekly pool). Max 15.
- headline: <=120 Korean chars summarizing the day; if 0 NEW, say so honestly and summarize cumulative themes.
- conclusion: one '한 줄 결론' sentence.
- Every card/ceo/recap MUST carry source_name (매체명 in Korean) and the article's real url + date.
- Do not fabricate facts; base everything on the provided title/desc/date. Be conservative."""


def openai_compose(today, verified_by_company, prev_date):
    """Call OpenAI; returns the structured dict. Raises on hard failure."""
    from openai import OpenAI  # lazy import so dry-run needs no dep
    client = OpenAI()  # reads OPENAI_API_KEY

    payload = {"today": today, "prev_digest_date": prev_date, "companies": []}
    for c in verified_by_company:
        payload["companies"].append({
            "id": c["id"], "name": c["name"],
            "NEW": [{"url": x["url"], "title": x["title"], "date": x["date"],
                     "desc": x["desc"]} for x in c["new"]],
            "ALREADY_COVERED": [{"url": x["url"], "title": x["title"], "date": x["date"],
                                 "desc": x["desc"]} for x in c["covered"]],
        })

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_schema",
                         "json_schema": {"name": "digest", "strict": True, "schema": COMPOSE_SCHEMA}},
    )
    return json.loads(resp.choices[0].message.content)


def enforce_url_whitelist(data, allowed):
    """Hard guard: drop any card/ceo/recap whose url the LLM was not actually given."""
    def keep(items):
        out = []
        for it in items:
            if it.get("url") in allowed:
                out.append(it)
            else:
                log(f"    ! dropped hallucinated/altered URL: {it.get('url')!r}")
        return out
    data["cards"] = keep(data.get("cards", []))
    data["ceo_top3"] = keep(data.get("ceo_top3", []))
    data["recap"] = keep(data.get("recap", []))
    return data


# ----------------------------------------------------------------------------- 5. render
def render_page(today, window_start, data, companies, archived):
    cards_by = {}
    for c in data.get("cards", []):
        cards_by.setdefault(c["company_id"], []).append(c)

    eyebrow = (f'<span class="eyebrow archived">📅 ARCHIVED · {today}</span>' if archived
               else f'<span class="eyebrow">🟢 LATEST · {today}</span>')
    page_date = today if archived else ""
    title = (f"{today} 다이제스트 | 경쟁사 주간 동향" if archived
             else "경쟁사 주간 동향 다이제스트 (최신)")
    footer = (f'Generated {today} · <a href="/" style="color:var(--accent);">← 최신 다이제스트로</a>'
              if archived else f"Generated {today} · 매일 KST 오전 7시 자동 갱신")

    # CEO
    ceo_items = ""
    for i, it in enumerate(data.get("ceo_top3", [])[:3], 1):
        cum = " (누적)" if it.get("cumulative") else ""
        ceo_items += f'''        <li class="ceo-item">
          <div class="ceo-num">{i}</div>
          <div class="ceo-body">
            <div class="title"><a href="{esc(it["url"])}" target="_blank" rel="noopener">{esc(it["title"])}</a> <span style="color:var(--text-dim);font-weight:500;font-size:13px;">({esc(it["date"])}){cum}</span><span class="src-tag">{esc(it["source_name"])}</span></div>
            <div class="desc">{esc(it["desc"])}</div>
          </div>
          <span class="urgency {esc(it["urgency"])}">{ {"high":"High","midhigh":"Mid-High","low":"Low"}.get(it["urgency"],"Mid") }</span>
        </li>
'''
    if not ceo_items:
        ceo_items = '        <li class="ceo-item"><div class="ceo-body"><div class="desc">오늘 신규 동향 없음 — 하단 누적 섹션 참조.</div></div></li>\n'

    # company sections
    sections = ""
    for co in companies:
        cid = co["id"]
        sub = f'<span class="company-sub">{esc(co["sub"])}</span>' if co.get("sub") else ""
        body = ""
        for c in cards_by.get(cid, []):
            badge = " 🆕" if c["date_class"] == "fresh" else ""
            body += f'''      <article class="card">
        <div class="card-meta"><span class="source-chip">{esc(c["source_name"])}</span><span class="date-chip {esc(c["date_class"])}">{esc(c["date"])}{badge}</span></div>
        <h3 class="card-title"><a href="{esc(c["url"])}" target="_blank" rel="noopener">{esc(c["title"])}</a></h3>
        <p class="card-summary">{esc(c["summary"])}</p>
        <div class="card-impact {esc(c["impact_class"])}"><strong>영향:</strong> {esc(c["impact"])}</div>
        <div class="card-action"><strong>대응:</strong> {esc(c["action"])}</div>
      </article>
'''
        if not body:
            body = f'      <div class="empty-state"><strong>오늘({today[5:].replace("-","/")}) 신규 동향 없음 (이번 주 누적 세션 참조)</strong> — 최근 {cfg_window}일 내 검증 가능한 신규 보도·공시 미확인. 누적 항목은 하단 누적 섹션 참조.</div>\n'
        sections += f'''    <section id="{cid}" class="company">
      <div class="company-head">
        <span class="company-num">{co["num"]}</span>
        <h2 class="company-name">{esc(co["name"])}</h2>
        {sub}
      </div>
{body}    </section>

'''

    # recap
    recap_li = ""
    name_by = {co["id"]: co["name"].split(" /")[0].split(" (")[0] for co in companies}
    for r in data.get("recap", [])[:15]:
        nm = name_by.get(r["company_id"], r["company_id"]).upper() if r["company_id"] in ("nice", "kcb", "kcs") else name_by.get(r["company_id"], r["company_id"])
        recap_li += f'''          <li><strong>{esc(nm)} —</strong> <a class="recap-link" href="{esc(r["url"])}" target="_blank" rel="noopener">{esc(r["title"])}</a>: {esc(r["summary"])} <span style="color:var(--text-dim);">({esc(r["source_name"])} · {esc(r["date"])} 최초 보도)</span></li>
'''
    if not recap_li:
        recap_li = '          <li>이번 주 누적 항목 없음.</li>\n'

    # sources (union of all cited urls)
    src_seen, src_li = set(), ""
    for it in (data.get("ceo_top3", []) + data.get("cards", []) + data.get("recap", [])):
        if it["url"] in src_seen:
            continue
        src_seen.add(it["url"])
        src_li += f'''        <li><a href="{esc(it["url"])}" target="_blank" rel="noopener">{esc(it["title"])} — {esc(it["source_name"])}</a><span class="src-date">{esc(it["date"])}</span></li>
'''

    names = ", ".join(co["name"].split(" /")[0].split(" (")[0] for co in companies)
    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(today)} 경쟁사 주간 동향 다이제스트 — {esc(names)}">
<link rel="stylesheet" href="/styles.css">
</head>
<body data-page-date="{page_date}">
<div class="app">

  <button class="sidebar-toggle" type="button">목차 / 아카이브 ▾</button>

  <aside class="sidebar" aria-label="목차 및 아카이브">
    <div class="sidebar-brand">COMPETITIVE INTEL</div>
    <div class="sidebar-title">경쟁사 주간 동향 다이제스트</div>
    <a class="sidebar-switch" href="/ai/">🤖 글로벌 AI 기술 동향으로 →</a>
    <a class="sidebar-switch" href="/fsc/">🏛️ 금융위원회 동향으로 →</a>
    <a class="sidebar-switch" href="/douzone/">🏢 더존비즈온 동향으로 →</a>

    <h3>이 페이지에서</h3>
    <ul class="sidebar-nav">
      <li><a href="#ceo">🎯 CEO 5분 브리핑</a></li>
{"".join(f'      <li><a href="#{co["id"]}">{co["num"].lstrip("0")}. {co["name"].split(" /")[0].split(" (")[0]}</a></li>' + chr(10) for co in companies)}      <li><a href="#recap">📚 이번 주 누적</a></li>
      <li><a href="#sources">Sources</a></li>
    </ul>

    <h3>일자별 아카이브</h3>
    <ul class="archive-list" id="archive-list"></ul>
    <p class="archive-empty" id="archive-empty">로드 중…</p>
  </aside>

  <main class="content">

    <header class="hero">
      {eyebrow}
      <h1>경쟁사 주간 동향 다이제스트</h1>
      <p class="meta">기간: <strong>{window_start} ~ {today}</strong> · 대상 5개사: {esc(names)}</p>
    </header>

    <div class="notice">
      <strong>중복 제거 적용.</strong> 7일 윈도우 조사 후 이전 다이제스트에서 이미 다룬 항목은 하단 <strong>이번 주 누적 주요 동향</strong> 섹션으로 이동. 모든 항목에 <strong>출처 매체</strong>를 표기하며, 링크는 실제 기사 URL만 사용(검증 완료).
    </div>

    <section id="ceo" class="ceo-brief" aria-labelledby="ceo-title">
      <h2 id="ceo-title"><span class="icon">🎯</span> CEO 5분 브리핑</h2>
      <p class="subtitle">가장 중요한 3가지만</p>
      <ol class="ceo-list">
{ceo_items}      </ol>
      <div class="ceo-conclusion">💡 <strong>한 줄 결론</strong> — {esc(data.get("conclusion",""))}</div>
    </section>

{sections}    <section id="recap" class="company">
      <div class="company-head">
        <span class="company-num">📚</span>
        <h2 class="company-name">이번 주 누적 주요 동향</h2>
        <span class="company-sub">이전 다이제스트에서 이미 다룬 항목 — 1줄 요약</span>
      </div>
      <article class="card">
        <ul style="margin:0; padding-left:18px; display:flex; flex-direction:column; gap:8px;">
{recap_li}        </ul>
      </article>
    </section>

    <section id="sources" class="sources">
      <h2>Sources</h2>
      <ul>
{src_li}      </ul>
    </section>

    <footer class="page-footer">
      {footer}
    </footer>

  </main>
</div>

<script src="/sidebar.js"></script>
</body>
</html>
'''


# stash window days for empty-state text
cfg_window = 14


def update_manifest(today, headline):
    m = [x for x in read_manifest() if x.get("date") != today]
    m.insert(0, {"date": today,
                 "title": f"경쟁사 주간 동향 다이제스트 — {today}",
                 "headline": headline})
    m.sort(key=lambda x: x["date"], reverse=True)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        f.write(json.dumps(m, ensure_ascii=False, indent=2) + "\n")


# ----------------------------------------------------------------------------- main
def main():
    global cfg_window
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="fetch+verify+dedup only; no OpenAI, no writes")
    ap.add_argument("--no-openai", action="store_true", help="skip OpenAI; write honest empty-state pages")
    args = ap.parse_args()

    cfg = load_config()
    cfg_window = cfg["window_days"]
    today = today_str()
    window_start = (dt.datetime.strptime(today, "%Y-%m-%d") - dt.timedelta(days=6)).strftime("%Y-%m-%d")
    companies = cfg["companies"]

    cid = os.environ.get("NAVER_CLIENT_ID")
    csec = os.environ.get("NAVER_CLIENT_SECRET")
    if not (cid and csec):
        log("FATAL: NAVER_CLIENT_ID / NAVER_CLIENT_SECRET not set"); sys.exit(2)

    pset, prev_date = prev_urls()
    log(f"[*] today={today}  prev_digest={prev_date}  prev_urls={len(pset)}")

    verified_by_company = []
    allowed_urls = set()
    total_new = 0
    for co in companies:
        log(f"[*] {co['id']}: searching…")
        cands = gather_candidates(co, cfg, (cid, csec))
        log(f"    {len(cands)} candidates after window/host filter; verifying…")
        new, covered = [], []
        for c in cands:
            ok, why = verify_url(c["url"])
            if not ok:
                log(f"    - drop {c['url']} ({why})")
                continue
            allowed_urls.add(c["url"])
            (covered if c["url"] in pset else new).append(c)
        total_new += len(new)
        log(f"    => NEW={len(new)}  ALREADY_COVERED={len(covered)}")
        verified_by_company.append({**co, "new": new, "covered": covered})

    if args.dry_run:
        log(f"\n[dry-run] total NEW across companies = {total_new}")
        for c in verified_by_company:
            log(f"  {c['id']}: NEW={len(c['new'])} COVERED={len(c['covered'])}")
            for n in c["new"]:
                log(f"     NEW  {n['date']}  {n['title'][:60]}  {n['url']}")
        return

    if args.no_openai or total_new == 0 and args.no_openai:
        data = {"cards": [], "ceo_top3": [], "recap": [], "headline":
                f"{today} 5개사 신규 보도 미확인.", "conclusion": "오늘 신규 이슈 없음 — 누적 참조."}
    else:
        log("[*] OpenAI composing…")
        data = openai_compose(today, verified_by_company, prev_date)
        data = enforce_url_whitelist(data, allowed_urls)

    # write archive + index
    arch = render_page(today, window_start, data, companies, archived=True)
    idx = render_page(today, window_start, data, companies, archived=False)
    with open(os.path.join(ARCHIVE_DIR, f"{today}.html"), "w", encoding="utf-8") as f:
        f.write(arch)
    with open(os.path.join(REPO, "index.html"), "w", encoding="utf-8") as f:
        f.write(idx)
    update_manifest(today, data.get("headline", f"{today} 경쟁사 동향"))
    log(f"[✓] wrote archive/{today}.html + index.html + manifest.json")
    log(f"[✓] cards={len(data.get('cards',[]))} ceo={len(data.get('ceo_top3',[]))} recap={len(data.get('recap',[]))}")


if __name__ == "__main__":
    main()
