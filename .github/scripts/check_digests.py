#!/usr/bin/env python3
"""
Daily watchdog: check that today's digest entry exists in all 4 manifests.
Runs at 09:00 KST (00:00 UTC). If any manifest is missing today's date,
sends a Gmail alert and exits non-zero (visible as a failed GH Actions run).
"""
import json
import os
import smtplib
import sys
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

kst = datetime.timezone(datetime.timedelta(hours=9))
today = datetime.datetime.now(kst).strftime('%Y-%m-%d')

MANIFESTS = {
    '경쟁사': 'archive/manifest.json',
    'AI': 'ai/archive/manifest.json',
    'FSC': 'fsc/archive/manifest.json',
    '더존비즈온': 'douzone/archive/manifest.json',
}

ROUTINE_URLS = {
    '경쟁사': 'https://claude.ai/code/routines/trig_01HHXYVgdgB7HToq4SrFaPZk',
    'AI': 'https://claude.ai/code/routines/trig_01FJQEYTS9m2b9cB3a2qp14J',
    'FSC': 'https://claude.ai/code/routines/trig_01SryyhJftXg4VH1suEHgeF3',
    '더존비즈온': 'https://claude.ai/code/routines/trig_01X4BRezpqH5ftebw4NJnPad',
}


def check_manifest(name, path):
    try:
        with open(path, encoding='utf-8') as f:
            entries = json.load(f)
        dates = [e['date'] for e in entries]
        if today in dates:
            print(f"✅ {name}: {today} 정상")
            return True
        latest = max(dates) if dates else '(없음)'
        print(f"❌ {name}: {today} 없음 (최신 엔트리: {latest})")
        return False
    except FileNotFoundError:
        print(f"❌ {name}: manifest 파일 없음 ({path})")
        return False
    except Exception as e:
        print(f"❌ {name}: 오류 — {e}")
        return False


def send_alert(missing):
    gmail_user = os.environ.get('GMAIL_USER', '')
    gmail_pw = os.environ.get('GMAIL_APP_PASSWORD', '').replace(' ', '')
    extra = os.environ.get('GMAIL_EXTRA_RECIPIENTS', '')

    if not gmail_user or not gmail_pw:
        print("⚠️ Gmail 자격증명 없음 — 이메일 알림 생략")
        return

    subject = f"[자동화 경보] 다이제스트 누락 — {today}"

    rows = ''.join(
        f'<tr><td style="padding:8px;border:1px solid #ddd"><strong>{n}</strong></td>'
        f'<td style="padding:8px;border:1px solid #ddd">{today} 엔트리 없음</td>'
        f'<td style="padding:8px;border:1px solid #ddd"><a href="{ROUTINE_URLS[n]}">'
        f'루틴 로그 보기</a></td></tr>'
        for n in missing
    )

    body = f"""
<h2 style="color:#cc0000">⚠️ 다이제스트 누락 감지 — {today}</h2>
<p>KST 09:00 자동 점검에서 오늘({today}) 다이제스트가 누락된 것을 발견했습니다.</p>
<table style="border-collapse:collapse;width:100%">
  <tr style="background:#f0f0f0">
    <th style="padding:8px;border:1px solid #ddd">다이제스트</th>
    <th style="padding:8px;border:1px solid #ddd">상태</th>
    <th style="padding:8px;border:1px solid #ddd">진단</th>
  </tr>
  {rows}
</table>
<h3>조치 방법</h3>
<ol>
  <li><a href="https://github.com/coll20/competitor-digest-site/actions">GitHub Actions 로그</a>에서 오늘 실패한 워크플로 확인</li>
  <li>해당 루틴 로그(위 링크)에서 실패 원인 확인</li>
  <li>수동 백필 필요 시: Claude Code 세션에서 <code>RemoteTrigger action:run</code> 또는 수동 작성 후 push</li>
</ol>
<hr>
<p style="color:#888;font-size:12px">
  자동 발송 · check-digests.yml watchdog · 사이트:
  <a href="https://competitor-digest-jay-1779945070.netlify.app">competitor-digest-jay</a>
</p>
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = gmail_user
    msg.attach(MIMEText(body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pw)
            recipients = [gmail_user]
            if extra:
                recipients += [a.strip() for a in extra.split(',') if a.strip()]
            server.sendmail(gmail_user, recipients, msg.as_bytes())
        print(f"📧 경보 이메일 발송 완료 → {gmail_user}")
    except Exception as e:
        print(f"⚠️ 이메일 발송 실패: {e}")


def main():
    print(f"=== 다이제스트 신선도 점검 · KST {today} ===\n")
    results = {name: check_manifest(name, path) for name, path in MANIFESTS.items()}
    missing = [name for name, ok in results.items() if not ok]

    if missing:
        print(f"\n❌ 누락 다이제스트: {', '.join(missing)}")
        send_alert(missing)
        return 1

    print(f"\n✅ 전체 정상 — {today} 4개 다이제스트 모두 발행 확인")
    return 0


if __name__ == '__main__':
    sys.exit(main())
