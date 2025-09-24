#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os, sys, base64
from datetime import datetime, timezone
import requests
from dotenv import load_dotenv

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception as e:
    print(f"[WARN] dotenv not available; skipping .env loading ({e})")

# Add parent directory to sys.path for absolute imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import from parameter_store module
from parameter_store import load_token_from_parameter_store, save_token_to_parameter_store

TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
ERROR_PARAM_NAME = "/x-post-bot/token_error.json"

# --- debug helpers (mask & hash) ---
def _mask(s: str, head: int = 4, tail: int = 4) -> str:
    if not s:
        return "<empty>"
    if len(s) <= head + tail:
        return s
    return f"{s[:head]}...{s[-tail:]}"

def _sha8(s: str) -> str:
    """
    SHA-256 の先頭8桁だけ出す（機密は漏らさず指紋化）
    """
    if not s:
        return "--------"
    import hashlib
    return hashlib.sha256(s.encode()).hexdigest()[:8]

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

    print(f"[DEBUG] Sending refresh request to {TOKEN_URL}")
    resp = requests.post(TOKEN_URL, data=data, headers=headers, timeout=20)
    
    if not resp.ok:
        error_detail = resp.text
        print(f"[ERROR] OAuth2 refresh failed - Status: {resp.status_code}, Response: {error_detail}", file=sys.stderr)
        
        # より詳細なエラー分析
        try:
            error_json = resp.json()
            error_code = error_json.get("error", "unknown_error")
            error_desc = error_json.get("error_description", "No description")
            
            if error_code == "invalid_request" and "token was invalid" in error_desc:
                raise RuntimeError(f"Refresh token is invalid or expired. Re-authentication required. Error: {error_code} - {error_desc}")
            elif error_code == "invalid_grant":
                raise RuntimeError(f"Refresh token is invalid, expired, or revoked. Re-authentication required. Error: {error_code} - {error_desc}")
            else:
                raise RuntimeError(f"OAuth2 refresh failed: {error_code} - {error_desc}")
        except json.JSONDecodeError:
            raise RuntimeError(f"OAuth2 refresh failed with HTTP {resp.status_code}: {error_detail}")
    
    new_token = resp.json()
    # （診断ログ）レスポンスに新しい refresh_token が含まれているかを可視化
    try:
        _rt_resp = new_token.get("refresh_token", "")
        print(
            f"[DEBUG] refresh_resp "
            f"rt(sig={_mask(_rt_resp)},sha8={_sha8(_rt_resp)},len={len(_rt_resp)})"
        )
    except Exception:
        pass
    new_token["_refreshed_at"] = _now_iso()
    print(f"[INFO] ✅ Token refresh successful. New access token obtained.")
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

    # トークンの状態チェック
    if token.get("needs_reauth"):
        print("[ERROR] 🔒 Token is marked as requiring re-authentication.", file=sys.stderr)
        print("[ERROR] 📋 Previous refresh attempts have failed.", file=sys.stderr)
        print("[ERROR] 💡 Manual OAuth2 flow required before automatic refresh can resume.", file=sys.stderr)
        sys.exit(1)

    # 前回のリフレッシュエラーの確認
    last_error = token.get("_refresh_error")
    if last_error and last_error.get("requires_reauth"):
        print(f"[ERROR] 🔑 Previous refresh failure requires re-authentication: {last_error.get('message', 'Unknown error')}", file=sys.stderr)
        print(f"[ERROR] 📅 Error occurred at: {last_error.get('at', 'Unknown time')}", file=sys.stderr)
        sys.exit(1)

    try:
        rt = token.get("refresh_token", "")
        print(
            f"[DEBUG] cid={cid[:6]}... "
            f"rt(sig={_mask(rt)},sha8={_sha8(rt)},len={len(rt)}) "
            f"confidential={'yes' if csec else 'no'}"
        )
        
        # リフレッシュトークンの基本的な検証
        if not rt or len(rt) < 20:
            raise RuntimeError("Refresh token is missing or too short. Re-authentication required.")
        
        new_token = _refresh(token, cid, csec)
        
        # 成功時は以前のエラー情報をクリア
        new_token.pop("needs_reauth", None)
        new_token.pop("_refresh_error", None)
        
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Refresh failed: {error_msg}", file=sys.stderr)
        
        # エラーの種類に応じた詳細なログ出力
        if "invalid" in error_msg.lower() or "expired" in error_msg.lower():
            print("[ERROR] 🔑 Refresh token is invalid or expired.", file=sys.stderr)
            print("[ERROR] 📋 Action required: Manual re-authentication needed.", file=sys.stderr)
            print("[ERROR] 💡 Run the OAuth2 flow again to get a new token.", file=sys.stderr)
            token["needs_reauth"] = True
            token["_refresh_error"] = {
                "message": error_msg, 
                "at": _now_iso(),
                "requires_reauth": True
            }
        else:
            print("[ERROR] ⚠️  Temporary refresh failure. May succeed on retry.", file=sys.stderr)
            token["_refresh_error"] = {
                "message": error_msg, 
                "at": _now_iso(),
                "requires_reauth": False
            }
        
        sys.exit(1)

    try:
        success = save_token_to_parameter_store(new_token, name, region)
        if not success:
            raise RuntimeError("Parameter Store 保存に失敗しました")
    except Exception as e:
        print(f"[ERROR] Parameter Store 保存失敗: {e}", file=sys.stderr); sys.exit(1)

    # （診断ログ）保存直後に read-back して同一性を確認
    try:
        _rb = load_token_from_parameter_store(name, region)
        _rb_rt  = _rb.get("refresh_token", "")
        _new_rt = new_token.get("refresh_token", "")
        _match  = "OK" if _rb_rt == _new_rt else "MISMATCH"
        print(
            f"[DEBUG] ssm_readback "
            f"rt(sig={_mask(_rb_rt)},sha8={_sha8(_rb_rt)},len={len(_rb_rt)}) "
            f"match={_match}"
        )
    except Exception as e:
        print(f"[WARN] read-back check failed: {e}")

    print("[INFO] Token refreshed & saved ✅")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # ここで“本番キー”を触らない。デバッグ用に別キーへ退避のみ。
        try:
            import os, json
            region = os.getenv("AWS_REGION", "ap-northeast-1")
            name = os.getenv("SSM_PARAM_NAME", "/x-post-bot/token.json")
            # 現状のSSM値を読み、それにエラーメタを付けて error キーへ保存
            current = {}
            try:
                current = load_token_from_parameter_store(name, region)
            except Exception:
                current = {}
            err = {
                "_error": str(e),
                "_at": _now_iso(),
                "_source": "refresh_oauth2_token.py",
                "snapshot": current,
            }
            save_token_to_parameter_store(err, ERROR_PARAM_NAME, region)
            print("[INFO] Error state saved to Parameter Store for debugging (separate key).")
        except Exception:
            pass
        raise
