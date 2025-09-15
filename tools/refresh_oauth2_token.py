#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os, sys, base64
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError
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

def _refresh(token:dict, client_id:str, client_secret:str|None) -> dict:
    rt = (token.get("refresh_token") or "").strip()
    if len(rt) < 20:
        raise RuntimeError(f"refresh_token too short (len={len(rt)}); re-auth required.")

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    if client_secret:  # ← Confidential app（Basic必須）
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        headers["Authorization"] = f"Basic {basic}"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": rt,
            # Basicを付ける場合は通常、bodyに client_id は不要
        }
    else:              # ← Public(PKCE) app（client_id を body に）
        data = {
            "grant_type": "refresh_token",
            "refresh_token": rt,
            "client_id": client_id,
        }

    resp = requests.post(TOKEN_URL, data=data, headers=headers, timeout=20)
    if not resp.ok:
        raise RuntimeError(f"{resp.status_code} {resp.text}")
    new_token = resp.json()
    new_token["_refreshed_at"] = _now_iso()
    return new_token

def main():
    region = os.environ.get("AWS_REGION", "ap-northeast-1")
    name   = os.environ.get("SSM_PARAM_NAME", "/x-post-bot/token.json")
    cid    = (os.environ.get("X_CLIENT_ID") or "").strip()
    csec   = (os.environ.get("X_CLIENT_SECRET") or "").strip() or None  # ← ここで判定
    if not cid:
        print(f"[ERROR] Missing env: X_CLIENT_ID", file=sys.stderr); sys.exit(2)

    print(f"[INFO] Refresh start (region={region}, ssm={name})")
    try:
        token = _load_token_from_ssm(name, region)
    except ClientError as e:
        print(f"[ERROR] SSM get failed: {e}", file=sys.stderr); sys.exit(1)

    try:
        rt = token.get("refresh_token", "")
        print(f"[DEBUG] cid={cid[:6]}... len(refresh_token)={len(rt)} confidential={'yes' if csec else 'no'}")
        new_token = _refresh(token, cid, csec)
    except Exception as e:
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
