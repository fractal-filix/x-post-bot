# notion_queue.py
import datetime
import os
from typing import Optional, Tuple, Dict, Any

from notion_client import AsyncClient

STATUS_READY = os.getenv("NOTION_STATUS_READY", "ready")
STATUS_POSTED = os.getenv("NOTION_STATUS_POSTED", "posted")
TITLE_PROP = os.getenv("NOTION_TITLE_PROP", "Text")  # Title型のプロパティ名

def _title_plain(props: dict) -> str:
    arr = props[TITLE_PROP]["title"]
    return "".join(x.get("plain_text", "") for x in arr).strip()

async def pick_ready(notion_token: str, db_id: str) -> Tuple[AsyncClient, Optional[dict]]:
    n = AsyncClient(auth=notion_token)
    now_iso = datetime.datetime.utcnow().isoformat()
    q: Dict[str, Any] = await n.databases.query(
        database_id=db_id,
        filter={
            "and": [
                {"property": "Status", "select": {"equals": STATUS_READY}},
                {"or": [
                    {"property": "ScheduledAt", "date": {"on_or_before": now_iso}},
                    {"property": "ScheduledAt", "date": {"is_empty": True}},
                ]},
            ]
        },
        sorts=[{"property": "ScheduledAt", "direction": "ascending"}],
        page_size=1,
    )
    rs = q.get("results", [])
    return n, (rs[0] if rs else None)

def page_text(page: dict) -> str:
    return _title_plain(page["properties"])

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
