#!/usr/bin/env python3
"""Build the phone site (app.bin + index.html) from the app page — no password needed.

  python3 _build/make_site.py PAGE.html [SITE_DIR]          # SITE_DIR = the repo root (default: the folder above _build)
  ISN_PASSWORD='…' (or ISN_KEY='<base64 site key>') python3 _build/make_site.py --check [SITE_DIR]   # decrypt app.bin and report

PAGE.html is the app page as published in the Claude version (the artifact's own page: it starts with <title> and has no
<html>/<head>/<body> of its own; the claude.ai host adds those). In a Claude session: Artifact read → strip the host's
'<!doctype html>…<body>' prefix and the closing '</body></html>'.

app.bin format "ISN2" (since 2026-10-27):
  "ISN2" | salt(16) | iterations(u32 BE) | wiv(12) | wlen(u16 BE) | wrapped(wlen) | epub(65) | iv(12) | AES-256-GCM(ck, gzip(html))
  - wrapped = AES-256-GCM(K, wiv, site private key as JWK JSON), K = PBKDF2-SHA256(normalized password, salt, iterations).
    It is made once (when the password is set) and copied unchanged into every build: _build/site_key.json.
  - each build makes a fresh P-256 key pair (eph); epub = its public key (uncompressed point);
    ck = SHA-256("ISN2" ‖ ECDH(eph, site public key).x ‖ epub).
  The browser (index.html) derives K from the password (or uses the K it remembered), unwraps the site private key,
  computes the same ECDH secret with epub and decrypts. So building needs only the site PUBLIC key, while reading needs
  the password. K itself is unchanged by updates: devices that remember it open new versions without asking again,
  and the app keeps using K to seal the synced study records (records.enc on branch 'sync').
Older "ISN1" files (AES-256-GCM with K directly) are still opened by index.html.

index.html is the lock screen. Only its first-line constants are rewritten here: VER (first 12 hex of sha256(app.bin);
also the cache key of app.bin), SIZE, SALT, ITER.
"""
import base64, gzip, hashlib, json, os, re, struct, sys, unicodedata
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HERE = os.path.dirname(os.path.abspath(__file__))


def norm(pw):  # must match norm() in index.html
    return re.sub(r"[\s-]", "", unicodedata.normalize("NFC", pw).lower())


def standalone_html(page):
    """The artifact page is a body fragment; the phone site writes it over the lock screen as a whole document."""
    page, n = re.subn(r'<link rel="apple-touch-icon" href="data:image/png;base64,[A-Za-z0-9+/=]+">',
                      '<link rel="apple-touch-icon" href="icon-180.png">', page, count=1)
    if not n:
        sys.exit("apple-touch-icon not found — is this the app page?")
    if "window.__STANDALONE__" not in page or "const APPVER=" not in page:
        sys.exit("this does not look like the app page (no __STANDALONE__ / APPVER)")
    if re.search(r"<html[\s>]|<body[\s>]", page[:2000], re.I):
        sys.exit("page still has <html>/<body> at the top — strip the claude.ai host wrapper first")
    head = ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<link rel="icon" type="image/png" sizes="192x192" href="icon-192.png">\n'
            '<script>window.__STANDALONE__=true;window.__LSP__="isn:";</script>\n')
    return head + page.strip() + "\n</body>\n</html>\n"


def load_key():
    k = json.load(open(os.path.join(HERE, "site_key.json"), encoding="utf-8"))
    assert k["v"] == 2
    return {"salt": base64.b64decode(k["salt"]), "iter": int(k["iter"]), "wiv": base64.b64decode(k["wiv"]),
            "wrapped": base64.b64decode(k["wrapped"]), "pub": base64.b64decode(k["pub"])}


def seal(html_bytes, key):
    site_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), key["pub"])
    eph = ec.generate_private_key(ec.SECP256R1())
    epub = eph.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    shared = eph.exchange(ec.ECDH(), site_pub)
    ck = hashlib.sha256(b"ISN2" + shared + epub).digest()
    iv = os.urandom(12)
    body = AESGCM(ck).encrypt(iv, gzip.compress(html_bytes, 9, mtime=0), None)
    w = key["wrapped"]
    return (b"ISN2" + key["salt"] + struct.pack(">I", key["iter"]) + key["wiv"] + struct.pack(">H", len(w)) + w
            + epub + iv + body)


def open_bin(blob, password=None, key=None):
    """decrypt app.bin with the password or the site key K itself (for --check and tests)"""
    salt, it = blob[4:20], struct.unpack(">I", blob[20:24])[0]
    K = key or hashlib.pbkdf2_hmac("sha256", norm(password).encode("utf-8"), salt, it, 32)
    if blob[:4] == b"ISN1":
        return gzip.decompress(AESGCM(K).decrypt(blob[24:36], blob[36:], None)).decode("utf-8")
    assert blob[:4] == b"ISN2", blob[:4]
    p = 24
    wiv = blob[p:p + 12]; p += 12
    wl = struct.unpack(">H", blob[p:p + 2])[0]; p += 2
    jwk = json.loads(AESGCM(K).decrypt(wiv, blob[p:p + wl], None)); p += wl
    epub = blob[p:p + 65]; p += 65
    iv = blob[p:p + 12]; p += 12
    b64u = lambda s: int.from_bytes(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)), "big")
    priv = ec.derive_private_key(b64u(jwk["d"]), ec.SECP256R1())
    shared = priv.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), epub))
    ck = hashlib.sha256(b"ISN2" + shared + epub).digest()
    return gzip.decompress(AESGCM(ck).decrypt(iv, blob[p:], None)).decode("utf-8")


def set_consts(index_html, ver, size, key):
    pat = re.compile(r'var VER="[0-9a-f]*", SIZE=\d+, SALT="[A-Za-z0-9+/=]*", ITER=\d+,')
    new = f'var VER="{ver}", SIZE={size}, SALT="{base64.b64encode(key["salt"]).decode()}", ITER={key["iter"]},'
    out, n = pat.subn(new, index_html)
    if n != 1:
        sys.exit("index.html: constants line not found")
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--check" in sys.argv:
        site = args[0] if args else os.path.dirname(HERE)
        pw, kb = os.environ.get("ISN_PASSWORD"), os.environ.get("ISN_KEY")
        if not (pw or kb):
            sys.exit("ISN_PASSWORD(사이트 비밀번호) 또는 ISN_KEY(사이트 열쇠, base64) 환경 변수가 필요해요")
        blob = open(os.path.join(site, "app.bin"), "rb").read()
        html = open_bin(blob, pw, base64.b64decode(kb) if kb else None)
        ver = hashlib.sha256(blob).hexdigest()[:12]
        idx = open(os.path.join(site, "index.html"), encoding="utf-8").read()
        appver = re.findall(r'const APPVER="([^"]+)"', html)
        ver_ok = ('VER="%s"' % ver) in idx
        print("decrypt ok · %s · %s chars · APPVER %s · index VER %s"
              % (blob[:4].decode(), format(len(html), ","), appver, "ok" if ver_ok else "MISMATCH"))
        return
    if not args:
        sys.exit(__doc__)
    page = open(args[0], encoding="utf-8").read()
    site = args[1] if len(args) > 1 else os.path.dirname(HERE)
    key = load_key()
    html = standalone_html(page).encode("utf-8")
    blob = seal(html, key)
    ver = hashlib.sha256(blob).hexdigest()[:12]
    open(os.path.join(site, "app.bin"), "wb").write(blob)
    ip = os.path.join(site, "index.html")
    idx = set_consts(open(ip, encoding="utf-8").read(), ver, len(blob), key)   # read fully before opening for writing
    open(ip, "w", encoding="utf-8").write(idx)
    print(f"app.bin {len(blob):,} bytes (html {len(html):,}) · VER {ver} · ISN2")


if __name__ == "__main__":
    main()
