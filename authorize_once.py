#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Twitter OAuth2 Authorization Code (with PKCE) one-time authorizer.

- .env から設定値を読み込む (python-dotenv 使用)
- 認可URLを出力 → ブラウザで開いてログイン/承認
- リダイレクトURLを貼り付けると token.json を生成
"""

import base64
import hashlib
import json
import os
import secrets
import sys
import urllib.parse
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

AUTH_URL  = "https://twitter.com/i/oauth2/authorize"
TOKEN_URL = "https://api.twitter.com/2/oauth2/token"

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def gen_pkce():
    verifier = base64.urlsafe_b64encode(os.urandom(64)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge

def main():
    load_dotenv()  # .envを読み込む

    client_id     = os.getenv("X_CLIENT_ID", "").strip()
    client_secret = os.getenv("X_CLIENT_SECRET", "").strip() or None
    redirect_uri  = os.getenv("X_REDIRECT_URI", "").strip()
    scopes        = os.getenv("X_SCOPES", "tweet.read tweet.write users.read offline.access").strip()

    if not client_id or not redirect_uri:
        print("[ERROR] .envに X_CLIENT_ID / X_REDIRECT_URI が設定されていません", file=sys.stderr)
        sys.exit(2)

    code_verifier, code_challenge = gen_pkce()
    state = secrets.token_urlsafe(24)

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"

    print("[INFO] 下のURLをブラウザで開いて認可してください:")
    print(auth_url)
    redirected = input("リダイレクト後のフルURLを貼り付け: ").strip()

    parsed = urllib.parse.urlparse(redirected)
    q = urllib.parse.parse_qs(parsed.query)
    code = (q.get("code") or [None])[0]
    ret_state = (q.get("state") or [None])[0]

    if not code:
        print("[ERROR] code が見つかりません", file=sys.stderr); sys.exit(1)
    if ret_state != state:
        print("[ERROR] state が一致しません (CSRFの可能性)", file=sys.stderr); sys.exit(1)

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
        "client_id": client_id,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    if client_secret:
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        headers["Authorization"] = f"Basic {basic}"

    resp = requests.post(TOKEN_URL, data=data, headers=headers, timeout=25)
    if not resp.ok:
        print(f"[ERROR] Token exchange failed: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)

    token = resp.json()
    if isinstance(token.get("scope"), str):
        token["scope"] = token["scope"].split()
    token["_refreshed_at"] = now_iso()

    with open("token.json", "w", encoding="utf-8") as f:
        json.dump(token, f, ensure_ascii=False, indent=2)

    print("[INFO] token.json written ✅")
    rt = token.get("refresh_token", "")
    print(f"[INFO] refresh_token length = {len(rt)}")
    if len(rt) < 20:
        print("[WARN] refresh_token が短すぎます。offline.access が付与されていない可能性があります。")

if __name__ == "__main__":
    main()
