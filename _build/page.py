#!/usr/bin/env python3
"""Helpers for editing the app page (the Claude version's page, which the phone site is built from).

  python3 _build/page.py extract ARTIFACT_READ.html PAGE.html   # strip the claude.ai host wrapper from an Artifact read
  python3 _build/page.py find PAGE.html QID [QID…]              # where a question is (section, topic, number) + its texts
  python3 _build/page.py check PAGE.html                         # DATA/EXTRA parse, APPVER, RESOLVED

In Python:  from page import Page;  p = Page.load("PAGE.html");  q = p.question(qid)  … edit q (a dict) …
            p.resolve({qid: ms}); p.set_appver("v50.1"); p.save("PAGE.html")
Rules for edits (the user's highlights and records depend on them):
  - never change a question's stem: its id is hsh(stem) — records, highlights and reports are keyed by it;
  - keep every <en>…</en> gloss; in a zone the user highlighted (read_records.py lists them) only add text after the
    highlighted ranges — offsets count the text without tags and without <en> parts;
  - mark each fixed report in RESOLVED (qid → time of the fix in ms): the app then removes those reports on every device.
"""
import json, re, sys


def hsh(s):
    """the app's question id: djb2 over UTF-16 code units, base 36"""
    h = 5381
    for ch in s:
        c = ord(ch)
        units = [c] if c <= 0xFFFF else [0xD800 + ((c - 0x10000) >> 10), 0xDC00 + ((c - 0x10000) & 0x3FF)]
        for x in units:
            h = ((h << 5) + h + x) & 0xFFFFFFFF
    digits, out = "0123456789abcdefghijklmnopqrstuvwxyz", ""
    while True:
        h, r = divmod(h, 36)
        out = digits[r] + out
        if not h:
            return out


def extract(artifact_html):
    """Artifact read output → the page as published (starts with <title>)"""
    i = artifact_html.index("<body>") + len("<body>")
    if i > artifact_html.index("\n") + 1:
        raise ValueError("unexpected wrapper: <body> is not on the first line")
    j = artifact_html.rindex("</body></html>")
    return artifact_html[i:j].lstrip("\n").rstrip() + "\n"


class Page:
    def __init__(self, text):
        self.lines = text.split("\n")
        self.di = next(i for i, l in enumerate(self.lines) if l.startswith("const DATA = "))
        self.data = json.loads(self.lines[self.di][len("const DATA = "):].rstrip().rstrip(";"))
        self._trail = ";" if self.lines[self.di].rstrip().endswith(";") else ""

    @classmethod
    def load(cls, path):
        return cls(open(path, encoding="utf-8").read())

    def text(self):
        lines = list(self.lines)
        lines[self.di] = "const DATA = " + json.dumps(self.data, ensure_ascii=False) + self._trail
        return "\n".join(lines)

    def save(self, path):
        open(path, "w", encoding="utf-8").write(self.text())

    def questions(self):
        for s in self.data["sections"]:
            for ti, tp in enumerate(self.data["content"].get(s["id"], [])):
                for qi, q in enumerate(tp["q"]):
                    yield s["id"], s.get("ko", ""), ti + 1, tp.get("t", ""), qi + 1, q

    def question(self, qid):
        for sid, sko, t, tko, n, q in self.questions():
            if hsh(q["stem"]) == qid:
                return {"sid": sid, "section": sko, "topic": t, "topic_title": tko, "n": n, "q": q,
                        "label": f"{sid} T{t}-Q{n}"}
        return None

    def _code(self, pat):
        for i, l in enumerate(self.lines):
            if i != self.di and re.search(pat, l):
                return i
        raise KeyError(pat)

    def resolved(self):
        i = self._code(r"^const RESOLVED=")
        return json.loads(re.match(r"const RESOLVED=(\{.*?\});", self.lines[i]).group(1))

    def resolve(self, fixed):
        """fixed: {qid: ms} — reports on these questions made before that time are dropped by the app"""
        i = self._code(r"^const RESOLVED=")
        cur = self.resolved()
        cur.update({k: int(v) for k, v in fixed.items()})
        self.lines[i] = re.sub(r"^const RESOLVED=\{.*?\};", "const RESOLVED=" + json.dumps(cur, separators=(",", ":")) + ";",
                               self.lines[i])

    def appver(self):
        return re.search(r'const APPVER="([^"]+)"', self.lines[self._code(r'^const APPVER=')]).group(1)

    def set_appver(self, v):
        i = self._code(r'^const APPVER=')
        self.lines[i] = re.sub(r'const APPVER="[^"]+"', f'const APPVER="{v}"', self.lines[i])


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "extract":
        open(a[2], "w", encoding="utf-8").write(extract(open(a[1], encoding="utf-8").read()))
        print("page written:", a[2])
    elif a[0] == "find":
        p = Page.load(a[1])
        for qid in a[2:]:
            r = p.question(qid)
            if not r:
                print(qid, "— not found"); continue
            q = r["q"]
            print(f"{qid} = {r['label']} · {r['section']} · {r['topic_title']}")
            print(json.dumps({k: q[k] for k in q if not str(q[k]).startswith("data:")}, ensure_ascii=False, indent=1)[:4000])
    elif a[0] == "check":
        text = open(a[1], encoding="utf-8").read()
        p = Page(text)
        assert p.text() == text, "DATA does not round-trip"
        nq = sum(1 for _ in p.questions())
        print(f"ok · {nq} questions · APPVER {p.appver()} · RESOLVED {len(p.resolved())}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
