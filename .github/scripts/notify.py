#!/usr/bin/env python3
"""Daily notifier — sends KakaoTalk (나에게 보내기) + Gmail with latest digest URL + headline.

Required env vars:
  KAKAO_REST_API_KEY, KAKAO_REFRESH_TOKEN, GMAIL_USER, GMAIL_APP_PASSWORD
Optional:
  ADMIN_PAT  — if set, auto-updates KAKAO_REFRESH_TOKEN secret when Kakao rotates it
"""
import datetime
import json
import os
import smtplib
import sys
import time
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

KST = datetime.timezone(datetime.timedelta(hours=9))
TODAY_KST = datetime.datetime.now(KST).strftime("%Y-%m-%d")

SITE_URL = "https://competitor-digest-jay-1779945070.netlify.app"
MANIFEST_URL = f"{SITE_URL}/archive/manifest.json"
AI_URL = f"{SITE_URL}/ai/"
AI_MANIFEST_URL = f"{SITE_URL}/ai/archive/manifest.json"
FSC_URL = f"{SITE_URL}/fsc/"
FSC_MANIFEST_URL = f"{SITE_URL}/fsc/archive/manifest.json"
DZ_URL = f"{SITE_URL}/douzone/"
DZ_MANIFEST_URL = f"{SITE_URL}/douzone/archive/manifest.json"
REPO = "coll20/competitor-digest-site"


def is_stale(date_str):
    """A digest section is stale if its latest manifest date isn't today (KST)."""
    return (date_str or "")[:10] != TODAY_KST


def stale_suffix(date_str):
    """Human-readable freshness flag appended to a stale section's date (else '')."""
    if is_stale(date_str):
        mmdd = TODAY_KST[5:]
        return f" ⚠️ 오늘({mmdd}) 미갱신 · 최신 {date_str}"
    return ""


def stale_html(date_str):
    """A red freshness banner for a stale Gmail section (else '')."""
    if is_stale(date_str):
        return (
            '<p style="font-size:13px;color:#b91c1c;background:#fef2f2;'
            'padding:10px 14px;border-radius:8px;border-left:3px solid #ef4444;'
            f'margin:0 0 12px;">⚠️ 오늘({TODAY_KST}) 분이 아직 생성되지 않았습니다 '
            f'— 아래는 가장 최근({date_str}) 내용입니다.</p>'
        )
    return ""


def http_post(url, form, headers=None):
    data = urllib.parse.urlencode(form).encode()
    h = {"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        return e.code, json.loads(body) if body.startswith("{") else {"error": body}


def http_get_json(url):
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def refresh_kakao(rest_api_key, refresh_token):
    """Returns (access_token, new_refresh_token_or_None)."""
    status, body = http_post(
        "https://kauth.kakao.com/oauth/token",
        {
            "grant_type": "refresh_token",
            "client_id": rest_api_key,
            "refresh_token": refresh_token,
        },
    )
    if status != 200 or "access_token" not in body:
        raise RuntimeError(f"Kakao refresh failed (status={status}): {body}")
    return body["access_token"], body.get("refresh_token")


def send_kakao(access_token, text, web_url):
    template = {
        "object_type": "text",
        "text": text,
        "link": {"web_url": web_url, "mobile_web_url": web_url},
        "button_title": "다이제스트 열기",
    }
    status, body = http_post(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        {"template_object": json.dumps(template, ensure_ascii=False)},
        {"Authorization": f"Bearer {access_token}"},
    )
    if status != 200 or body.get("result_code") != 0:
        raise RuntimeError(f"Kakao send failed (status={status}): {body}")


def update_github_secret(repo, secret_name, value, admin_pat):
    """Encrypt and PUT a GitHub Actions secret via REST API."""
    import nacl.encoding
    import nacl.public

    headers = {"Authorization": f"Bearer {admin_pat}", "Accept": "application/vnd.github+json"}
    # Fetch repo public key
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/secrets/public-key", headers=headers
    )
    with urllib.request.urlopen(req) as r:
        key_info = json.loads(r.read().decode())
    pubkey = nacl.public.PublicKey(key_info["key"].encode(), nacl.encoding.Base64Encoder())
    encrypted = nacl.public.SealedBox(pubkey).encrypt(value.encode())
    encrypted_b64 = nacl.encoding.Base64Encoder.encode(encrypted).decode()
    # PUT secret
    body = json.dumps({"encrypted_value": encrypted_b64, "key_id": key_info["key_id"]}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}",
        data=body,
        headers={**headers, "Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req) as r:
        return r.status  # 201 (created) or 204 (updated)


def send_gmail(user, password, subject, html_body, bcc=None):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Competitor Digest <{user}>"
    msg["To"] = user
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    recipients = [user] + (bcc or [])
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(user, password)
        server.sendmail(user, recipients, msg.as_string())


def main():
    rest_api_key = os.environ["KAKAO_REST_API_KEY"]
    refresh_token = os.environ["KAKAO_REFRESH_TOKEN"]
    gmail_user = os.environ["GMAIL_USER"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")
    bcc_raw = os.environ.get("GMAIL_EXTRA_RECIPIENTS", "").strip()
    bcc_list = [e.strip() for e in bcc_raw.split(",") if e.strip()] if bcc_raw else []

    print(f"[1/4] Fetching competitor manifest: {MANIFEST_URL}")
    manifest = http_get_json(f"{MANIFEST_URL}?t={int(time.time())}")
    if not manifest:
        raise RuntimeError("Manifest is empty")
    latest = manifest[0]
    date = latest["date"]
    title = latest.get("title", f"경쟁사 다이제스트 — {date}")
    headline = latest.get("headline", "(헤드라인 없음)")
    print(f"      competitor latest: date={date}  headline={headline}")

    # AI digest manifest is optional — degrade gracefully if missing/empty.
    ai = None
    try:
        ai_manifest = http_get_json(f"{AI_MANIFEST_URL}?t={int(time.time())}")
        if ai_manifest:
            ai_latest = ai_manifest[0]
            ai = {
                "date": ai_latest["date"],
                "headline": ai_latest.get("headline", "(헤드라인 없음)"),
            }
            print(f"      AI latest: date={ai['date']}  headline={ai['headline']}")
        else:
            print("      AI manifest empty — skipping AI section")
    except Exception as e:
        print(f"::warning::AI manifest fetch failed ({e}) — sending competitor-only notification")

    # FSC (금융위) digest manifest is optional — degrade gracefully if missing/empty.
    fsc = None
    try:
        fsc_manifest = http_get_json(f"{FSC_MANIFEST_URL}?t={int(time.time())}")
        if fsc_manifest:
            fsc_latest = fsc_manifest[0]
            fsc = {
                "date": fsc_latest["date"],
                "headline": fsc_latest.get("headline", "(헤드라인 없음)"),
            }
            print(f"      FSC latest: date={fsc['date']}  headline={fsc['headline']}")
        else:
            print("      FSC manifest empty — skipping FSC section")
    except Exception as e:
        print(f"::warning::FSC manifest fetch failed ({e}) — skipping FSC section")

    # 더존비즈온 digest manifest is optional — degrade gracefully if missing/empty.
    dz = None
    try:
        dz_manifest = http_get_json(f"{DZ_MANIFEST_URL}?t={int(time.time())}")
        if dz_manifest:
            dz_latest = dz_manifest[0]
            dz = {
                "date": dz_latest["date"],
                "headline": dz_latest.get("headline", "(헤드라인 없음)"),
            }
            print(f"      Douzone latest: date={dz['date']}  headline={dz['headline']}")
        else:
            print("      Douzone manifest empty — skipping Douzone section")
    except Exception as e:
        print(f"::warning::Douzone manifest fetch failed ({e}) — skipping Douzone section")

    print("[2/4] Refreshing Kakao access token...")
    access_token, new_refresh = refresh_kakao(rest_api_key, refresh_token)
    if new_refresh and new_refresh != refresh_token:
        admin_pat = os.environ.get("ADMIN_PAT")
        if admin_pat:
            try:
                status = update_github_secret(REPO, "KAKAO_REFRESH_TOKEN", new_refresh, admin_pat)
                print(f"      ✓ Kakao rotated refresh_token — auto-updated GH secret (HTTP {status})")
            except Exception as e:
                print(
                    f"::error::Kakao rotated refresh_token but auto-update FAILED: {e}\n"
                    f"Manually update GH secret KAKAO_REFRESH_TOKEN with:\n{new_refresh}"
                )
        else:
            print(
                "::warning::Kakao rotated refresh_token; ADMIN_PAT not set. "
                f"Manually update GH secret KAKAO_REFRESH_TOKEN with:\n{new_refresh}"
            )
    else:
        print("      (refresh_token still valid, no rotation needed)")

    # ---- Freshness summary (header line so a stale day is obvious at a glance) ----
    stale_sections = []
    if is_stale(date):
        stale_sections.append("경쟁사")
    if ai and is_stale(ai["date"]):
        stale_sections.append("AI")
    if fsc and is_stale(fsc["date"]):
        stale_sections.append("금융위")
    if dz and is_stale(dz["date"]):
        stale_sections.append("더존")

    # ---- Build KakaoTalk text (one message, sections with freshness flags) ----
    if stale_sections:
        kakao_text = f"⚠️ {TODAY_KST} 다이제스트 — 미갱신: {', '.join(stale_sections)}\n\n"
    else:
        kakao_text = ""
    kakao_text += f"📊 {date} 경쟁사 다이제스트{stale_suffix(date)}\n\n{headline}\n\n🔗 {SITE_URL}"
    if ai:
        kakao_text += (
            f"\n\n────────────\n🤖 {ai['date']} 글로벌 AI 기술 동향{stale_suffix(ai['date'])}\n\n"
            f"{ai['headline']}\n\n🔗 {AI_URL}"
        )
    if fsc:
        kakao_text += (
            f"\n\n────────────\n🏛️ {fsc['date']} 금융위원회 동향{stale_suffix(fsc['date'])}\n\n"
            f"{fsc['headline']}\n\n🔗 {FSC_URL}"
        )
    if dz:
        kakao_text += (
            f"\n\n────────────\n🏢 {dz['date']} 더존비즈온 동향{stale_suffix(dz['date'])}\n\n"
            f"{dz['headline']}\n\n🔗 {DZ_URL}"
        )

    # ---- Build Gmail (one mail, multiple sections) ----
    sections = ["경쟁사"]
    if ai:
        sections.append("AI 기술 동향")
    if fsc:
        sections.append("금융위 동향")
    if dz:
        sections.append("더존비즈온")
    warn = "⚠️ " if stale_sections else ""
    if len(sections) > 1:
        gmail_subject = f"[데일리 다이제스트] {warn}{TODAY_KST} " + " + ".join(sections)
        if stale_sections:
            gmail_subject += f" (미갱신: {', '.join(stale_sections)})"
    else:
        gmail_subject = f"[경쟁사 다이제스트] {warn}{TODAY_KST} — {headline[:60]}"

    ai_section = ""
    if ai:
        ai_section = f"""
    <p style="color:#888;font-size:11px;letter-spacing:0.12em;text-transform:uppercase;margin:28px 0 8px;">GLOBAL AI TECH INTEL</p>
    <h2 style="margin:0 0 16px;font-size:22px;color:#0f766e;">🤖 {ai['date']} 글로벌 AI 기술 동향</h2>
    {stale_html(ai['date'])}
    <p style="font-size:16px;color:#333;background:#ecfdf5;padding:16px 20px;border-radius:8px;border-left:3px solid #2dd4bf;margin:0 0 20px;">
      {ai['headline']}
    </p>
    <p style="margin:0 0 8px;">
      <a href="{AI_URL}" style="display:inline-block;background:linear-gradient(135deg,#2dd4bf,#818cf8);color:white;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;">
        🔗 AI 다이제스트 열기
      </a>
    </p>"""

    fsc_section = ""
    if fsc:
        fsc_section = f"""
    <p style="color:#888;font-size:11px;letter-spacing:0.12em;text-transform:uppercase;margin:28px 0 8px;">FSC REGULATORY WATCH</p>
    <h2 style="margin:0 0 16px;font-size:22px;color:#b8860b;">🏛️ {fsc['date']} 금융위원회 동향</h2>
    {stale_html(fsc['date'])}
    <p style="font-size:16px;color:#333;background:#fdf6e3;padding:16px 20px;border-radius:8px;border-left:3px solid #e3b341;margin:0 0 20px;">
      {fsc['headline']}
    </p>
    <p style="margin:0 0 8px;">
      <a href="{FSC_URL}" style="display:inline-block;background:linear-gradient(135deg,#e3b341,#5b8dd6);color:white;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;">
        🔗 금융위 다이제스트 열기
      </a>
    </p>"""

    dz_section = ""
    if dz:
        dz_section = f"""
    <p style="color:#888;font-size:11px;letter-spacing:0.12em;text-transform:uppercase;margin:28px 0 8px;">DOUZONE GROUP INTEL</p>
    <h2 style="margin:0 0 16px;font-size:22px;color:#e11d48;">🏢 {dz['date']} 더존비즈온 동향</h2>
    {stale_html(dz['date'])}
    <p style="font-size:16px;color:#333;background:#fff1f2;padding:16px 20px;border-radius:8px;border-left:3px solid #f43f5e;margin:0 0 20px;">
      {dz['headline']}
    </p>
    <p style="margin:0 0 8px;">
      <a href="{DZ_URL}" style="display:inline-block;background:linear-gradient(135deg,#f43f5e,#fb923c);color:white;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;">
        🔗 더존 다이제스트 열기
      </a>
    </p>"""

    gmail_html = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Noto Sans KR',sans-serif;line-height:1.6;color:#222;background:#f5f5f7;margin:0;padding:24px;">
  <div style="max-width:560px;margin:0 auto;background:white;border-radius:12px;padding:32px;">
    <p style="color:#888;font-size:11px;letter-spacing:0.12em;text-transform:uppercase;margin:0 0 8px;">COMPETITIVE INTELLIGENCE</p>
    <h2 style="margin:0 0 16px;font-size:22px;color:#1a1a2e;">📊 {date} 경쟁사 다이제스트</h2>
    {stale_html(date)}
    <p style="font-size:16px;color:#333;background:#f0f4ff;padding:16px 20px;border-radius:8px;border-left:3px solid #6ea8ff;margin:0 0 20px;">
      {headline}
    </p>
    <p style="margin:0;">
      <a href="{SITE_URL}" style="display:inline-block;background:linear-gradient(135deg,#6ea8ff,#b794ff);color:white;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;">
        🔗 경쟁사 다이제스트 열기
      </a>
    </p>{ai_section}{fsc_section}{dz_section}
    <p style="font-size:12px;color:#999;margin:32px 0 0;border-top:1px solid #eee;padding-top:16px;">
      매일 KST 자동 수집 → 카카오톡·이메일 동시 발송<br>
      경쟁사: <a href="{SITE_URL}" style="color:#6ea8ff;">{SITE_URL}</a><br>
      AI 동향: <a href="{AI_URL}" style="color:#2dd4bf;">{AI_URL}</a><br>
      금융위: <a href="{FSC_URL}" style="color:#b8860b;">{FSC_URL}</a><br>
      더존비즈온: <a href="{DZ_URL}" style="color:#f43f5e;">{DZ_URL}</a>
    </p>
  </div>
</body></html>"""

    print("[3/4] Sending KakaoTalk...")
    send_kakao(access_token, kakao_text, SITE_URL)
    print(f"      ✓ KakaoTalk sent ({len(sections)} section{'s' if len(sections) > 1 else ''}: {', '.join(sections)})")

    print("[4/4] Sending Gmail...")
    send_gmail(gmail_user, gmail_password, gmail_subject, gmail_html, bcc=bcc_list)
    bcc_summary = f" + {len(bcc_list)} BCC ({', '.join(bcc_list)})" if bcc_list else ""
    print(f"      ✓ Gmail sent to {gmail_user}{bcc_summary}")

    print(f"\n✅ Notification complete for {date}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"::error::Notify failed: {e}", file=sys.stderr)
        sys.exit(1)
