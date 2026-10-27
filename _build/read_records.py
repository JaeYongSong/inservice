#!/usr/bin/env python3
"""Read the synced study records (records.enc on branch 'sync') and list the 🚩 error reports.

  ISN_KEY='<base64 site key>' python3 _build/read_records.py [--page PAGE.html] [--file records.enc] [--json]
  (ISN_PASSWORD='…' also works: the key is derived with _build/site_key.json's salt and rounds)

(fetches branch 'sync' itself) records.enc = "ISR1" | gzip flag(1) | iv(12) | AES-256-GCM(site key, records JSON). The site key K is the key the lock screen
derives from the password (devices keep it as isn:unlock). With --page, reports already fixed (RESOLVED in the page, report
time ≤ fix time) are left out and each report shows where its question is. For each reported question the user's
highlight zones are listed too (zone → [start, end] in text without tags/<en>): edits there may only add text after them.
Exit code 3 = the file is sealed with another key (e.g. a device has not yet synced since a password change).
"""
import base64, datetime, gzip, hashlib, json, os, re, subprocess, sys, unicodedata
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from page import Page  # noqa: E402

KST = datetime.timezone(datetime.timedelta(hours=9))


def site_key():
    if os.environ.get("ISN_KEY"):
        return base64.b64decode(os.environ["ISN_KEY"])
    pw = os.environ.get("ISN_PASSWORD") or sys.exit("ISN_KEY(또는 ISN_PASSWORD) 환경 변수가 필요해요")
    k = json.load(open(os.path.join(HERE, "site_key.json")))
    norm = re.sub(r"[\s-]", "", unicodedata.normalize("NFC", pw).lower())
    return hashlib.pbkdf2_hmac("sha256", norm.encode("utf-8"), base64.b64decode(k["salt"]), int(k["iter"]), 32)


def open_records(u8, key):
    if u8[:4] != b"ISR1":
        raise ValueError("not a records file")
    plain = AESGCM(key).decrypt(u8[5:17], u8[17:], None)
    if u8[4] == 1:
        plain = gzip.decompress(plain)
    return json.loads(plain)


def main():
    args = sys.argv[1:]
    opt = lambda name: args[args.index(name) + 1] if name in args else None
    path = opt("--file")
    if path:
        blob = open(path, "rb").read()
    else:
        repo = os.path.dirname(HERE)
        subprocess.run(["git", "-C", repo, "fetch", "-q", "--depth", "1", "origin", "+refs/heads/sync:refs/remotes/origin/sync"],
                       check=True)
        blob = subprocess.run(["git", "-C", repo, "show", "origin/sync:records.enc"], capture_output=True, check=True).stdout
    try:
        rec = open_records(blob, site_key())
    except Exception:
        print("records.enc를 이 열쇠로 열 수 없어요 (비밀번호가 바뀐 뒤 아직 어느 기기도 새 비밀번호로 동기화하지 않았을 수 있어요)")
        sys.exit(3)
    page = Page.load(opt("--page")) if opt("--page") else None
    done = page.resolved() if page else {}
    hl = rec.get("hl", {})
    out = []
    for qid, reps in (rec.get("err") or {}).items():
        for r in reps or []:
            ts = int((r or {}).get("ts") or 0)
            if qid in done and ts <= int(done[qid]):
                continue
            item = {"qid": qid, "ts": ts, "time": datetime.datetime.fromtimestamp(ts / 1000, KST).strftime("%Y-%m-%d %H:%M"),
                    "text": (r or {}).get("text", ""), "stem": ((r or {}).get("stem") or "")[:120],
                    "highlights": {z: [[h.get("s"), h.get("e")] for h in v] for z, v in hl.items()
                                   if (z.startswith(qid + "|")) and v}}
            if page:
                f = page.question(qid)
                item["where"] = f"{f['label']} · {f['section']} · {f['topic_title']}" if f else "(문항을 찾지 못함)"
            out.append(item)
    out.sort(key=lambda x: x["ts"])
    if "--json" in args:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    att = rec.get("att") or {}
    print(f"기록: 풀어본 문항 {len(att)} · 형광펜 구역 {len(hl)} · 처리할 신고 {len(out)}건")
    for x in out:
        print(f"- {x['time']} · {x['qid']} · {x.get('where', '')}\n  신고: {x['text']}\n  문제: {x['stem']}"
              + (f"\n  형광펜: {x['highlights']}" if x["highlights"] else ""))


if __name__ == "__main__":
    main()
