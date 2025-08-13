import os, sys
from dotenv import load_dotenv, dotenv_values

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
load_dotenv()

def get_env(key) -> str:
    # まず環境変数（GitHub Actionsのsecret含む）を優先
    value = os.getenv(key)
    if value is not None:
        return value
    # .envファイル（dotenv）もサポート
    env_dict = dotenv_values()
    if key in env_dict and env_dict[key] is not None:
        return str(env_dict[key])
    print(f"環境変数または.envに {key} がありません", file=sys.stderr)
    sys.exit(1)

TOKEN_FILE: str = "token.json"
X_CLIENT_ID: str = get_env("X_CLIENT_ID")
X_CLIENT_SECRET: str = get_env("X_CLIENT_SECRET")
X_REDIRECT_URI: str = get_env("X_REDIRECT_URI")
