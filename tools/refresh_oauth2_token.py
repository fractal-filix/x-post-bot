#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
X(Twitter) OAuth2 token refresh → SSM(/x-post-bot/token.json)へ書き戻し。
環境変数は既存の x-post-bot と同じものを利用:
  - AWS_REGION, SSM_PARAM_NAME
  - X_CLIENT_ID, X_CLIENT_SECRET, X_REDIRECT_URI
期待する token.json 例:
{
  "token_type":"bearer",
  "expires_in":7200,
  "access_token":"...",
  "refresh_token":"...",
  "scope":"tweet.read tweet.write users.read offline.access"
}
"""
import json, os, sys
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError
from requests_oauthlib import OAuth2Session
from requests.auth import HTTPBasicAuth
import requests

TOKEN_URL = "https://api.twitter.com/2/oauth2/token"

def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _load_token_from_ssm(name:str, region:str) -> dict:
    ssm = boto3.client("ssm", region_name=region)
    resp = ssm.get_parameter(Name=name, WithDecryption=True)
    raw = resp["Parameter"]["Value"].lstrip("\ufeff").strip()
    return json.loads(raw)

def _save_token_to_ssm(name:str, region:str, token:dict):
    ssm = boto3.client("ssm", region_name=region)
    value = json.dumps(token, ensure_ascii=False, indent=2)
    ssm.put_parameter(Name=name, Type="SecureString", Value=value, Overwrite=True)

def _refresh(token:dict, client_id:str) -> dict:
    if not token.get("refresh_token"):
        raise RuntimeError("No refresh_token found; interactive re-auth required.")
    refresh_token = token["refresh_token"].strip()
    # PKCEのrefreshは Basic 認証ではなく、client_id をボディに含める
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(TOKEN_URL, data=data, headers=headers, timeout=20)
    if not resp.ok:
        # 返ってきたエラー本文をそのまま見られるように
        raise RuntimeError(f"{resp.status_code} {resp.text}")
    new_token = resp.json()
    new_token["_refreshed_at"] = _now_iso()
    return new_token

def main():
    region = os.environ.get("AWS_REGION", "ap-northeast-1")
    name = os.environ.get("SSM_PARAM_NAME", "/x-post-bot/token.json")
    cid  = os.environ.get("X_CLIENT_ID")

    missing = [k for k,v in {"X_CLIENT_ID": cid}.items() if not v]
    if missing:
        print(f"[ERROR] Missing envs: {', '.join(missing)}", file=sys.stderr)
        sys.exit(2)

    print(f"[INFO] Refresh start (region={region}, ssm={name})")
    try:
        token = _load_token_from_ssm(name, region)
    except ClientError as e:
        print(f"[ERROR] SSM get failed: {e}", file=sys.stderr); sys.exit(1)

    try:
        # 参考デバッグ（マスク）
        rt = token.get("refresh_token", "")
        assert cid is not None
        print(f"[DEBUG] cid={cid[:6]}... len(refresh_token)={len(rt)}")
        new_token = _refresh(token, cid)
    except Exception as e:
        # リフレッシュ失敗時は needs_reauth を立てて保存し、明示的に失敗終了
        token["needs_reauth"] = True
        token["_refresh_error"] = {"message": str(e), "at": _now_iso()}
        try: _save_token_to_ssm(name, region, token)
        except Exception as e2: print(f"[WARN] SSM put after fail: {e2}", file=sys.stderr)
        print(f"[ERROR] Refresh failed: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        _save_token_to_ssm(name, region, new_token)
    except ClientError as e:
        print(f"[ERROR] SSM put failed: {e}", file=sys.stderr); sys.exit(1)
    print("[INFO] Token refreshed & saved ✅")

if __name__ == "__main__":
    main()
