# notion_queue.py
import datetime
import os
from typing import Optional, Tuple, Dict, Any

from notion_client import AsyncClient

STATUS_READY = os.getenv("NOTION_STATUS_READY", "ready")
STATUS_POSTED = os.getenv("NOTION_STATUS_POSTED", "posted")
CONTENT_PROP = os.getenv("NOTION_CONTENT_PROP", "Text")  # 投稿内容のプロパティ名
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

def _content_plain(props: dict) -> str:
    prop = props[CONTENT_PROP]
    if "rich_text" not in prop:
        raise ValueError(f"Property {CONTENT_PROP} must be a rich_text type")
    arr = prop["rich_text"]
    return "".join(x.get("plain_text", "") for x in arr).strip()

async def pick_ready(notion_token: str, db_id: str) -> Tuple[AsyncClient, Optional[dict]]:
    n = AsyncClient(auth=notion_token)
    # 現在時刻をタイムゾーン付きの UTC にして、Z で明示
    now_iso = (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)              # 小数秒は不要なので切り捨て
        .isoformat()                         # ex.'2025-11-01T23:11:58+00:00'
        .replace("+00:00", "Z")              # ex.'2025-11-01T23:11:58Z'
    )
    
    # デバッグ用：フィルター条件をログ出力  
    # より厳密なフィルター条件を構築
    filter_condition = {
        "and": [
            # Statusが確実にreadyであることを確認
            {"property": "Status", "select": {"equals": STATUS_READY}},
            # Status が空でないことも確認
            {"property": "Status", "select": {"is_not_empty": True}},
            {"or": [
                {"property": "ScheduledAt", "date": {"on_or_before": now_iso}},
                {"property": "ScheduledAt", "date": {"is_empty": True}},
            ]},
        ]
    }
    print(f"🔍 DEBUG: フィルター条件 STATUS_READY='{STATUS_READY}'")
    print(f"🔍 DEBUG: フィルター = {filter_condition}")
    
    # さらなるデバッグ：すべてのページのStatusを確認（デバッグモード時のみ）
    if DEBUG_MODE:
        all_pages_query = await n.databases.query(
            database_id=db_id,
            page_size=10,
        )
        all_pages = all_pages_query.get("results", [])
        print(f"🔍 DEBUG: データベース内の全ページ数 = {len(all_pages)}")
        for i, page in enumerate(all_pages):
            status_prop = page.get("properties", {}).get("Status", {})
            if "select" in status_prop and status_prop["select"]:
                status_name = status_prop["select"].get("name", "")
                print(f"🔍 DEBUG: ページ{i+1} Status = '{status_name}'")
    
    q: Dict[str, Any] = await n.databases.query(
        database_id=db_id,
        filter=filter_condition,
        sorts=[{"property": "ScheduledAt", "direction": "ascending"}],
        page_size=1,
    )
    rs = q.get("results", [])
    
    # デバッグ用：取得したページの詳細をログ出力
    if rs:
        page = rs[0]
        status_prop = page.get("properties", {}).get("Status", {})
        print(f"🔍 DEBUG: 取得したページのStatusプロパティ = {status_prop}")
        if "select" in status_prop and status_prop["select"]:
            actual_status = status_prop["select"].get("name", "")
            print(f"🔍 DEBUG: 実際のStatus値 = '{actual_status}'")
            
            # 追加検証：Statusが期待値と一致しない場合は除外
            if actual_status != STATUS_READY:
                print(f"⚠️  WARNING: Status値が期待値と異なります。期待値='{STATUS_READY}', 実際='{actual_status}' - このページをスキップします。")
                return n, None
    
    return n, (rs[0] if rs else None)

def page_text(page: dict) -> str:
    return _content_plain(page["properties"])

async def mark_posted(n: AsyncClient, page_id: str) -> None:
    await n.pages.update(
        page_id=page_id,
        properties={
            "Status": {"select": {"name": STATUS_POSTED}},
            "PostedAt": {
                "date": {
                    "start": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
                }
            },
        },
    )
