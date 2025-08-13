from typing import Dict, Mapping, Any, Optional
import tweepy

def client_from_access_token(access_token: str) -> tweepy.Client:
    # OAuth2 ベアラでOK（user_auth=Falseで明示）
    return tweepy.Client(access_token)

def create_text_tweet(client: tweepy.Client, text: str) -> Dict[str, Any]:
    """
    TweepyのResponse型に依存せず、常に Dict を返す。
    返り値: {"id": Optional[str], "data": Optional[Mapping], "raw": Response}
    """
    resp = client.create_tweet(text=text, user_auth=False)
    data: Optional[Mapping[str, Any]] = getattr(resp, "data", None)
    tweet_id: Optional[str] = None
    if isinstance(data, Mapping):
        # Tweepy v4 系は data に {"id": "...", "text": "..."} が入る
        _id = data.get("id")
        if isinstance(_id, (str, int)):
            tweet_id = str(_id)
    return {"id": tweet_id, "data": data, "raw": resp}
