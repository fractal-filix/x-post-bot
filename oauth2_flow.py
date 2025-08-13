import hashlib, os, sys, tweepy
from typing import Dict
from config import X_CLIENT_ID, X_CLIENT_SECRET, X_REDIRECT_URI
from token_store import save_token, load_token

try:
    import boto3
except Exception:
    boto3 = None

def _ssm_pull_if_configured():
    """SSM_PARAM_NAME があれば SSM から token.json を pull。成功なら True、設定なしは False、失敗は例外。"""
    name = os.getenv("SSM_PARAM_NAME")
    region = os.getenv("AWS_REGION", "ap-northeast-1")
    if not (name and boto3):
        print("[WARN] SSM_PARAM_NAME または boto3 が設定されていません。SSM pull をスキップします。", file=sys.stderr)
        return
    try:
        before = None
        if os.path.exists("token.json"):
            before = hashlib.sha256(open("token.json","rb").read()).hexdigest()
        ssm = boto3.client("ssm", region_name=region)
        val = ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
        with open("token.json", "w", encoding="utf-8") as f:
            f.write(val)
        after = hashlib.sha256(open("token.json","rb").read()).hexdigest()
        changed = (before != after)
        print(f"[INFO] SSM pull 成功（region={region}, name={name}, changed={changed})")
        return True
    except Exception as e:
        raise RuntimeError(f"SSM pull 失敗（region={region}, name={name}）: {e}")

def _ssm_write_back_if_configured():
    """SSM_WRITE_BACK=true かつ SSM_PARAM_NAME がある場合のみ、token.json を SSM に保存"""
    if os.getenv("SSM_WRITE_BACK", "false").lower() != "true":
        return
    name = os.getenv("SSM_PARAM_NAME")
    region = os.getenv("AWS_REGION", "ap-northeast-1")
    if not (name and boto3):
        return
    try:
        ssm = boto3.client("ssm", region_name=region)
        with open("token.json", "r", encoding="utf-8") as f:
            val = f.read()
        ssm.put_parameter(Name=name, Type="SecureString", Value=val, Overwrite=True)
    except Exception as e:
        print(f"[WARN] SSM への書き戻しに失敗: {e}", file=sys.stderr)

def create_oauth2_handler() -> tweepy.OAuth2UserHandler:
    return tweepy.OAuth2UserHandler(
        client_id=X_CLIENT_ID,
        redirect_uri=X_REDIRECT_URI,
        scope=["tweet.read", "tweet.write", "users.read", "offline.access"],
        client_secret=X_CLIENT_SECRET,
    )

def refresh_token(oauth2: tweepy.OAuth2UserHandler, refresh_token_str: str) -> Dict:
    token = oauth2.refresh_token(
        token_url="https://api.twitter.com/2/oauth2/token",
        refresh_token=refresh_token_str,
        client_id=X_CLIENT_ID,
        client_secret=X_CLIENT_SECRET,
    )
    save_token(token)
    return token

def ensure_token_interactive() -> Dict:
    """
    ローカル初回専用：token.json が無ければ手動認可で取得、あれば refresh。
    Actions では token.json をSSMから取得済みなので refresh パスが走る前提。
    """
    oauth2 = create_oauth2_handler()
    # まず SSM から pull（あれば）
    _ssm_pull_if_configured()
    token = load_token()
    if not token:
        auth_url = oauth2.get_authorization_url()
        print("認可URL:", auth_url)
        redirect = input("リダイレクトURLを貼ってください：")
        token = oauth2.fetch_token(authorization_response=redirect)
        save_token(token)
        _ssm_write_back_if_configured()
    else:
        refresh_token_str = token.get("refresh_token")
        if not isinstance(refresh_token_str, str) or not refresh_token_str:
            raise RuntimeError("refresh_tokenがありません。再認証が必要です。")
        try:
            token = refresh_token(oauth2, refresh_token_str)
            # refresh で token.json を更新したら SSM にも反映（条件付き）
            _ssm_write_back_if_configured()
        except Exception as e:
            # client_id/secret/redirect不一致、refresh失効など。ローカルなら再認可へフォールバック
            if sys.stdin.isatty():
                print(f"[WARN] refresh失敗: {e}\n再認可フローに移行します。")
                auth_url = oauth2.get_authorization_url()
                print("認可URL:", auth_url)
                redirect = input("リダイレクトURLを貼ってください：")
                token = oauth2.fetch_token(authorization_response=redirect)
                save_token(token)
                _ssm_write_back_if_configured()
            else:
                raise
    return token
