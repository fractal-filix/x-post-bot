#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os, sys, base64
from datetime import datetime, timezone
import requests

# 親ディレクトリのparameter_storeモジュールをインポート
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from parameter_store import load_token_from_parameter_store, save_token_to_parameter_store

TOKEN_URL = "https://api.twitter.com/2/oauth2/token"

def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

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
        token = load_token_from_parameter_store(name, region)
    except Exception as e:
        print(f"[ERROR] Parameter Store 読み込み失敗: {e}", file=sys.stderr); sys.exit(1)

    try:
        rt = token.get("refresh_token", "")
        print(f"[DEBUG] cid={cid[:6]}... len(refresh_token)={len(rt)} confidential={'yes' if csec else 'no'}")
        new_token = _refresh(token, cid, csec)
    except Exception as e:
        token["needs_reauth"] = True
        token["_refresh_error"] = {"message": str(e), "at": _now_iso()}
        try: 
            save_token_to_parameter_store(token, name, region)
        except Exception as e2: 
            print(f"[WARN] Parameter Store 保存失敗 (after refresh error): {e2}", file=sys.stderr)
        print(f"[ERROR] Refresh failed: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        success = save_token_to_parameter_store(new_token, name, region)
        if not success:
            raise RuntimeError("Parameter Store 保存に失敗しました")
    except Exception as e:
        print(f"[ERROR] Parameter Store 保存失敗: {e}", file=sys.stderr); sys.exit(1)
    print("[INFO] Token refreshed & saved ✅")

if __name__ == "__main__":
    main()
