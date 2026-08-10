#!/usr/bin/env python3
"""Weekly strategy-report notifier — KakaoTalk(나에게 보내기) + Gmail.

데일리 notify.py와 같은 카카오/Gmail 인프라·시크릿을 재사용하되, 대상은 주간 전략 리포트.
로컬 weekly-run.sh가 리포트 발행·검증 성공 후 이 워크플로를 workflow_dispatch로 트리거한다.

입력(env, 워크플로 inputs에서 주입):
  WEEKLY_URL       (필수) 이번 주 리포트 아카이브 URL
  WEEKLY_LABEL     예: "7월 3주차"
  WEEKLY_DATE      예: "2026-07-20"
  WEEKLY_HEADLINE  총평 요약(Executive Summary verdict 발췌). 없으면 라벨만.
  WEEKLY_PASSWORD  사이트 접속 비밀번호(GitHub Secret, 미설정 시 메시지에서 생략)
시크릿(env):
  KAKAO_REST_API_KEY, KAKAO_REFRESH_TOKEN, GMAIL_USER, GMAIL_APP_PASSWORD,
  GMAIL_EXTRA_RECIPIENTS(옵션), ADMIN_PAT(옵션 — 카카오 refresh_token rotate 시 GH secret 갱신)
"""
import json
import os
import smtplib
import sys
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

REPO = "coll20/competitor-digest-site"
# 카카오 앱에 등록된(=링크 버튼 허용) 도메인. 주간 사이트 도메인이 미등록이면 이 도메인으로 폴백.
REGISTERED_FALLBACK_URL = "https://competitor-digest-jay-1779945070.netlify.app"


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


def refresh_kakao(rest_api_key, refresh_token):
    status, body = http_post(
        "https://kauth.kakao.com/oauth/token",
        {"grant_type": "refresh_token", "client_id": rest_api_key, "refresh_token": refresh_token},
    )
    if status != 200 or "access_token" not in body:
        raise RuntimeError(f"Kakao refresh failed (status={status}): {body}")
    return body["access_token"], body.get("refresh_token")


def send_kakao(access_token, text, web_url):
    template = {
        "object_type": "text",
        "text": text,
        "link": {"web_url": web_url, "mobile_web_url": web_url},
        "button_title": "리포트 열기",
    }
    return http_post(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        {"template_object": json.dumps(template, ensure_ascii=False)},
        {"Authorization": f"Bearer {access_token}"},
    )


def send_kakao_with_fallback(access_token, text, primary_url):
    """primary_url(주간 도메인)로 먼저 시도. 도메인 미등록 등으로 실패하면 등록 도메인으로 폴백."""
    status, body = send_kakao(access_token, text, primary_url)
    if status == 200 and body.get("result_code") == 0:
        return "primary"
    print(f"::warning::Kakao 링크 도메인 미등록 추정(status={status}, body={body}). 등록 도메인으로 폴백.")
    status, body = send_kakao(access_token, text, REGISTERED_FALLBACK_URL)
    if status == 200 and body.get("result_code") == 0:
        return "fallback"
    raise RuntimeError(f"Kakao send failed (fallback도 실패, status={status}): {body}")


def update_github_secret(repo, secret_name, value, admin_pat):
    import nacl.encoding
    import nacl.public

    headers = {"Authorization": f"Bearer {admin_pat}", "Accept": "application/vnd.github+json"}
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/secrets/public-key", headers=headers)
    with urllib.request.urlopen(req) as r:
        key_info = json.loads(r.read().decode())
    pubkey = nacl.public.PublicKey(key_info["key"].encode(), nacl.encoding.Base64Encoder())
    encrypted = nacl.public.SealedBox(pubkey).encrypt(value.encode())
    encrypted_b64 = nacl.encoding.Base64Encoder.encode(encrypted).decode()
    body = json.dumps({"encrypted_value": encrypted_b64, "key_id": key_info["key_id"]}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}",
        data=body, headers={**headers, "Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req) as r:
        return r.status


def send_gmail(user, password, subject, html_body, bcc=None):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Techfin Weekly Strategy <{user}>"
    msg["To"] = user
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    recipients = [user] + (bcc or [])
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(user, password)
        server.sendmail(user, recipients, msg.as_string())


def main():
    rest_api_key = os.environ["KAKAO_REST_API_KEY"]
    refresh_token = os.environ["KAKAO_REFRESH_TOKEN"]
    url = os.environ["WEEKLY_URL"].strip()
    label = os.environ.get("WEEKLY_LABEL", "").strip() or "주간 전략 리포트"
    date = os.environ.get("WEEKLY_DATE", "").strip()
    headline = os.environ.get("WEEKLY_HEADLINE", "").strip()
    password = os.environ.get("WEEKLY_PASSWORD", "").strip()  # GH secret WEEKLY_PASSWORD (미설정 시 메시지에서 생략)

    # ---- Kakao access token (+ rotate) ----
    print("[1/3] Refreshing Kakao access token...")
    access_token, new_refresh = refresh_kakao(rest_api_key, refresh_token)
    if new_refresh and new_refresh != refresh_token:
        admin_pat = os.environ.get("ADMIN_PAT")
        if admin_pat:
            try:
                st = update_github_secret(REPO, "KAKAO_REFRESH_TOKEN", new_refresh, admin_pat)
                print(f"      ✓ refresh_token rotate → GH secret 갱신(HTTP {st})")
            except Exception as e:
                print(f"::error::refresh_token rotate 됐으나 secret 갱신 실패: {e}\n수동 갱신값:\n{new_refresh}")
        else:
            print(f"::warning::refresh_token rotate 됐으나 ADMIN_PAT 없음. 수동 갱신값:\n{new_refresh}")
    else:
        print("      (refresh_token 유효, rotate 불필요)")

    # ---- KakaoTalk ----
    hl = (headline[:220] + "…") if len(headline) > 221 else headline
    kakao_text = f"📈 주간 전략 리포트 · {label}"
    if date:
        kakao_text += f" ({date})"
    if hl:
        kakao_text += f"\n\n{hl}"
    if password:
        kakao_text += f"\n\n🔒 접속 비밀번호: {password}"
    kakao_text += f"\n🔗 {url}"

    print("[2/3] Sending KakaoTalk...")
    where = send_kakao_with_fallback(access_token, kakao_text, url)
    print(f"      ✓ KakaoTalk sent (link={where})")

    # ---- Gmail ----
    gmail_user = os.environ.get("GMAIL_USER")
    if gmail_user:
        gmail_password = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")
        bcc_raw = os.environ.get("GMAIL_EXTRA_RECIPIENTS", "").strip()
        bcc_list = [e.strip() for e in bcc_raw.split(",") if e.strip()] if bcc_raw else []
        subject = f"[주간 전략 리포트] {date} {label}".strip()
        gmail_html = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Noto Sans KR',sans-serif;line-height:1.6;color:#222;background:#f5f5f7;margin:0;padding:24px;">
  <div style="max-width:600px;margin:0 auto;background:white;border-radius:12px;padding:32px;">
    <p style="color:#888;font-size:11px;letter-spacing:0.12em;text-transform:uppercase;margin:0 0 8px;">TECHFIN WEEKLY STRATEGY BRIEF</p>
    <h2 style="margin:0 0 16px;font-size:22px;color:#0f1c33;">📈 주간 전략 리포트 · {label}</h2>
    <p style="font-size:15px;color:#333;background:#eef2fb;padding:16px 20px;border-radius:8px;border-left:3px solid #1d3a6b;margin:0 0 20px;">
      {hl or '이번 주 뉴스 인텔리전스 × 당사 현안 교차 분석 리포트가 발행되었습니다.'}
    </p>
    <p style="margin:0 0 12px;">
      <a href="{url}" style="display:inline-block;background:linear-gradient(135deg,#1d3a6b,#4064a0);color:white;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;">
        🔗 주간 전략 리포트 열기
      </a>
    </p>
    {f'<p style="font-size:13px;color:#555;background:#fff8e1;padding:10px 14px;border-radius:8px;border-left:3px solid #e3b341;margin:0 0 8px;">🔒 사이트 전체 비밀번호 보호 — 접속 비밀번호: <b>{password}</b></p>' if password else ''}
    <p style="font-size:12px;color:#999;margin:28px 0 0;border-top:1px solid #eee;padding-top:16px;">
      매주 월요일 자동 발행 · 4종 데일리 다이제스트 전수 추출 × 사내 현안 교차 분석<br>대외비(Confidential) · 외부 공유 금지
    </p>
  </div>
</body></html>"""
        print("[3/3] Sending Gmail...")
        send_gmail(gmail_user, gmail_password, subject, gmail_html, bcc=bcc_list)
        bcc_summary = f" + {len(bcc_list)} BCC" if bcc_list else ""
        print(f"      ✓ Gmail sent to {gmail_user}{bcc_summary}")
    else:
        print("[3/3] Gmail 생략(GMAIL_USER 없음)")

    print(f"\n✅ Weekly notification complete: {label} ({date}) {url}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"::error::Weekly notify failed: {e}", file=sys.stderr)
        sys.exit(1)
