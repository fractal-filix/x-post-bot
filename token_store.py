import json, os
from typing import Optional, Dict
from config import TOKEN_FILE

def save_token(token: Dict) -> None:
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token, f, ensure_ascii=False, indent=2)

def load_token() -> Optional[Dict]:
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None
