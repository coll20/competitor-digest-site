#!/usr/bin/env python3
"""
Deterministic citation-link gate for the digest sites.

WHY: A routine once published cards whose "source" link pointed at a board/listing
ROOT page (e.g. https://www.fsc.go.kr/no010101) instead of the specific post. The
root page returns HTTP 200 and even contains the headline text, so the routine's
self-verification ("HTTP 200 + keyword match") passed it — yet a reader clicking
the link cannot find the claimed item. See CLAUDE.md §6/§11.

This script is the deterministic backstop the LLM routine cannot skip. It scans the
*citation* links in generated digest HTML (card titles, CEO items, recap, Sources,
국내 보도 chips, 원문 보기) and FAILS if any of them points at a listing / board-root
/ search / homepage / un-fetchable (blog·cafe) URL instead of a specific article or
post. Navigational links (게시판 전체 ↗ board-link, sidebar-switch, footer, 한글로
읽기 ko-btn, internal relative links) are intentionally exempt — those are allowed
to point at roots.

Usage:
  verify_links.py <file.html> [<file2.html> ...]   # check specific files
  verify_links.py                                   # check *.html changed in HEAD~1..HEAD

Exit code 0 = all citation links are item-level. Exit code 1 = at least one bad
citation link (details printed). Exit code 2 = usage / internal error.
"""
import sys
import subprocess
from html.parser import HTMLParser
from urllib.parse import urlsplit

SITE_HOST = "competitor-digest-jay-1779945070.netlify.app"

# Anchor classes that mark a link as navigational (allowed to be a root/listing).
NAV_ANCHOR_CLASSES = {"board-link", "sidebar-switch", "ko-btn", "ghost"}
# Anchor classes that mark a link as a CITATION (must be item-level).
CITATION_ANCHOR_CLASSES = {"recap-link", "kr-src", "ko-orig"}
# Ancestor classes/ids that wrap citation links.
CITATION_ANCESTOR_CLASSES = {"card-title", "sources"}
CITATION_ANCESTOR_IDS = {"sources"}
# Ancestor classes that mark navigational regions. empty-state has no specific claim
# to cite, so any link inside it is "browse the board" navigation, not a citation.
NAV_ANCESTOR_CLASSES = {"sidebar", "toc", "sidebar-switch", "company-head", "empty-state"}


class Ctx:
    __slots__ = ("tag", "classes", "id")

    def __init__(self, tag, classes, _id):
        self.tag = tag
        self.classes = classes
        self.id = _id


class CitationParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.citations = []  # list of (href, line)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set((a.get("class") or "").split())
        _id = a.get("id") or ""
        if tag == "a" and a.get("href"):
            self._consider_anchor(a.get("href"), classes)
        # void/self-closing tags should not push onto the stack
        if tag not in ("a", "img", "br", "hr", "meta", "link", "input", "source"):
            self.stack.append(Ctx(tag, classes, _id))
        elif tag == "a":
            # anchors can wrap content but rarely nest meaningfully here; don't track
            pass

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def _is_nav(self, anchor_classes):
        if anchor_classes & NAV_ANCHOR_CLASSES:
            return True
        for ctx in self.stack:
            if ctx.tag == "footer":
                return True
            if ctx.classes & NAV_ANCESTOR_CLASSES:
                return True
        return False

    def _is_citation(self, anchor_classes):
        if anchor_classes & CITATION_ANCHOR_CLASSES:
            return True
        for ctx in self.stack:
            if ctx.classes & CITATION_ANCESTOR_CLASSES:
                return True
            if ctx.id in CITATION_ANCESTOR_IDS:
                return True
            # CEO item: <div class="title"> inside a ceo-* container
            if "title" in ctx.classes and any(
                c.startswith("ceo") for c in ctx.classes
            ):
                return True
        # CEO item alt structure: anchor inside .ceo-body .title
        in_ceo = any(any(c.startswith("ceo") for c in ctx.classes) for ctx in self.stack)
        in_title = any("title" in ctx.classes for ctx in self.stack)
        if in_ceo and in_title:
            return True
        return False

    def _consider_anchor(self, href, anchor_classes):
        href = href.strip()
        # internal / relative links are navigation
        if not (href.startswith("http://") or href.startswith("https://")):
            return
        host = urlsplit(href).netloc.lower()
        if host == SITE_HOST:
            return
        if self._is_nav(anchor_classes):
            return
        # citation OR unknown external link -> must be item-level
        if self._is_citation(anchor_classes) or True:
            self.citations.append((href, self.getpos()[0]))


def classify_bad(href):
    """Return a reason string if href is NOT an acceptable item-level citation, else None."""
    parts = urlsplit(href)
    host = parts.netloc.lower()
    path = parts.path or ""
    query = parts.query or ""

    # blog/cafe/post.naver are not fetchable -> never citable
    if any(h in host for h in ("blog.naver.com", "cafe.naver.com", "post.naver.com")):
        return f"un-fetchable blog/cafe host ({host}) — cite the news outlet article instead"

    # search / news-index result pages
    if host.startswith("search.") or "search.naver.com" in host:
        return f"search-results page ({host}) — cite the specific article URL"
    if host == "news.google.com":
        return "Google News index page — cite the specific article URL"
    if "/search" in path:
        return "search/listing path (/search) — cite the specific article URL"

    # FSC board ROOT (no numeric post id): /noXXXXXX  or  /noXXXXXX/
    if host.endswith("fsc.go.kr"):
        segs = [s for s in path.split("/") if s]
        # acceptable: /noNNNN/<digits>   (post detail). bad: /noNNNN  (board root)
        if len(segs) == 1 and segs[0].startswith("no") and segs[0][2:].isdigit():
            return f"FSC board-root listing page (/{segs[0]}) — needs the specific /{segs[0]}/<postId>"
        if len(segs) == 0:
            return "FSC homepage root — needs a specific post URL"

    # bare homepage root for any host
    if path in ("", "/") and not query:
        return f"homepage root ({host}/) — needs a specific article URL"

    return None


def check_file(path):
    """Return list of (href, line, reason) bad citations in the file."""
    try:
        with open(path, encoding="utf-8") as f:
            html = f.read()
    except OSError as e:
        print(f"  ! could not read {path}: {e}", file=sys.stderr)
        return [("<unreadable>", 0, str(e))]
    p = CitationParser()
    p.feed(html)
    bad = []
    seen = set()
    for href, line in p.citations:
        reason = classify_bad(href)
        if reason:
            key = (href, reason)
            if key in seen:
                continue
            seen.add(key)
            bad.append((href, line, reason))
    return bad


def changed_html_files():
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            text=True,
        )
    except subprocess.CalledProcessError:
        return []
    return [ln for ln in out.splitlines() if ln.endswith(".html")]


def main(argv):
    files = argv[1:]
    if not files:
        files = changed_html_files()
        if not files:
            print("verify_links: no HTML files to check.")
            return 0
    total_bad = 0
    for path in files:
        bad = check_file(path)
        if bad:
            total_bad += len(bad)
            print(f"\n❌ {path}: {len(bad)} bad citation link(s)")
            for href, line, reason in bad:
                print(f"   line {line}: {href}\n      → {reason}")
        else:
            print(f"✅ {path}: citation links OK")
    if total_bad:
        print(
            f"\n❌ FAIL: {total_bad} citation link(s) point at a listing/root/search/"
            "blog page instead of a specific article/post.\n"
            "   Fix: use the specific article/post URL, cite a verified news article, "
            "or drop the item. Do NOT link a board/section root as a source."
        )
        return 1
    print("\n✅ PASS: all citation links are item-level.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as e:  # noqa: BLE001
        print(f"verify_links: internal error: {e}", file=sys.stderr)
        sys.exit(2)
