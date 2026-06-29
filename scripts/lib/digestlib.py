"""
Shared helpers for all digest generators (competitor / douzone / fsc / ai).

Principle (same across every digest): URL discovery + verification + rendering are
DETERMINISTIC Python. The LLM only writes prose and only picks from the verified
URL set we hand it. This module holds the reusable, non-LLM machinery.
"""
import datetime as dt
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime

KST = dt.timezone(dt.timedelta(hours=9))

BLOCKED_HOSTS = ("blog.naver.com", "cafe.naver.com", "post.naver.com",
                 "news.google.com", "search.naver.com")


def log(msg):
    print(msg, flush=True)


def today_str():
    return os.environ.get("TODAY") or dt.datetime.now(KST).strftime("%Y-%m-%d")


def esc(s):
    return html.escape(s or "", quote=True)


# --------------------------------------------------------------------------- Naver feed
def naver_news(query, client_id, client_secret, display=30, sort="date"):
    """Return [{title,url,naver_link,desc,pubDate}] from Naver News Search API."""
    url = "https://openapi.naver.com/v1/search/news.json?" + urllib.parse.urlencode(
        {"query": query, "display": display, "sort": sort})
    req = urllib.request.Request(url, headers={
        "X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = []
    for it in data.get("items", []):
        clean = lambda t: re.sub(r"<.*?>", "", t or "").replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        out.append({
            "title": clean(it.get("title", "")),
            "url": (it.get("originallink") or it.get("link", "")).strip(),
            "naver_link": it.get("link", ""),
            "desc": clean(it.get("description", "")),
            "pubDate": it.get("pubDate", ""),
        })
    return out


def parse_pub(pubdate):
    try:
        return parsedate_to_datetime(pubdate).astimezone(KST)
    except Exception:
        return None


def naver_candidates(queries, match, creds, window_days, today=None):
    """Run all queries, dedup by URL, keep within window, drop blocked hosts,
    require a company/entity name (match token) in title+desc. Newest first."""
    cid, csec = creds
    today = today or dt.datetime.strptime(today_str(), "%Y-%m-%d").replace(tzinfo=KST)
    window_start = today - dt.timedelta(days=window_days)
    match = [m.lower() for m in (match or [])]
    seen, cands = set(), []
    for q in queries:
        try:
            items = naver_news(q, cid, csec)
        except Exception as e:
            log(f"    ! naver query failed [{q}]: {e}")
            continue
        for it in items:
            u = it["url"]
            if not u or u in seen:
                continue
            host = urllib.parse.urlsplit(u).netloc.lower()
            if any(b in host for b in BLOCKED_HOSTS):
                continue
            if match:
                hay = (it["title"] + " " + it["desc"]).lower()
                if not any(m in hay for m in match):
                    continue
            pub = parse_pub(it["pubDate"])
            if pub and pub < window_start:
                continue
            seen.add(u)
            it["date"] = pub.strftime("%Y-%m-%d") if pub else ""
            cands.append(it)
        time.sleep(0.12)
    cands.sort(key=lambda x: x.get("date", ""), reverse=True)
    return cands


# --------------------------------------------------------------------------- URL verify
def verify_url(url):
    """GET url; (ok, reason). ok = 200, not redirected to homepage root, has body, not blocked host."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (digest-verify)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            final, code = r.geturl(), r.getcode()
            body = r.read(200000).decode("utf-8", "ignore")
    except Exception as e:
        return False, f"fetch error: {e}"
    if code != 200:
        return False, f"HTTP {code}"
    fp = urllib.parse.urlsplit(final)
    if fp.path in ("", "/") and not fp.query:
        return False, "redirected to homepage root"
    if any(b in fp.netloc.lower() for b in BLOCKED_HOSTS):
        return False, f"resolved to blocked host {fp.netloc}"
    if len(body) < 600:
        return False, "body too short (likely not an article)"
    return True, "ok"


# --------------------------------------------------------------------------- manifest
def read_manifest(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []


def prev_urls(archive_dir, manifest_path, today):
    """Return (set_of_urls_in_latest_archive_before_today, prev_date)."""
    m = read_manifest(manifest_path)
    dates = sorted([x["date"] for x in m if x.get("date") < today], reverse=True)
    if not dates:
        return set(), None
    p = os.path.join(archive_dir, f"{dates[0]}.html")
    if not os.path.exists(p):
        return set(), dates[0]
    with open(p, encoding="utf-8") as f:
        s = f.read()
    return set(re.findall(r'href="(https?://[^"]+)"', s)), dates[0]


def update_manifest(manifest_path, today, title, headline):
    m = [x for x in read_manifest(manifest_path) if x.get("date") != today]
    m.insert(0, {"date": today, "title": title, "headline": headline})
    m.sort(key=lambda x: x["date"], reverse=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(m, ensure_ascii=False, indent=2) + "\n")


# --------------------------------------------------------------------------- OpenAI
def openai_compose(system_prompt, payload, schema, schema_name="digest", model=None):
    """One structured-output call. Returns the parsed dict. Raises on hard failure."""
    from openai import OpenAI
    client = OpenAI()
    model = model or os.environ.get("OPENAI_MODEL", "gpt-5.1")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        response_format={"type": "json_schema",
                         "json_schema": {"name": schema_name, "strict": True, "schema": schema}},
    )
    return json.loads(resp.choices[0].message.content)


def enforce_url_whitelist(data, allowed, list_keys):
    """Drop any item in data[key] whose url is not in `allowed` (anti-hallucination guard)."""
    for key in list_keys:
        kept = []
        for it in data.get(key, []):
            if it.get("url") in allowed:
                kept.append(it)
            else:
                log(f"    ! dropped non-whitelisted URL in {key}: {it.get('url')!r}")
        data[key] = kept
    return data
