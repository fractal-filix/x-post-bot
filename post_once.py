import os, sys
from oauth2_flow import ensure_token_interactive
from x_api import client_from_access_token, create_text_tweet

def main():
    # テキストは環境変数 or 引数から
    text = os.getenv("POST_TEXT") or (sys.argv[1] if len(sys.argv) > 1 else "OAuth2 テスト投稿 ✅")

    token = ensure_token_interactive()
    client = client_from_access_token(token["access_token"])

    try:
        res = create_text_tweet(client, text)
        if res.get("id"):
            print("✅ 投稿しました！tweet_id =", res["id"])
        else:
            # 念のためのフォールバック（型不一致時など）
            print("✅ 投稿しました（ID取得できず）")
        # author_id は create_tweet 応答に含まれないことが多いのでURL生成は控える
    except Exception as e:
        # duplicate は403/エラーメッセージで判断できる
        msg = str(e).lower()
        if "duplicate" in msg:
            print("✅ 重複検知：スキップ扱い")
            sys.exit(0)
        print("❌ 投稿失敗:", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
