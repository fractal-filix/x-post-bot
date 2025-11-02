import sys, tweepy
from typing import Dict
from config import X_CLIENT_ID, X_CLIENT_SECRET, X_REDIRECT_URI
from token_store import save_token, load_token
from parameter_store import pull_token_if_configured, push_token_if_configured

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
    # Pull token from SSM if configured
    try:
        token_from_ssm = pull_token_if_configured()
        if token_from_ssm:
            save_token(token_from_ssm)  # keep local cache in sync for downstream modules
    except Exception as e:
        print(f"[WARN] SSM pull skipped due to error: {e}", file=sys.stderr)
    token = load_token()
    if not token:
        auth_url = oauth2.get_authorization_url()
        print("認可URL:", auth_url)
        redirect = input("リダイレクトURLを貼ってください:")
        token = oauth2.fetch_token(authorization_response=redirect)
        save_token(token)
        try:
            push_token_if_configured(token)
        except Exception as e:
            print(f"[WARN] SSM write-back skipped due to error: {e}", file=sys.stderr)
    else:
        refresh_token_str = token.get("refresh_token")
        if not isinstance(refresh_token_str, str) or not refresh_token_str:
            raise RuntimeError("refresh_tokenがありません。再認証が必要です。")
        try:
            token = refresh_token(oauth2, refresh_token_str)
            # refresh で token.json を更新したら SSM にも反映（条件付き）
            try:
                push_token_if_configured(token)
            except Exception as e:
                print(f"[WARN] SSM write-back skipped due to error: {e}", file=sys.stderr)
        except Exception as e:
            # client_id/secret/redirect不一致、refresh失効など。ローカルなら再認可へフォールバック
            if sys.stdin.isatty():
                print(f"[WARN] refresh失敗: {e}\n再認可フローに移行します。")
                auth_url = oauth2.get_authorization_url()
                print("認可URL:", auth_url)
                redirect = input("リダイレクトURLを貼ってください:")
                token = oauth2.fetch_token(authorization_response=redirect)
                save_token(token)
                try:
                    push_token_if_configured(token)
                except Exception as e:
                    print(f"[WARN] SSM write-back skipped due to error: {e}", file=sys.stderr)
            else:
                raise
    return token
