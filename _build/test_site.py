#!/usr/bin/env python3
"""Browser test of the built site (Playwright + Chromium). Needs the site password:
  ISN_PASSWORD='…' python3 _build/test_site.py [SITE_DIR]
Serves SITE_DIR on localhost and checks, on a phone-sized screen:
  1. a new device: lock screen → password → app (standards mode, site mode, 'isn:' records, no sideways scroll, no errors)
  2. a device that remembered the key of an OLD password: asked once for the new password, old key kept as isn:unlock_prev
  3. records sync right after a password change (GitHub API mocked): records.enc sealed with the old key is read with the
     kept old key, merged and pushed back sealed with the new key; the old key is then forgotten
  3b. same, when nothing else changed since the last sync: the file is re-sealed with the new key anyway
  4. another device afterwards: records.enc already uses the new key → read with it directly, old key forgotten
Nothing here contacts GitHub.
"""
import asyncio, base64, gzip, hashlib, json, os, socket, subprocess, sys, time
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from playwright.async_api import async_playwright

SITE = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), ".."))
PW = os.environ.get("ISN_PASSWORD") or sys.exit("ISN_PASSWORD 환경 변수에 사이트 비밀번호를 넣어 주세요")
OWNER, REPO = "JaeYongSong", "inservice"


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def seal_records(obj, key):
    iv = os.urandom(12)
    ct = AESGCM(key).encrypt(iv, gzip.compress(json.dumps(obj).encode()), None)
    return b"ISR1" + bytes([1]) + iv + ct


def open_records(u8, key):
    assert u8[:4] == b"ISR1"
    plain = AESGCM(key).decrypt(u8[5:17], u8[17:], None)
    if u8[4] == 1:
        plain = gzip.decompress(plain)
    return json.loads(plain)


def git_sha(u8):
    return hashlib.sha1(b"blob %d\0" % len(u8) + u8).hexdigest()


class MockGitHub:
    """just enough of the GitHub REST API for the app's sync (refs, commits, trees, blobs)"""
    def __init__(self, records_enc):
        self.blobs, self.trees, self.commits, self.pushed = {}, {}, {}, []
        self.head = self._commit(self._tree(self._blob(records_enc)))

    def _blob(self, u8):
        sha = git_sha(u8); self.blobs[sha] = u8; return sha

    def _tree(self, blob_sha):
        sha = "t" + blob_sha[:39]; self.trees[sha] = blob_sha; return sha

    def _commit(self, tree_sha):
        sha = "c" + hashlib.sha1(tree_sha.encode() + str(len(self.commits)).encode()).hexdigest()[:39]
        self.commits[sha] = tree_sha; return sha

    async def handle(self, route):
        req = route.request
        path = req.url.split(f"/repos/{OWNER}/{REPO}", 1)[1].split("?")[0]
        m = req.method
        body = json.loads(req.post_data) if req.post_data else None
        def ok(obj, status=200):
            return route.fulfill(status=status, content_type="application/json", body=json.dumps(obj),
                                 headers={"Access-Control-Allow-Origin": "*"})
        if m == "OPTIONS":
            return await route.fulfill(status=204, headers={"Access-Control-Allow-Origin": "*",
                                       "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "GET,POST,PATCH"})
        if path == "/git/ref/heads/sync" and m == "GET":
            return await ok({"object": {"sha": self.head}})
        if path.startswith("/git/commits/") and m == "GET":
            return await ok({"tree": {"sha": self.commits[path.rsplit("/", 1)[1]]}})
        if path.startswith("/git/trees/") and m == "GET":
            return await ok({"tree": [{"path": "records.enc", "type": "blob", "sha": self.trees[path.rsplit("/", 1)[1]]}]})
        if path.startswith("/git/blobs/") and m == "GET":
            return await ok({"encoding": "base64", "content": base64.b64encode(self.blobs[path.rsplit("/", 1)[1]]).decode()})
        if path == "/git/blobs" and m == "POST":
            return await ok({"sha": self._blob(base64.b64decode(body["content"]))}, 201)
        if path == "/git/trees" and m == "POST":
            return await ok({"sha": self._tree(body["tree"][0]["sha"])}, 201)
        if path == "/git/commits" and m == "POST":
            return await ok({"sha": self._commit(body["tree"])}, 201)
        if path == "/git/refs/heads/sync" and m == "PATCH":
            self.head = body["sha"]; self.pushed.append(self.blobs[self.trees[self.commits[self.head]]])
            return await ok({"object": {"sha": self.head}})
        return await route.fulfill(status=404, content_type="application/json", body='{"message":"Not Found"}',
                                   headers={"Access-Control-Allow-Origin": "*"})


async def wait_app(pg, t=90000):
    await pg.wait_for_function("typeof APPVER!=='undefined' && !!document.querySelector('.navitem')", timeout=t)
    await pg.wait_for_timeout(600)


async def main():
    port = free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "-d", SITE],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    url = f"http://localhost:{port}/"
    fails = []
    def check(name, cond, extra=""):
        print(("ok   " if cond else "FAIL ") + name + (" · " + str(extra) if extra != "" else ""))
        if not cond:
            fails.append(name)
    try:
        async with async_playwright() as p:
            b = await p.chromium.launch()
            phone = dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2)

            # 1. new device
            ctx = await b.new_context(**phone); pg = await ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            await pg.goto(url); await pg.wait_for_selector("#f:not(.hide)")
            await pg.fill("#pw", "wrong password"); await pg.click("#go")
            await pg.wait_for_function("document.getElementById('msg') && /맞지 않아요/.test(document.getElementById('msg').textContent)", timeout=60000)
            check("wrong password refused", True)
            await pg.fill("#pw", PW.upper()); await pg.click("#go"); await wait_app(pg)
            info = await pg.evaluate("""(()=>({ver:APPVER, mode:document.compatMode, st:!!window.__STANDALONE__, title:document.title,
                icon:(document.querySelector('link[rel=apple-touch-icon]')||{}).getAttribute&&document.querySelector('link[rel=apple-touch-icon]').getAttribute('href'),
                sw:document.documentElement.scrollWidth, keys:Object.keys(localStorage).sort()}))()""")
            print("     ", info)
            check("app opens with the new password (case ignored)", info["ver"] == "v50")
            check("standards mode", info["mode"] == "CSS1Compat")
            check("site mode", info["st"] is True)
            check("touch icon is the site file", info["icon"] == "icon-180.png")
            check("no sideways scroll at 390px", info["sw"] <= 390, info["sw"])
            check("key remembered", "isn:unlock" in info["keys"])
            newkey = base64.b64decode(await pg.evaluate("localStorage.getItem('isn:unlock')"))
            await pg.reload(); await wait_app(pg)
            check("reopens without asking", (await pg.evaluate("APPVER")) == "v50")
            check("no page errors (new device)", not errs, errs[:2])
            await ctx.close()

            # 2 + 3. device that remembered the OLD password's key, with sync on; records.enc still sealed with the old key
            oldkey = os.urandom(32)
            remote = {"imp": {"remoteq": 1}, "wrong": {"remoteq": 2}, "hl": {}, "memo": {}, "hlid": 1}
            gh = MockGitHub(seal_records(remote, oldkey))
            ctx = await b.new_context(**phone); pg = await ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            await ctx.route("https://api.github.com/**", gh.handle)
            await pg.goto(url); await pg.wait_for_selector("#f:not(.hide)")
            await pg.evaluate(f"""(()=>{{ localStorage.setItem('isn:unlock','{base64.b64encode(oldkey).decode()}');
                localStorage.setItem('isn:ghrepo',JSON.stringify('{OWNER}/{REPO}'));
                localStorage.setItem('isn:ghtoken',JSON.stringify('github_pat_'+'x'.repeat(60)));
                localStorage.setItem('isn:imp',JSON.stringify({{localq:1}})); }})()""")
            await pg.reload()
            await pg.wait_for_function("document.getElementById('msg') && /바뀌었어요/.test(document.getElementById('msg').textContent)", timeout=60000)
            msg = await pg.text_content("#msg")
            prev = await pg.evaluate("localStorage.getItem('isn:unlock_prev')")
            check("old remembered key → asks for the new password once", "바뀌었어요" in msg, msg)
            check("old key kept for the records", prev == base64.b64encode(oldkey).decode())
            await pg.fill("#pw", PW); await pg.click("#go"); await wait_app(pg)
            for _ in range(60):
                if gh.pushed and await pg.evaluate("!localStorage.getItem('isn:unlock_prev')"):
                    break
                await pg.wait_for_timeout(500)
            check("records re-uploaded after the password change", len(gh.pushed) == 1, len(gh.pushed))
            if gh.pushed:
                try:
                    got = open_records(gh.pushed[-1], newkey)
                    check("re-uploaded records open with the NEW key", True)
                    check("…and contain both devices' records", got.get("imp", {}).get("remoteq") == 1 and got.get("imp", {}).get("localq") == 1, got.get("imp"))
                except Exception as e:
                    check("re-uploaded records open with the NEW key", False, e)
                try:
                    open_records(gh.pushed[-1], oldkey); check("old key no longer opens them", False)
                except Exception:
                    check("old key no longer opens them", True)
            check("old key forgotten after sync", await pg.evaluate("!localStorage.getItem('isn:unlock_prev')"))
            diag = await pg.evaluate("SYNC.log.join(' | ')")
            check("sync log mentions the old key", "이전 비밀번호의 열쇠로 열림" in diag, diag[-240:])
            check("no page errors (old-key device)", not errs, errs[:2])
            await ctx.close()

            # 3b. password changed after this device last synced: same commit, same records, but the file still uses the old key
            same = {"imp": {"s1": 1}, "wrong": {}, "hl": {}, "memo": {}, "hlid": 1}
            gh2 = MockGitHub(seal_records(same, newkey))
            ctx = await b.new_context(**phone); pg = await ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            await ctx.route("https://api.github.com/**", gh2.handle)
            await pg.goto(url); await pg.wait_for_selector("#f:not(.hide)")
            await pg.evaluate(f"""(()=>{{ localStorage.setItem('isn:ghrepo',JSON.stringify('{OWNER}/{REPO}'));
                localStorage.setItem('isn:ghtoken',JSON.stringify('github_pat_'+'x'.repeat(60))); }})()""")
            await pg.fill("#pw", PW); await pg.click("#go"); await wait_app(pg)
            for _ in range(40):
                if await pg.evaluate("!SYNC.busy && !!localStorage.getItem('isn:syncCommit')"):
                    break
                await pg.wait_for_timeout(500)
            n0 = len(gh2.pushed)
            # now make the stored file the same records sealed with the OLD key, and give the device the old key as after a change
            t = gh2.commits[gh2.head]; gh2.trees[t] = gh2._blob(seal_records(same, oldkey))
            await pg.evaluate(f"localStorage.setItem('isn:unlock_prev','{base64.b64encode(oldkey).decode()}')")
            await pg.evaluate("runSync('manual',false)")
            for _ in range(40):
                if len(gh2.pushed) > n0 and await pg.evaluate("!SYNC.busy && !localStorage.getItem('isn:unlock_prev')"):
                    break
                await pg.wait_for_timeout(500)
            check("unchanged records still re-sealed with the new key", len(gh2.pushed) == n0 + 1, len(gh2.pushed) - n0)
            if len(gh2.pushed) > n0:
                try:
                    got = open_records(gh2.pushed[-1], newkey)
                    check("…opens with the new key, same records", got.get("imp") == {"s1": 1}, got.get("imp"))
                except Exception as e:
                    check("…opens with the new key, same records", False, e)
            diag = await pg.evaluate("SYNC.log.join(' | ')")
            check("…log says why it uploaded", "새 열쇠로 다시 올림" in diag, diag[-200:])
            check("no page errors (re-seal only)", not errs, errs[:2])
            await ctx.close()

            # 4. another device after that: the file already uses the new key, the device still had the old one
            ctx = await b.new_context(**phone); pg = await ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            await ctx.route("https://api.github.com/**", gh.handle)
            await pg.goto(url); await pg.wait_for_selector("#f:not(.hide)")
            await pg.evaluate(f"""(()=>{{ localStorage.setItem('isn:unlock','{base64.b64encode(oldkey).decode()}');
                localStorage.setItem('isn:ghrepo',JSON.stringify('{OWNER}/{REPO}'));
                localStorage.setItem('isn:ghtoken',JSON.stringify('github_pat_'+'x'.repeat(60))); }})()""")
            await pg.reload()
            await pg.wait_for_function("document.getElementById('msg') && /바뀌었어요/.test(document.getElementById('msg').textContent)", timeout=60000)
            await pg.fill("#pw", PW); await pg.click("#go"); await wait_app(pg)
            for _ in range(40):
                if await pg.evaluate("!localStorage.getItem('isn:unlock_prev') && !SYNC.busy && !!localStorage.getItem('isn:syncCommit')"):
                    break
                await pg.wait_for_timeout(500)
            imp = await pg.evaluate("JSON.parse(localStorage.getItem('isn:imp')||'{}')")
            check("another device receives the records", imp.get("remoteq") == 1 and imp.get("localq") == 1, imp)
            check("…old key forgotten", await pg.evaluate("!localStorage.getItem('isn:unlock_prev')"))
            diag = await pg.evaluate("SYNC.log.join(' | ')")
            check("…file opened with the new key directly", "이전 비밀번호의 열쇠로 열림" not in diag, diag[-200:])
            if gh.pushed:
                try:
                    open_records(gh.pushed[-1], newkey); check("…anything uploaded uses the new key", True)
                except Exception as e:
                    check("…anything uploaded uses the new key", False, e)
            check("no page errors (another device)", not errs, errs[:2])
            await ctx.close()
            await b.close()
    finally:
        srv.terminate()
    print("FAILED: " + ", ".join(fails) if fails else "all checks passed")
    sys.exit(1 if fails else 0)


asyncio.run(main())
