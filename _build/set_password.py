#!/usr/bin/env python3
"""Change the site password: write a new _build/site_key.json (then rebuild with make_site.py and push).

  ISN_NEW_PASSWORD='…' python3 _build/set_password.py

Makes a new P-256 site key pair and a new salt, and stores the private key only encrypted with the key of the new password
(PBKDF2-SHA256, 600,000 rounds). The private key and the password are not written anywhere else.
After the push, every device that remembered the old key is asked once for the new password; index.html keeps the old key
as 'isn:unlock_prev' so the app can read the synced study records saved under the old password and reseal them.
"""
import base64, hashlib, json, os, re, sys, unicodedata
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ITER = 600000


def norm(pw):  # must match norm() in index.html
    return re.sub(r"[\s-]", "", unicodedata.normalize("NFC", pw).lower())


def main():
    pw = os.environ.get("ISN_NEW_PASSWORD") or sys.exit("ISN_NEW_PASSWORD 환경 변수에 새 비밀번호를 넣어 주세요")
    if len(norm(pw)) < 8:
        sys.exit("비밀번호가 너무 짧아요 (8자 이상)")
    salt = os.urandom(16)
    K = hashlib.pbkdf2_hmac("sha256", norm(pw).encode("utf-8"), salt, ITER, 32)
    priv = ec.generate_private_key(ec.SECP256R1())
    n = priv.private_numbers()
    b64u = lambda i: base64.urlsafe_b64encode(i.to_bytes(32, "big")).rstrip(b"=").decode()
    jwk = {"kty": "EC", "crv": "P-256", "x": b64u(n.public_numbers.x), "y": b64u(n.public_numbers.y), "d": b64u(n.private_value)}
    wiv = os.urandom(12)
    wrapped = AESGCM(K).encrypt(wiv, json.dumps(jwk, separators=(",", ":")).encode(), None)
    pub = priv.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    out = {"v": 2,
           "note": "phone-site key: the public key seals each build; the private key is stored only encrypted with the "
                   "password key (PBKDF2-SHA256). Nothing here reveals the password.",
           "salt": base64.b64encode(salt).decode(), "iter": ITER, "wiv": base64.b64encode(wiv).decode(),
           "wrapped": base64.b64encode(wrapped).decode(), "pub": base64.b64encode(pub).decode()}
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site_key.json")
    json.dump(out, open(path, "w"), indent=1)
    print("site_key.json written — now run make_site.py and push")


if __name__ == "__main__":
    main()
