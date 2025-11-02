# リファクタリング計画（実行順）

1. `requirements.txt` の正常化（UTF-8）と `logging` 基盤導入  
2. `parameter_store.py` に SSM を集約（既存の `_ssm_*` は削除）  
3. `token_store.py` にトークンI/Oを完全一元化（直書き禁止）  
4. Notion プロパティ名/ステータス値を `config.py` に集約（未着手/progress/ready/posted）  
5. 重複ツイート判定・HTTPエラー解析をユーティリティ化  
6. `async with` 化などリソース管理  
7. CLI 化・パッケージ化（`pyproject.toml`）