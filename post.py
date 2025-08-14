import asyncio, os, sys
from typing import cast, Any
from config import get_notion_config
from oauth2_flow import ensure_token_interactive
from x_api import client_from_access_token, create_text_tweet
from notion_queue import pick_ready, page_text, mark_posted

def getenv_str(name: str) -> str:
    v = os.getenv(name)
    if not v:
        print(f"ENV {name} is required.", file=sys.stderr)
        sys.exit(1)
    return v

async def main():
    # Notion の接続情報を取得
    notion = get_notion_config()
    notion_token = notion["token"]
    notion_db_id = notion["db_id"]

    token = ensure_token_interactive()
    client = client_from_access_token(token["access_token"])

    # Notion から 1 件取得
    n, page = await pick_ready(notion_token, notion_db_id)
    if not page:
        print("⚠️ Notion: Status=ready の投稿が見つかりません。終了。")
        return

    text = page_text(page)
    if not text:
        print("⚠️ Notion: Text(Title) が空のためスキップ。")
        return

    try:
        res = create_text_tweet(client, text)
        if res.get("id"):
            print("✅ 投稿成功 tweet_id =", res["id"])
        else:
            print("✅ 投稿成功（ID取得できず）")
        # 投稿できたら posted に更新
        await mark_posted(n, page["id"])
    except Exception as e:
        msg = str(e).lower()
        if "duplicate" in msg:
            print("✅ 重複検知：スキップ扱い（posted に更新）")
            await mark_posted(n, page["id"])
            return
        print("❌ 投稿失敗:", e)
        raise
    finally:
        await cast(Any, n).aclose()

if __name__ == "__main__":
    asyncio.run(main())
