#!/usr/bin/env python3
"""Build the public, password-free SHARED site (share/) from the app page.

  python3 _build/make_share.py PAGE.html [SITE_DIR]

share/index.html is the app page itself (no encryption, no lock screen): a snapshot of the questions and explanations
at build time. It contains NO study records — every visitor's answers, wrong-answer marks, highlights, memos and
"important" marks are kept only in that visitor's own browser (localStorage prefix "isnshare:", separate from the
owner's phone site which uses "isn:" on the same origin).

Differences from the owner's phone site, made here as text patches (the Claude artifact itself is not changed):
  - window.__SHARED__ = true; the 📱 기록 dialog keeps only backup/restore (no GitHub sync, no "send to the Claude
    version", no error-report forwarding, no device lock);
  - error "reports" become private notes on the question (nothing is forwarded anywhere);
  - the 3-day "send your records" nudge is off.
share/ has its own manifest.json (its own PWA scope/name) and copies of the icons. No service worker: the page is
served with gzip by GitHub Pages and the browser caches it normally.
"""
import json, os, re, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from make_site import standalone_html  # noqa: E402

PATCHES = [
    # flag
    ('const STANDALONE=!!window.__STANDALONE__;',
     'const STANDALONE=!!window.__STANDALONE__;\nconst SHARED=!!window.__SHARED__;   // public shared site: records stay in this browser, nothing is forwarded'),
    # error-report wording (nothing is forwarded on the shared site)
    ('const ERRBTN_TIP=STANDALONE\n',
     'const ERRBTN_TIP=SHARED?"문제 오류 메모 — 이 기기에만 표시로 남아요. 정리한 사람에게 알려 주시면 고칠게요.":STANDALONE\n'),
    ('const ERRNOTE_H=STANDALONE?"🚩 오류 신고됨 · 매일 아침 자동 검토":',
     'const ERRNOTE_H=SHARED?"🚩 오류 메모 (이 기기에만 보여요)":STANDALONE?"🚩 오류 신고됨 · 매일 아침 자동 검토":'),
    ('    +(STANDALONE?"신고는 동기화로 전달되어 매일 아침 자동으로 검토·수정돼요',
     '    +(SHARED?"메모는 이 기기에만 표시로 남아요(어디로도 보내지지 않아요). 정리한 사람에게 따로 알려 주시면 고칠게요."\n    :STANDALONE?"신고는 동기화로 전달되어 매일 아침 자동으로 검토·수정돼요'),
    # badge
    ('  else if(STANDALONE){el.textContent="📱 기록";el.title="공부 기록은 이 브라우저에만 저장돼요 — 눌러서 백업·불러오기·오류 신고 복사";',
     '  else if(SHARED){el.textContent="📱 내 기록";el.title="공부 기록은 이 브라우저에만 저장돼요 — 눌러서 백업·불러오기";el.style.color="var(--accent-ink)";el.style.cursor="pointer";}\n'
     '  else if(STANDALONE){el.textContent="📱 기록";el.title="공부 기록은 이 브라우저에만 저장돼요 — 눌러서 백업·불러오기·오류 신고 복사";'),
    # records dialog: backup/restore only
    ('recdlg.innerHTML=STANDALONE?`<div class="recbox" role="dialog" aria-modal="true" aria-labelledby="rech">\n    <h3 id="rech">📱 이 기기의 공부 기록</h3>',
     'recdlg.innerHTML=SHARED?`<div class="recbox" role="dialog" aria-modal="true" aria-labelledby="rech">\n    <h3 id="rech">📱 이 기기의 공부 기록</h3>\n'
     '    <div class="recstat" id="recstat"></div>\n'
     '    <div class="recnote">풀이·오답·중요 표시·형광펜·메모는 <b>이 브라우저에만</b> 저장돼요. 다른 기기에서도 이어서 보려면 백업 파일을 만들어 옮기세요. 브라우저 데이터를 지우면 기록도 지워집니다.</div>\n'
     '    <button type="button" class="recbtn" data-rec="export">⬇ 기록 백업 파일 만들기<span>파일로 저장해 두면 기기를 바꾸거나 데이터가 지워져도 되살릴 수 있어요</span></button>\n'
     '    <button type="button" class="recbtn" data-rec="import">⬆ 백업 파일 불러오기<span>지금 기록에 합칩니다 (있던 기록은 지우지 않아요)</span></button>\n'
     '    <div class="recnote" id="recnote"></div>\n'
     '    <div class="recfoot"><button type="button" class="tbtn recclose" data-rec="close">닫기</button></div>\n'
     '  </div>`:STANDALONE?`<div class="recbox" role="dialog" aria-modal="true" aria-labelledby="rech">\n    <h3 id="rech">📱 이 기기의 공부 기록</h3>'),
    # records dialog setup: skip the sync-button block (those buttons do not exist on the shared site)
    ("  if(STANDALONE){ const on=syncOn();\n    recdlg.querySelector('[data-rec=\"syncon\"]').hidden=on||!GH;",
     "  if(STANDALONE&&!SHARED){ const on=syncOn();\n    recdlg.querySelector('[data-rec=\"syncon\"]').hidden=on||!GH;"),
    # no nudge
    ('  if(!STANDALONE||syncOn()) return;\n  const el=document.getElementById("syncBadge"); if(!el) return;',
     '  if(!STANDALONE||SHARED||syncOn()) return;\n  const el=document.getElementById("syncBadge"); if(!el) return;'),
]


def shared_page(page):
    for old, new in PATCHES:
        n = page.count(old)
        if n != 1:
            sys.exit(f"patch anchor found {n}x (expected 1): {old[:70]!r}")
        page = page.replace(old, new)
    html = standalone_html(page)
    html = html.replace('<script>window.__STANDALONE__=true;window.__LSP__="isn:";</script>',
                        '<script>window.__STANDALONE__=true;window.__SHARED__=true;window.__LSP__="isnshare:";</script>', 1)
    assert "__SHARED__=true" in html
    return html


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    site = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(HERE)
    page = open(sys.argv[1], encoding="utf-8").read()
    ver = re.search(r'const APPVER="([^"]+)"', page)
    html = shared_page(page)
    out = os.path.join(site, "share")
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(html)
    for ic in ("icon-180.png", "icon-192.png", "icon-512.png"):
        shutil.copy(os.path.join(site, ic), os.path.join(out, ic))
    man = json.load(open(os.path.join(site, "manifest.json"), encoding="utf-8"))
    man["name"] = "인서비스 정리노트 (공유)"
    man["short_name"] = "인서비스 공유"
    json.dump(man, open(os.path.join(out, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"written {out}/index.html ({len(html.encode()) / 1e6:.1f} MB) · APPVER {ver.group(1) if ver else '?'}")


if __name__ == "__main__":
    main()
