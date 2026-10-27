#!/usr/bin/env python3
"""Check an edited app page before publishing it: no script errors, and every saved highlight still covers the same words.

  ISN_KEY='…' python3 _build/check_edit.py OLD_PAGE.html NEW_PAGE.html [--show QID …]
  (ISN_PASSWORD='…' also works; without either, only the script/render checks run)

- loads NEW as the phone site's standalone page in Chromium: any uncaught script error fails the check;
- renders every question once with the app's own questionHTML() (old and new) to catch data that breaks rendering;
- reads the user's highlights from the synced study records (branch 'sync', records.enc) and, for every highlight zone
  of a question (stem, explanation, note supplement) or a topic summary line, compares the highlighted characters in OLD
  and NEW. Offsets count the zone's text without tags and without <en> glosses, exactly as the app does, so a change is
  safe when the characters at those offsets are unchanged. Notes-library zones (note|…) are not checked here.
- --show QID…: print how these questions' stem/explanation read in NEW (line breaks shown as ⏎), to eyeball an edit.
Exit code 0 = all good, 1 = problems (listed).
"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from make_site import standalone_html  # noqa: E402

JS_SETUP = r"""() => {
  window.__QMAP = {};
  for (const sid in CONTENT) for (const t of CONTENT[sid]) for (const q of (t.q || [])) {
    const id = hsh(q.stem); (window.__QMAP[id] = window.__QMAP[id] || []).push(q);
  }
  window.__zoneText = (zone, copy) => {
    const parts = zone.split('|'); const host = document.createElement('div');
    if (parts[0] === 'note') return {skip: 'notes library'};
    if (parts[0] === 'sum') {
      const tp = (CONTENT[parts[1]] || [])[+parts[2]], x = tp && tp.sum && tp.sum[+parts[3]];
      if (!x) return {missing: true};
      host.innerHTML = `<span data-ak="${zone}">${glx(x.h)}</span>`;
    } else {
      const qs = window.__QMAP[parts[0]]; if (!qs || !qs[copy]) return {missing: true};
      host.innerHTML = questionHTML(qs[copy]);
    }
    const z = [...host.querySelectorAll('[data-ak]')].find(e => e.dataset.ak === zone);
    if (!z) return {missing: true};
    const w = document.createTreeWalker(z, NodeFilter.SHOW_TEXT, null); let n, t = '';
    while ((n = w.nextNode())) { if (n.parentNode.closest && n.parentNode.closest('.gl')) continue; t += n.nodeValue; }
    return {text: t, copies: parts[0] === 'sum' ? 1 : window.__QMAP[parts[0]].length};
  };
  window.__renderAll = () => {
    const bad = [];
    for (const id in window.__QMAP) window.__QMAP[id].forEach((q, i) => {
      try { const h = questionHTML(q); if (typeof h !== 'string' || !h) bad.push([id, i, 'empty']); }
      catch (e) { bad.push([id, i, String(e && e.message || e)]); }
    });
    return {n: Object.keys(window.__QMAP).length, bad};
  };
  window.__show = (id) => {
    const qs = window.__QMAP[id]; if (!qs) return null;
    const host = document.createElement('div'); host.innerHTML = questionHTML(qs[0]);
    const txt = (el) => { if (!el) return null; const c = el.cloneNode(true);
      c.querySelectorAll('br').forEach(b => b.replaceWith('⏎')); return c.textContent; };
    return {stem: txt(host.querySelector('[data-ak$="|stem"]')), exp: txt(host.querySelector('[data-ak$="|exp"]')),
            media: [...host.querySelectorAll('.medialink,.medianote,.vidbox,.vidmiss')].map(e => e.className + ': ' + e.textContent.trim())};
  };
  return true;
}"""


def highlights():
    """{zone: [[s, e], …]} from the synced records, or None without a key"""
    if not (os.environ.get("ISN_KEY") or os.environ.get("ISN_PASSWORD")):
        return None
    import read_records as rr
    repo = os.path.dirname(HERE)
    subprocess.run(["git", "-C", repo, "fetch", "-q", "--depth", "1", "origin", "+refs/heads/sync:refs/remotes/origin/sync"],
                   check=True)
    blob = subprocess.run(["git", "-C", repo, "show", "origin/sync:records.enc"], capture_output=True, check=True).stdout
    rec = rr.open_records(blob, rr.site_key())
    return {z: [[h.get("s"), h.get("e")] for h in v] for z, v in (rec.get("hl") or {}).items() if v}


def open_page(browser, page_path, errors, label):
    html = standalone_html(open(page_path, encoding="utf-8").read())
    fd, path = tempfile.mkstemp(suffix=".html"); os.close(fd)
    open(path, "w", encoding="utf-8").write(html)
    pg = browser.new_page()
    pg.route("**/*", lambda r: r.abort() if r.request.url.startswith("http") else r.continue_())
    pg.on("pageerror", lambda e: errors.append(f"{label}: script error: {e}"))
    pg.goto("file://" + path, wait_until="load", timeout=120000)
    pg.wait_for_timeout(1500)
    pg.evaluate(JS_SETUP)
    return pg


def main():
    args = sys.argv[1:]
    show = []
    if "--show" in args:
        i = args.index("--show"); show = args[i + 1:]; args = args[:i]
    if len(args) != 2:
        sys.exit(__doc__)
    old_path, new_path = args
    from playwright.sync_api import sync_playwright
    problems, notes = [], []
    with sync_playwright() as p:
        br = p.chromium.launch()
        old_err, new_err = [], []
        old = open_page(br, old_path, old_err, "OLD")
        new = open_page(br, new_path, new_err, "NEW")
        problems += new_err
        if old_err:
            notes.append(f"(OLD page also had {len(old_err)} script error(s): not caused by this edit)")
        ra = new.evaluate("() => window.__renderAll()")
        for id_, i, msg in ra["bad"]:
            problems.append(f"question {id_} (copy {i}) does not render: {msg}")
        notes.append(f"rendered {ra['n']} questions")
        hl = highlights()
        if hl is None:
            notes.append("no ISN_KEY: highlight check skipped")
        else:
            checked = skipped = 0
            for zone, ranges in sorted(hl.items()):
                o = old.evaluate("([z, c]) => window.__zoneText(z, c)", [zone, 0])
                if o.get("skip"):
                    skipped += 1; continue
                if o.get("missing"):
                    notes.append(f"{zone}: zone not on OLD page (question/line gone already) — not checked"); continue
                for c in range(o.get("copies", 1)):
                    oc = old.evaluate("([z, c]) => window.__zoneText(z, c)", [zone, c]) if c else o
                    nc = new.evaluate("([z, c]) => window.__zoneText(z, c)", [zone, c])
                    if nc.get("missing"):
                        problems.append(f"{zone}: zone missing on NEW page (stem changed or line removed?)"); continue
                    for s, e in ranges:
                        a, b = oc["text"][s:e], nc["text"][s:e]
                        if a != b:
                            problems.append(f"{zone} [{s},{e}]: highlighted text changed: {a!r} → {b!r}")
                    checked += 1
            notes.append(f"highlight zones checked {checked}, skipped {skipped} (notes library)")
        for q in show:
            r = new.evaluate("(id) => window.__show(id)", q)
            print(f"--- {q}\n" + (json.dumps(r, ensure_ascii=False, indent=1) if r else "not found"))
        br.close()
    for n in notes:
        print(n)
    if problems:
        print(f"PROBLEMS ({len(problems)}):")
        for x in problems:
            print("  -", x)
        sys.exit(1)
    print("ok")


if __name__ == "__main__":
    main()
