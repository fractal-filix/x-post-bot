#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AWS Systems Manager Parameter Store 操作の共通化モジュール

- トークンの読み込み・保存機能
- エラーハンドリングの統一
- 型ヒント付きで保守性向上
"""

import json
import sys
from typing import Dict, Any, Optional

def load_token_from_parameter_store(parameter_name: str, region: str = "ap-northeast-1") -> Dict[str, Any]:
    """
    AWS Parameter Store からトークンデータを読み込む
    
    Args:
        parameter_name: パラメータストアのパラメータ名
        region: AWSリージョン
        
    Returns:
        トークンデータの辞書
        
    Raises:
        ImportError: boto3が見つからない場合
        Exception: AWS API エラーやその他のエラー
    """
    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError
        
        print(f"[INFO] Parameter Store からトークン読み込み中... (region: {region})")
        
        ssm = boto3.client('ssm', region_name=region)
        
        response = ssm.get_parameter(Name=parameter_name, WithDecryption=True)
        raw_value = response["Parameter"]["Value"].lstrip("\ufeff").strip()
        
        token_data = json.loads(raw_value)
        print(f"[INFO] ✅ Parameter Store からトークン読み込み完了: {parameter_name}")
        
        return token_data
        
    except ImportError:
        print("[ERROR] boto3 が見つかりません。pip install boto3 を実行してください", file=sys.stderr)
        raise
    except Exception as e:
        error_message = str(e)
        if "NoCredentialsError" in type(e).__name__:
            print("[ERROR] AWS認証情報が見つかりません。AWS CLI設定またはIAMロールを確認してください", file=sys.stderr)
        elif "ClientError" in type(e).__name__:
            print(f"[ERROR] Parameter Store 読み込みエラー: {error_message}", file=sys.stderr)
        else:
            print(f"[ERROR] トークン読み込み中にエラーが発生しました: {error_message}", file=sys.stderr)
        raise


def save_token_to_parameter_store(
    token_data: Dict[str, Any], 
    parameter_name: str, 
    region: str = "ap-northeast-1",
    description: Optional[str] = None
) -> bool:
    """
    AWS Parameter Store にトークンデータを保存する
    
    Args:
        token_data: トークンの辞書データ
        parameter_name: パラメータストアのパラメータ名
        region: AWSリージョン
        description: パラメータの説明（オプション）
        
    Returns:
        成功した場合はTrue、失敗した場合はFalse
    """
    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError
        
        print(f"[INFO] Parameter Store へトークン保存中... (region: {region})")
        
        ssm = boto3.client('ssm', region_name=region)
        
        # トークンデータをJSON文字列に変換
        token_json = json.dumps(token_data, ensure_ascii=False, indent=2)
        
        # Parameter Store に保存 (SecureString として暗号化)
        params = {
            'Name': parameter_name,
            'Value': token_json,
            'Type': 'SecureString',
            'Overwrite': True,
        }
        
        if description:
            params['Description'] = description
        
        ssm.put_parameter(**params)
        
        print(f"[INFO] ✅ Parameter Store 保存完了: {parameter_name}")
        return True
        
    except ImportError:
        print("[ERROR] boto3 が見つかりません。pip install boto3 を実行してください", file=sys.stderr)
        return False
    except Exception as e:
        error_message = str(e)
        if "NoCredentialsError" in type(e).__name__:
            print("[ERROR] AWS認証情報が見つかりません。AWS CLI設定またはIAMロールを確認してください", file=sys.stderr)
        elif "ClientError" in type(e).__name__:
            print(f"[ERROR] Parameter Store 保存エラー: {error_message}", file=sys.stderr)
        else:
            print(f"[ERROR] トークン保存中にエラーが発生しました: {error_message}", file=sys.stderr)
        return False


def upload_token_with_confirmation(
    token_data: Dict[str, Any], 
    region: str = "ap-northeast-1", 
    parameter_name: str = "/x-post-bot/token.json"
) -> bool:
    """
    ユーザー確認付きでトークンをParameter Storeにアップロードする
    
    Args:
        token_data: トークンの辞書データ
        region: AWSリージョン
        parameter_name: パラメータストアのパラメータ名
        
    Returns:
        アップロードが実行され成功した場合はTrue、それ以外はFalse
    """
    upload_choice = input("\nAWS Parameter Store にトークンをアップロードしますか? (y/N): ").strip().lower()
    if upload_choice not in ['y', 'yes']:
        print("[INFO] ローカルの token.json のみ保存されました。")
        return False
    
    print(f"[INFO] リージョン: {region}, パラメータ名: {parameter_name}")
    success = save_token_to_parameter_store(
        token_data, 
        parameter_name, 
        region, 
        description='X (Twitter) OAuth2 Token for x-post-bot'
    )
    
    if success:
        # アップロード成功時にローカルファイルを削除するか確認
        delete_choice = input("アップロード完了。ローカルの token.json を削除しますか? (y/N): ").strip().lower()
        if delete_choice in ['y', 'yes']:
            try:
                import os
                os.remove("token.json")
                print("[INFO] ローカルの token.json を削除しました 🗑️")
            except OSError as e:
                print(f"[WARN] ローカルファイルの削除に失敗: {e}", file=sys.stderr)
    else:
        print("[WARN] Parameter Store へのアップロードに失敗しました。ローカルの token.json は残しておきます。")
    
    return success