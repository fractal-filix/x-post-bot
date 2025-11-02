#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SSM Parameter Store access is centralized here.

- SecureString get/put with consistent error handling
- UTF-8 / BOM stripping for JSON payloads
- Helper to load/save OAuth token JSON from SSM when configured

Env:
  AWS_REGION        (default: ap-northeast-1)
  SSM_PARAM_NAME    (e.g. "/x-post-bot/token.json")
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional

from config import AWS_REGION, SSM_PARAM_NAME  # optional values

# lazy import so local dev without boto3 still works
_boto3 = None
_botocore_exc = None

def _ensure_boto3():
    global _boto3, _botocore_exc
    if _boto3 is not None:
        return
    try:
        import boto3  # type: ignore
        from botocore.exceptions import ClientError, NoCredentialsError  # type: ignore
        _boto3 = boto3
        _botocore_exc = (ClientError, NoCredentialsError)
    except Exception as e:
        _boto3 = None
        _botocore_exc = tuple()
        print("[WARN] boto3未導入のためSSMは無効化されます。`pip install boto3` を検討してください。", file=sys.stderr)

def _client(region: Optional[str] = None):
    _ensure_boto3()
    if _boto3 is None:
        raise RuntimeError("boto3 が使用できないため SSM は利用できません。")
    return _boto3.client("ssm", region_name=region or AWS_REGION or "ap-northeast-1")

def get_parameter(name: str, *, with_decryption: bool = True, region: Optional[str] = None) -> str:
    """
    Get a parameter (typically SecureString). Returns raw string value.
    """
    ssm = _client(region)
    resp = ssm.get_parameter(Name=name, WithDecryption=with_decryption)
    raw = resp["Parameter"]["Value"]
    # normalize potential BOM/whitespace
    return raw.lstrip("\ufeff").strip()

def put_parameter(
    name: str,
    value: str,
    *,
    param_type: str = "SecureString",
    overwrite: bool = True,
    description: Optional[str] = None,
    region: Optional[str] = None,
) -> None:
    """
    Put a parameter. Defaults to SecureString + Overwrite.
    """
    ssm = _client(region)
    kwargs = {
        "Name": name,
        "Value": value,
        "Type": param_type,
        "Overwrite": overwrite,
    }
    if description:
        kwargs["Description"] = description
    ssm.put_parameter(**kwargs)

def load_json(name: str, *, region: Optional[str] = None) -> Dict[str, Any]:
    """
    Load JSON object stored in SSM ParameterStore.
    """
    raw = get_parameter(name, with_decryption=True, region=region)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"SSMパラメータ {name} のJSONデコードに失敗: {e}")

def save_json(
    name: str,
    data: Dict[str, Any],
    *,
    region: Optional[str] = None,
    description: Optional[str] = None,
) -> None:
    """
    Save JSON object into SSM as SecureString.
    """
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    put_parameter(name, payload, param_type="SecureString", overwrite=True, description=description, region=region)

# ---- High-level helpers used by the app ------------------------------------

def ssm_is_configured() -> bool:
    return bool(SSM_PARAM_NAME)

def pull_token_if_configured() -> Optional[Dict[str, Any]]:
    """
    If SSM_PARAM_NAME is set and boto3 is available, load token JSON and return it.
    If not configured, return None. Propagates exceptions for real failures.
    """
    if not ssm_is_configured():
        return None
    token = load_json(SSM_PARAM_NAME)
    print(f"[INFO] ✅ SSMからトークン取得: {SSM_PARAM_NAME}")
    return token

def push_token_if_configured(token: Dict[str, Any]) -> bool:
    """
    If SSM_PARAM_NAME is set and boto3 is available, save token JSON.
    Returns True on success, False when not configured. Raises on real failures.
    """
    if not ssm_is_configured():
        return False
    save_json(SSM_PARAM_NAME, token, description="X (Twitter) OAuth2 Token for x-post-bot")
    print(f"[INFO] ✅ SSMへトークン保存: {SSM_PARAM_NAME}")
    return True
