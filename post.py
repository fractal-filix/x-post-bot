import os
from dotenv import load_dotenv
import tweepy
import json

TOKEN_FILE = "token.json"
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
load_dotenv()

def save_token(token):
    with open(TOKEN_FILE, "w") as f:
        json.dump(token, f)

def load_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    return None

def refresh_token(oauth2, refresh_token):
    token = oauth2.refresh_token(
        token_url="https://api.twitter.com/2/oauth2/token",
        refresh_token=refresh_token,
        client_id=os.getenv("X_CLIENT_ID"),
        client_secret=os.getenv("X_CLIENT_SECRET"),
    )
    save_token(token)
    return token

oauth2 = tweepy.OAuth2UserHandler(
    client_id=os.getenv("X_CLIENT_ID"),
    redirect_uri=os.getenv("X_REDIRECT_URI"),
    scope=["tweet.read", "tweet.write", "users.read", "offline.access"],
    client_secret=os.getenv("X_CLIENT_SECRET")
)

token = load_token()
if not token:
    auth_url = oauth2.get_authorization_url()
    print("認可URL:", auth_url)
    redirect = input("リダイレクトURLを貼ってください：")
    token = oauth2.fetch_token(authorization_response=redirect)
    save_token(token)
else:
    token = refresh_token(oauth2, token.get("refresh_token"))

client = tweepy.Client(token["access_token"])

try:
    response = client.create_tweet(
        text="OAuth2 テスト投稿 ✅", 
        user_auth=False  # OAuth2 を明示的に使う指示（OAuth1.0aではない）
    )
    print("✅ 投稿しました！tweet_id =", response.data.get("id"))
    print(f"https://x.com/{response.data.get('author_id')}/status/{response.data.get('id')}")
except Exception as e:
    print("❌ 投稿失敗:", e)